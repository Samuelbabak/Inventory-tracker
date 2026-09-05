import { ArrowLeft, Check, CheckCircle2, CloudOff, HardDriveDownload, MapPin, PackageCheck, ScanLine } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError } from '../../api/client'
import type { Allocation, MaterialRequest } from '../../api/types'
import { useAuth } from '../../app/auth'
import { useOnlineStatus } from '../../app/useOnlineStatus'
import {
  getDeviceId,
  getOfflineGrant,
  queueOfflineCommand,
  saveOfflineGrant,
  type LocalOfflineGrant,
} from '../../offline/store'
import { formatRequestQuantity, formatRequestState } from '../requests/requestUi'

interface PickPageResult {
  request: MaterialRequest | null
  grant: LocalOfflineGrant | null
  error: string
}

interface PickDraft {
  location: string
  sku: string
  quantity: string
  shortageReason: string
}

function allocationDrafts(request: MaterialRequest) {
  const entries = request.lines.flatMap((line) =>
    line.allocations.map((allocation) => [
      allocation.id,
      {
        location: '',
        sku: '',
        quantity: String(Number(allocation.quantity) - Number(allocation.released_qty)),
        shortageReason: '',
      },
    ] as const),
  )
  return Object.fromEntries(entries) as Record<string, PickDraft>
}

function offlinePickSnapshot(
  request: MaterialRequest,
  allocationId: string,
  pickedQuantity: number,
) {
  const lines = request.lines.map((line) => {
    const allocations = line.allocations.map((allocation) => {
      if (allocation.id !== allocationId) return allocation
      const available = Number(allocation.quantity) - Number(allocation.released_qty)
      return {
        ...allocation,
        picked_qty: String(pickedQuantity),
        released_qty: String(Number(allocation.released_qty) + available - pickedQuantity),
        pick_confirmed: true,
      }
    })
    const picked = allocations.reduce((total, allocation) => total + Number(allocation.picked_qty), 0)
    const issued = allocations.reduce((total, allocation) => total + Number(allocation.issued_qty), 0)
    const openAllocated = allocations.reduce(
      (total, allocation) =>
        total + Number(allocation.quantity) - Number(allocation.issued_qty) - Number(allocation.released_qty),
      0,
    )
    return {
      ...line,
      picked_qty: String(picked),
      issued_qty: String(issued),
      backordered_qty: String(
        Math.max(Number(line.requested_qty) - issued - Number(line.cancelled_qty) - openAllocated, 0),
      ),
      allocations,
    }
  })
  const allConfirmed = lines.every((line) => line.allocations.every((allocation) => allocation.pick_confirmed))
  return {
    ...request,
    state: allConfirmed ? 'ready' : 'in_progress',
    version: request.version + 1,
    updated_at: new Date().toISOString(),
    lines,
  } satisfies MaterialRequest
}

function offlineHandoffSnapshot(request: MaterialRequest) {
  const lines = request.lines.map((line) => {
    const allocations = line.allocations.map((allocation) => ({
      ...allocation,
      issued_qty: allocation.picked_qty,
    }))
    const issued = allocations.reduce((total, allocation) => total + Number(allocation.issued_qty), 0)
    return {
      ...line,
      issued_qty: String(issued),
      backordered_qty: String(
        Math.max(Number(line.requested_qty) - issued - Number(line.cancelled_qty), 0),
      ),
      allocations,
    }
  })
  const completed = lines.every(
    (line) => Number(line.issued_qty) + Number(line.cancelled_qty) >= Number(line.requested_qty),
  )
  return {
    ...request,
    state: completed ? 'completed' : 'partially_fulfilled',
    claimed_by_user_id: null,
    claimed_by_name: null,
    version: request.version + 1,
    updated_at: new Date().toISOString(),
    lines,
  } satisfies MaterialRequest
}

