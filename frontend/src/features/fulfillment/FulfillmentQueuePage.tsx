import { ArrowRight, CircleAlert, CloudOff, ListChecks, PackageCheck, Play } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../../api/client'
import type { MaterialRequest } from '../../api/types'
import { useAuth } from '../../app/auth'
import { listOfflineGrants, type LocalOfflineGrant } from '../../offline/store'
import { formatRequestDate, formatRequestState } from '../requests/requestUi'

interface QueueResult {
  requests: MaterialRequest[]
  offlineGrants: LocalOfflineGrant[]
  error: string
}

const claimableStates = new Set(['submitted', 'partially_fulfilled'])
const activeStates = new Set(['claimed', 'in_progress', 'ready'])

async function loadQueue(userId: string): Promise<QueueResult> {
  const offlineGrants = await listOfflineGrants(userId)
  try {
    return { requests: await api.listRequests(false), offlineGrants, error: '' }
  } catch (error_) {
    if (offlineGrants.length > 0) return { requests: [], offlineGrants, error: '' }
    return {
      requests: [],
      offlineGrants,
      error: error_ instanceof ApiError ? error_.message : 'Fulfillment queue could not be loaded',
    }
  }
}

export function FulfillmentQueuePage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [result, setResult] = useState<QueueResult | null>(null)
  const [claimingId, setClaimingId] = useState<string | null>(null)
  const requests = result?.requests ?? []
  const serverActiveRequests = requests.filter(
    (request) => activeStates.has(request.state) && request.claimed_by_user_id === user?.id,
  )
  const serverActiveIds = new Set(serverActiveRequests.map((request) => request.id))
  const activeRequests = [
    ...serverActiveRequests.map((request) => ({
      request,
      offlineReady: result?.offlineGrants.some((grant) => grant.requestId === request.id) ?? false,
    })),
    ...(result?.offlineGrants ?? [])
      .filter((grant) => !serverActiveIds.has(grant.requestId))
      .map((grant) => ({ request: grant.snapshot, offlineReady: true })),
  ]
  const queue = requests.filter(
    (request) => claimableStates.has(request.state) && request.claimed_by_user_id === null,
  )

  useEffect(() => {
    let active = true
    if (!user) return undefined
    const reload = () => {
      void loadQueue(user.id).then((loaded) => {
        if (active) setResult(loaded)
      })
    }
    reload()
    window.addEventListener('haynes:offline-queue', reload)
    return () => {
      active = false
      window.removeEventListener('haynes:offline-queue', reload)
    }
  }, [user])

  async function claim(requestId: string) {
    setClaimingId(requestId)
    try {
      const claimed = await api.claimRequest(requestId)
      navigate(`/fulfillment/${claimed.id}`)
    } catch (error_) {
      setResult((current) => ({
        requests: current?.requests ?? [],
        offlineGrants: current?.offlineGrants ?? [],
        error: error_ instanceof ApiError ? error_.message : 'Request could not be claimed',
      }))
      setClaimingId(null)
    }
  }

  async function claimNext() {
    setClaimingId('next')
    try {
      const claimed = await api.claimNextRequest()
      if (claimed) {
        navigate(`/fulfillment/${claimed.id}`)
        return
      }
      setResult((current) => ({
        requests: current?.requests ?? [],
        offlineGrants: current?.offlineGrants ?? [],
        error: 'No unclaimed request is available',
      }))
    } catch (error_) {
      setResult((current) => ({
        requests: current?.requests ?? [],
        offlineGrants: current?.offlineGrants ?? [],
        error: error_ instanceof ApiError ? error_.message : 'Next request could not be claimed',
      }))
    }
    setClaimingId(null)
  }

  return (
    <div className="page fulfillment-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">Warehouse floor / Fulfillment</p>
          <h1>Pick queue</h1>
          <p>Urgent work is ordered first while existing allocations remain protected.</p>
        </div>
        <button type="button" className="button primary" disabled={claimingId !== null || queue.length === 0} onClick={() => void claimNext()}>
          <Play size={18} aria-hidden="true" /> {claimingId === 'next' ? 'Claiming...' : 'Claim next'}
        </button>
      </header>

      {result?.error && <div className="inline-alert error" role="alert">{result.error}</div>}

      {activeRequests.length > 0 && (
        <section className="active-work-section">
          <div className="section-heading"><div><p className="eyebrow">In progress</p><h2>My active picks</h2></div><span className="count-label">{activeRequests.length} active</span></div>
          <div className="active-pick-grid">
            {activeRequests.map(({ request, offlineReady }) => (
              <Link className="active-pick-card" to={`/fulfillment/${request.id}`} key={request.id}>
                <span className="metric-icon green"><PackageCheck size={21} aria-hidden="true" /></span>
                <span><strong>{request.request_number}</strong><small>{request.recipient_name} / {formatRequestState(request.state)}</small></span>
                {offlineReady && <CloudOff className="offline-ready-icon" size={18} aria-label="Available offline" />}
                <ArrowRight size={19} aria-hidden="true" />
              </Link>
            ))}
          </div>
        </section>
      )}

      <section className="queue-section">
        <div className="section-heading"><div><p className="eyebrow">Shared queue</p><h2>Waiting to be claimed</h2></div><span className="count-label">{queue.length} requests</span></div>
        <div className="fulfillment-queue">
          {!result && <p className="empty-copy">Loading fulfillment queue...</p>}
          {result && queue.length === 0 && !result.error && (
            <div className="empty-state"><ListChecks size={32} aria-hidden="true" /><h2>Queue is clear</h2><p>No submitted request is waiting for a worker.</p></div>
          )}
          {queue.map((request, index) => {
            const allocatedLines = request.lines.filter((line) => Number(line.allocated_qty) > 0).length
            const shortages = request.lines.filter((line) => Number(line.backordered_qty) > 0).length
            return (
              <article className="queue-row" key={request.id}>
                <span className="queue-position">{String(index + 1).padStart(2, '0')}</span>
                <span className={`priority-marker ${request.priority}`} aria-label={`${request.priority} priority`} />
                <span className="queue-request"><strong>{request.request_number}</strong><small>{request.recipient_name} / {formatRequestDate(request.created_at)}</small></span>
                <span className="queue-count"><strong>{allocatedLines}</strong><small>pick lines</small></span>
                <span className={`queue-count ${shortages ? 'short' : ''}`}>
                  {shortages > 0 && <CircleAlert size={15} aria-hidden="true" />}
                  <strong>{shortages}</strong><small>short</small>
                </span>
                <button type="button" className="button secondary" disabled={claimingId !== null} onClick={() => void claim(request.id)}>
                  {claimingId === request.id ? 'Claiming...' : 'Claim'}
                </button>
              </article>
            )
          })}
        </div>
      </section>
    </div>
  )
}
