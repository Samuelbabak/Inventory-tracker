import { ArrowRight, CircleAlert, CloudOff, ListChecks, PackageCheck, Play, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../../api/client'
import type { MaterialRequest, Allocation } from '../../api/types'
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
  const [reallocatingId, setReallocatingId] = useState<string | null>(null)
  const [reallocateDraft, setReallocateDraft] = useState({
    allocationId: '',
    targetRequestId: '',
    quantity: '',
    reason: '',
  })
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

  async function handleReallocate() {
    if (!reallocateDraft.allocationId || !reallocateDraft.targetRequestId || !reallocateDraft.quantity || !reallocateDraft.reason.trim()) {
      setResult((current) => ({
        ...current,
        error: 'Please fill in all reallocation fields',
      }))
      return
    }
    setClaimingId('reallocate')
    try {
      await api.reallocate({
        source_allocation_id: reallocateDraft.allocationId,
        target_request_id: reallocateDraft.targetRequestId,
        quantity: Number(reallocateDraft.quantity),
        reason: reallocateDraft.reason.trim(),
      })
      setReallocatingId(null)
      setReallocateDraft({ allocationId: '', targetRequestId: '', quantity: '', reason: '' })
      // Reload queue to reflect changes
      if (user) {
        void loadQueue(user.id).then((loaded) => setResult(loaded))
      }
    } catch (error_) {
      setResult((current) => ({
        ...current,
        error: error_ instanceof ApiError ? error_.message : 'Reallocation failed',
      }))
    } finally {
      setClaimingId(null)
    }
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
                {user?.roles.includes('inventory_manager') && (
                  <button type="button" className="button ghost" disabled={claimingId !== null} onClick={() => {
                    setReallocatingId(request.id)
                    setReallocateDraft({ allocationId: '', targetRequestId: '', quantity: '', reason: '' })
                  }}>
                    Reallocate
                  </button>
                )}
              </article>
            )
          })}
        </div>
      </section>

      {reallocatingId && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-header">
              <h2>Reallocate Stock</h2>
              <button type="button" className="button-icon" onClick={() => setReallocatingId(null)}><X size={20} /></button>
            </div>
            <div className="modal-body">
              {requests.find(r => r.id === reallocatingId) && (
                <>
                  <label>
                    <span>Source Allocation</span>
                    <select value={reallocateDraft.allocationId} onChange={(e) => setReallocateDraft(prev => ({ ...prev, allocationId: e.target.value }))}>
                      <option value="">Select allocation...</option>
                      {requests.find(r => r.id === reallocatingId)?.lines.flatMap(l => l.allocations).map(a => (
                        <option key={a.id} value={a.id}>{a.fulfillment_sku} - {a.location_code} ({a.quantity} {a.fulfillment_uom})</option>
                      ))}
                    </select>
                  </label>
                  {reallocateDraft.allocationId && (
                    <label>
                      <span>Target Request (Backordered)</span>
                      <select value={reallocateDraft.targetRequestId} onChange={(e) => setReallocateDraft(prev => ({ ...prev, targetRequestId: e.target.value }))}>
                        <option value="">Select target request...</option>
                        {requests
                          .filter(r => r.id !== reallocatingId)
                          .filter(r => r.lines.some(l => {
                            const sourceAlloc = requests.find(req => req.id === reallocatingId)?.lines.flatMap(line => line.allocations).find(a => a.id === reallocateDraft.allocationId);
                            return l.sku === sourceAlloc?.fulfillment_sku && Number(l.backordered_qty) > 0;
                          }))
                          .map(r => (
                            <option key={r.id} value={r.id}>{r.request_number} - {r.recipient_name}</option>
                          ))
                        }
                      </select>
                    </label>
                  )}
                  <label>
                    <span>Quantity</span>
                    <input type="number" value={reallocateDraft.quantity} onChange={(e) => setReallocateDraft(prev => ({ ...prev, quantity: e.target.value }))} />
                  </label>
                  <label>
                    <span>Reason</span>
                    <input value={reallocateDraft.reason} onChange={(e) => setReallocateDraft(prev => ({ ...prev, reason: e.target.value }))} />
                  </label>
                </>
              )}
            </div>
            <div className="modal-footer">
              <button type="button" className="button secondary" onClick={() => setReallocatingId(null)}>Cancel</button>
              <button type="button" className="button primary" disabled={claimingId === 'reallocate'} onClick={() => void handleReallocate()}>
                {claimingId === 'reallocate' ? 'Processing...' : 'Confirm Reallocation'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