async function loadPickTask(userId: string, requestId: string): Promise<PickPageResult> {
  const grant = await getOfflineGrant(userId, requestId)
  if (!navigator.onLine) {
    if (grant) return { request: grant.snapshot, grant, error: '' }
    return { request: null, grant: null, error: 'This task was not prepared for offline work' }
  }
  try {
    return { request: await api.getRequest(requestId), grant, error: '' }
  } catch (error_) {
    if (grant) return { request: grant.snapshot, grant, error: '' }
    return {
      request: null,
      grant: null,
      error: error_ instanceof ApiError ? error_.message : 'Pick task could not be loaded',
    }
  }
}

export function PickRequestPage() {
  const { requestId } = useParams()
  const { user } = useAuth()
  const isOnline = useOnlineStatus()
  const [result, setResult] = useState<PickPageResult | null>(null)

  useEffect(() => {
    let active = true
    if (!requestId || !user) return undefined
    void loadPickTask(user.id, requestId).then((loaded) => {
      if (active) setResult(loaded)
    })
    return () => {
      active = false
    }
  }, [requestId, user])

  function updateRequest(request: MaterialRequest) {
    setResult((current) => ({ request, grant: current?.grant ?? null, error: '' }))
  }

  function showError(message: string) {
    setResult((current) => ({
      request: current?.request ?? null,
      grant: current?.grant ?? null,
      error: message,
    }))
  }

  function storeGrant(grant: LocalOfflineGrant) {
    setResult((current) => ({ request: current?.request ?? grant.snapshot, grant, error: '' }))
  }

  if (!result) return <div className="page"><p className="empty-copy">Opening pick task...</p></div>

  return (
    <div className="page pick-page">
      <Link className="back-link" to="/fulfillment"><ArrowLeft size={17} aria-hidden="true" /> Pick queue</Link>
      {result.error && <div className="inline-alert error" role="alert">{result.error}</div>}
      {result.request && (
        <PickTask
          key={`${result.request.id}:${result.request.version}`}
          request={result.request}
          offlineGrant={result.grant}
          isOnline={isOnline}
          onUpdated={updateRequest}
          onGrant={storeGrant}
          onError={showError}
        />
      )}
    </div>
  )
}

function PickTask({
  request,
  offlineGrant,
  isOnline,
  onUpdated,
  onGrant,
  onError,
}: Readonly<{
  request: MaterialRequest
  offlineGrant: LocalOfflineGrant | null
  isOnline: boolean
  onUpdated: (request: MaterialRequest) => void
  onGrant: (grant: LocalOfflineGrant) => void
  onError: (message: string) => void
}>) {
  const { user } = useAuth()
  const [drafts, setDrafts] = useState(() => allocationDrafts(request))
  const [busyId, setBusyId] = useState<string | null>(null)
  const [handoffConfirmed, setHandoffConfirmed] = useState(false)
  const [substituteCandidates, setSubstituteCandidates] = useState<Record<string, SubstituteCandidateResponse[]>>({})
  const [substituteDraft, setSubstituteDraft] = useState<Record<string, { candidateId: string; quantity: string; reason: string }}>({})
  const ownedByUser = request.claimed_by_user_id === user?.id
  const canClaim = ['submitted', 'partially_fulfilled'].includes(request.state) && request.claimed_by_user_id === null
  const allocations = request.lines.flatMap((line) => line.allocations.map((allocation) => ({ line, allocation })))
  const confirmedCount = allocations.filter(({ allocation }) => allocation.pick_confirmed).length
  let offlineActionLabel = 'Keep offline'
  if (busyId === 'offline') offlineActionLabel = 'Preparing...'
  if (offlineGrant) offlineActionLabel = 'Offline ready'

  function changeDraft(allocationId: string, changes: Partial<PickDraft>) {
    setDrafts((current) => ({ ...current, [allocationId]: { ...current[allocationId], ...changes } }))
  }

  async function claimTask() {
    setBusyId('claim')
    try {
      onUpdated(await api.claimRequest(request.id))
    } catch (error_) {
      onError(error_ instanceof ApiError ? error_.message : 'Request could not be claimed')
      setBusyId(null)
    }
  }

  async function prepareOffline() {
    if (!user || !isOnline) return
    setBusyId('offline')
    try {
      const deviceId = getDeviceId()
      await api.enrollDevice(deviceId, `Warehouse browser ${deviceId.slice(0, 8)}`)
      const grant = await api.createOfflineGrant(request.id, deviceId)
      await saveOfflineGrant(user.id, grant)
      const stored = await getOfflineGrant(user.id, request.id)
      if (stored) onGrant(stored)
    } catch (error_) {
      onError(error_ instanceof ApiError ? error_.message : 'Task could not be prepared for offline work')
      setBusyId(null)
    }
  }

  async function confirmPick(allocation: Allocation) {
    const draft = drafts[allocation.id]
    if (!draft.location.trim() || !draft.sku.trim()) {
      onError('Scan or enter both the expected location and item')
      return
    }
    const available = Number(allocation.quantity) - Number(allocation.released_qty)
    if (Number(draft.quantity) < available && !draft.shortageReason.trim()) {
      onError('A shortage reason is required when the picked quantity is reduced')
      return
    }
    setBusyId(allocation.id)
    const payload = {
      allocation_id: allocation.id,
      quantity: Number(draft.quantity),
      scanned_location_code: draft.location.trim(),
      scanned_sku: draft.sku.trim(),
      shortage_reason: draft.shortageReason.trim() || undefined,
    }
    try {
      if (!isOnline) {
        if (!offlineGrant) throw new Error('This task is not available offline')
        const snapshot = offlinePickSnapshot(request, allocation.id, Number(draft.quantity))
        await queueOfflineCommand(offlineGrant.id, 'record_pick', payload, snapshot)
        onUpdated(snapshot)
      } else {
        onUpdated(await api.recordPick(request.id, payload))
      }
    } catch (error_) {
      onError(error_ instanceof ApiError ? error_.message : `${allocation.fulfillment_sku} pick could not be confirmed`)
      setBusyId(null)
    }
  }

  async function fetchSubstitutes(allocation: Allocation) {
    if (!isOnline) {
      onError('Substitutions are not available offline')
      return
    }
    setBusyId(`sub-list-${allocation.id}`)
    try {
      const candidates = await api.listSubstituteCandidates(request.id, allocation.id)
      setSubstituteCandidates((current) => ({ ...current, [allocation.id]: candidates }))
    } catch (error_) {
      onError(error_ instanceof ApiError ? error_.message : 'Could not load substitute candidates')
    } finally {
      setBusyId(null)
    }
  }

  async function confirmSubstitution(allocation: Allocation) {
    const draft = substituteDraft[allocation.id]
    if (!draft || !draft.candidateId || !draft.reason.trim()) {
      onError('Please select a candidate and provide a reason')
      return
    }
    const candidate = substituteCandidates[allocation.id]?.find((c) => c.stock_position_id === draft.candidateId)
    if (!candidate) {
      onError('Invalid substitute candidate selected')
      return
    }
    setBusyId(`sub-confirm-${allocation.id}`)
    try {
      const payload = {
        allocation_id: allocation.id,
        alternate_stock_position_id: draft.candidateId,
        quantity: Number(draft.quantity),
        reason: draft.reason.trim(),
      }
      onUpdated(await api.substituteAllocation(request.id, payload))
      setSubstituteCandidates((current) => {
        const next = { ...current }
        delete next[allocation.id]
        return next
      })
      setSubstituteDraft((current) => {
        const next = { ...current }
        delete next[allocation.id]
        return next
      })
    } catch (error_) {
      onError(error_ instanceof ApiError ? error_.message : 'Substitution could not be confirmed')
    } finally {
      setBusyId(null)
    }
  }

  async function handoff() {
    setBusyId('handoff')
    try {
      if (!isOnline) {
        if (!offlineGrant) throw new Error('This task is not available offline')
        const snapshot = offlineHandoffSnapshot(request)
        await queueOfflineCommand(offlineGrant.id, 'handoff', {}, snapshot)
        onUpdated(snapshot)
      } else {
        onUpdated(await api.handoffRequest(request.id))
      }
    } catch (error_) {
      onError(error_ instanceof ApiError ? error_.message : 'Handoff could not be recorded')
      setBusyId(null)
    }
  }

  return (
    <>
      <header className="pick-header">
        <div>
          <span className={`status-badge ${request.state}`}>{formatRequestState(request.state)}</span>
          <p className="eyebrow">{request.priority} priority / {confirmedCount} of {allocations.length} positions verified</p>
          <h1>{request.request_number}</h1>
          <p>Material for {request.recipient_name}{request.job_number ? ` / Job ${request.job_number}` : ''}</p>
        </div>
        <div className="detail-actions">
          {ownedByUser && isOnline && ['claimed', 'in_progress', 'ready'].includes(request.state) && (
            <button type="button" className="button secondary" disabled={busyId !== null || offlineGrant !== null} onClick={() => void prepareOffline()}>
              <HardDriveDownload size={18} aria-hidden="true" />
              {offlineActionLabel}
            </button>
          )}
          {canClaim && isOnline && (
            <button type="button" className="button primary" disabled={busyId !== null} onClick={() => void claimTask()}>
              <PackageCheck size={18} aria-hidden="true" /> {busyId === 'claim' ? 'Claiming...' : 'Claim request'}
            </button>
          )}
        </div>
      </header>

      {!isOnline && offlineGrant && (
        <output className="inline-alert offline-mode" aria-live="polite">
          <CloudOff size={19} aria-hidden="true" />
          <span><strong>Working offline</strong>Verified changes are encrypted on this device and will sync in order.</span>
        </output>
      )}

      {!ownedByUser && !canClaim && (
        <div className="inline-alert warning">This request is assigned to {request.claimed_by_name ?? 'another worker'}.</div>
      )}

      <div className="pick-layout">
        {Object.entries(substituteCandidates).map(([allocationId, candidates]) => {
          const { allocation, line } = allocations.find(({ allocation: a }) => a.id === allocationId) || {};
          const available = allocation ? Number(allocation.quantity) - Number(allocation.released_qty) : '1';

          return (
            <section className="substitution-panel" key={allocationId}>
              <div className="section-heading">
                <div><p className="eyebrow">Substitution</p><h2>Select substitute for position {allocationId.slice(-4)}</h2></div>
                <button type="button" className="button secondary" onClick={() => setSubstituteCandidates((current) => {
                  const next = { ...current };
                  delete next[allocationId];
                  return next;
                })}>Cancel</button>
              </div>
              <div className="candidate-list">
                {candidates.map((candidate) => (
                  <div className="candidate-item" key={candidate.stock_position_id}>
                    <div className="candidate-info">
                      <strong>{candidate.sku}</strong>
                      <small>{candidate.description}</small>
                      <span className="candidate-stock">{candidate.available_qty} {candidate.uom} available</span>
                    </div>
                    <button 
                      type="button" 
                      className="button secondary" 
                      disabled={busyId !== null} 
                      onClick={() => setSubstituteDraft((current) => ({ ...current, [allocationId]: { candidateId: candidate.stock_position_id, quantity: String(available), reason: '' } }))}
                    >
                      Select
                    </button>
                  </div>
                ))}
              </div>
              {substituteDraft[allocationId] && (
                <div className="substitution-form">
                  <label><span>Quantity to substitute / {allocation?.fulfillment_uom || line?.uom}</span><input type="number" inputMode="decimal" value={substituteDraft[allocationId].quantity} onChange={(event) => setSubstituteDraft((current) => ({ ...current, [allocationId]: { ...substituteDraft[allocationId], quantity: event.target.value } }))} /></label>
                  <label><span>Reason for substitution</span><input value={substituteDraft[allocationId].reason} onChange={(event) => setSubstituteDraft((current) => ({ ...current, [allocationId]: { ...substituteDraft[allocationId], reason: event.target.value } }))} /></label>
                  <button type="button" className="button primary" disabled={busyId !== null} onClick={() => void confirmSubstitution(allocation!)}>
                    {busyId === `sub-confirm-${allocationId}` ? 'Confirming...' : 'Confirm substitution'}
                  </button>
                </div>
              )}
            </section>
          );
        })})}
        <section className="pick-list-section">
          <div className="section-heading"><div><p className="eyebrow">Location order</p><h2>Pick positions</h2></div><span className="count-label">{allocations.length} positions</span></div>
          <div className="pick-list">
            {allocations.length === 0 && <p className="empty-copy">No stock is allocated. This request remains backordered.</p>}
            {allocations.map(({ line, allocation }, index) => {
              const draft = drafts[allocation.id]
              const available = Number(allocation.quantity) - Number(allocation.released_qty)
              const isShort = Number(draft.quantity) < available
              return (
                <article className={`pick-card ${allocation.pick_confirmed ? 'confirmed' : ''}`} key={allocation.id}>
                  <div className="pick-card-heading">
                    <span className="pick-sequence">{String(index + 1).padStart(2, '0')}</span>
                    <span className="item-identity">
                      <strong>{allocation.fulfillment_sku}</strong>
                      <small>{allocation.is_substitute ? `${allocation.fulfillment_description} / substitute for ${line.sku}` : line.description}</small>
                    </span>
                    <span className="pick-target"><strong>{formatRequestQuantity(allocation.quantity)}</strong><small>{allocation.fulfillment_uom || line.uom} allocated</small></span>
                    {allocation.pick_confirmed && <span className="confirmed-label"><CheckCircle2 size={18} aria-hidden="true" /> Confirmed</span>}
                  </div>
                  <div className="expected-location"><MapPin size={18} aria-hidden="true" /><span><small>Expected location</small><strong>{allocation.location_code}</strong></span></div>
                  {!allocation.pick_confirmed && ownedByUser && (
                    <div className="pick-entry-grid">
                      <label><span><ScanLine size={16} aria-hidden="true" /> Location scan</span><input value={draft.location} onChange={(event) => changeDraft(allocation.id, { location: event.target.value })} autoCapitalize="characters" /></label>
                      <label><span><ScanLine size={16} aria-hidden="true" /> Item scan</span><input value={draft.sku} onChange={(event) => changeDraft(allocation.id, { sku: event.target.value })} autoCapitalize="characters" /></label>
                      <label><span>Picked / {allocation.fulfillment_uom || line.uom}</span><input type="number" inputMode="decimal" min={allocation.issued_qty} max={available} step="0.001" value={draft.quantity} onChange={(event) => changeDraft(allocation.id, { quantity: event.target.value })} /></label>
                      {isShort && <label className="shortage-field"><span>Shortage reason</span><input value={draft.shortageReason} onChange={(event) => changeDraft(allocation.id, { shortageReason: event.target.value })} maxLength={500} /></label>}
                      <div className="pick-actions">
                        <button type="button" className="button primary" disabled={busyId !== null} onClick={() => void confirmPick(allocation)}>
                          <Check size={18} aria-hidden="true" /> {busyId === allocation.id ? 'Confirming...' : 'Confirm pick'}
                        </button>
                        {!allocation.is_substitute && (
                          <button type="button" className="button secondary" disabled={busyId !== null} onClick={() => void fetchSubstitutes(allocation)}>
                            {busyId === `sub-list-${allocation.id}` ? 'Loading...' : 'Substitute'}
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </article>
              )
            })}
          </div>
        </section>

        <aside className="handoff-panel">
          <p className="eyebrow">Final handoff</p>
          <h2>{request.recipient_name}</h2>
          <dl>
            <div><dt>Positions verified</dt><dd>{confirmedCount} / {allocations.length}</dd></div>
            <div><dt>Request state</dt><dd>{formatRequestState(request.state)}</dd></div>
            <div><dt>Job</dt><dd>{request.job_number ?? 'Local stock'}</dd></div>
          </dl>
          <label className="confirmation-check">
            <input type="checkbox" checked={handoffConfirmed} onChange={(event) => setHandoffConfirmed(event.target.checked)} />
            <span>Physical handoff completed</span>
          </label>
          <button type="button" className="button primary" disabled={!ownedByUser || request.state !== 'ready' || !handoffConfirmed || busyId !== null} onClick={() => void handoff()}>
            <PackageCheck size={18} aria-hidden="true" /> {busyId === 'handoff' ? 'Recording...' : 'Complete handoff'}
          </button>
        </aside>
      </div>
    </>
  )
}
