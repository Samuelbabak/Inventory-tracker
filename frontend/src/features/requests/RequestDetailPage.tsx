import { ArrowLeft, CheckCircle2, ClipboardCopy, MapPin, Send, XCircle } from 'lucide-react'
import { useEffect, useState, type SyntheticEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../../api/client'
import type { MaterialRequest } from '../../api/types'
import { useAuth } from '../../app/auth'
import { formatRequestDate, formatRequestQuantity, formatRequestState } from './requestUi'

interface RequestDetailResult {
  request: MaterialRequest | null
  error: string
}

export function RequestDetailPage() {
  const { user } = useAuth()
  const { requestId } = useParams()
  const navigate = useNavigate()
  const [result, setResult] = useState<RequestDetailResult | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [cancelOpen, setCancelOpen] = useState(false)
  const [cancelReason, setCancelReason] = useState('')
  const request = result?.request
  const canCancel = Boolean(
    request &&
    !['completed', 'cancelled'].includes(request.state) &&
    user?.roles.some((role) => ['warehouse_worker', 'inventory_manager'].includes(role)),
  )

  useEffect(() => {
    let active = true
    if (!requestId) return undefined
    api
      .getRequest(requestId)
      .then((materialRequest) => {
        if (active) setResult({ request: materialRequest, error: '' })
      })
      .catch((error_: unknown) => {
        if (active) setResult({ request: null, error: error_ instanceof ApiError ? error_.message : 'Request could not be loaded' })
      })
    return () => {
      active = false
    }
  }, [requestId])

  async function submitDraft() {
    if (!request) return
    setSubmitting(true)
    try {
      setResult({ request: await api.submitRequest(request.id), error: '' })
    } catch (error_) {
      setResult({ request, error: error_ instanceof ApiError ? error_.message : 'Draft could not be submitted' })
    } finally {
      setSubmitting(false)
    }
  }

  async function cancelRequest(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!request) return
    setSubmitting(true)
    try {
      setResult({ request: await api.cancelRequest(request.id, cancelReason.trim()), error: '' })
      setCancelOpen(false)
      setCancelReason('')
    } catch (error_) {
      setResult({ request, error: error_ instanceof ApiError ? error_.message : 'Request could not be cancelled' })
    } finally {
      setSubmitting(false)
    }
  }

  if (!result) return <div className="page"><p className="empty-copy">Loading request...</p></div>

  return (
    <div className="page request-detail-page">
      <Link className="back-link" to="/requests"><ArrowLeft size={17} aria-hidden="true" /> Requests</Link>
      {result.error && <div className="inline-alert error" role="alert">{result.error}</div>}
      {request && (
        <>
          <header className="request-detail-header">
            <div>
              <span className={`status-badge ${request.state}`}>{formatRequestState(request.state)}</span>
              <p className="eyebrow">{request.priority} priority / Version {request.version}</p>
              <h1>{request.request_number}</h1>
              <p>For {request.recipient_name} / Created by {request.creator_name} / {formatRequestDate(request.created_at)}</p>
            </div>
            <div className="detail-actions">
              <button type="button" className="button secondary" onClick={() => navigate('/requests/new', { state: { repeat: request } })}>
                <ClipboardCopy size={18} aria-hidden="true" /> Repeat
              </button>
              {request.state === 'draft' && (
                <button type="button" className="button primary" disabled={submitting} onClick={() => void submitDraft()}>
                  <Send size={18} aria-hidden="true" /> {submitting ? 'Submitting...' : 'Submit'}
                </button>
              )}
              {canCancel && (
                <button type="button" className="button secondary danger-action" disabled={submitting} onClick={() => setCancelOpen((current) => !current)}>
                  <XCircle size={18} aria-hidden="true" /> Cancel
                </button>
              )}
            </div>
          </header>

          {cancelOpen && (
            <form className="request-cancel-form" onSubmit={(event) => void cancelRequest(event)}>
              <label><span>Cancellation reason</span><input value={cancelReason} onChange={(event) => setCancelReason(event.target.value)} minLength={3} maxLength={500} required /></label>
              <button className="button primary" type="submit" disabled={submitting}><XCircle size={18} aria-hidden="true" />{submitting ? 'Cancelling...' : 'Confirm cancellation'}</button>
            </form>
          )}

          <section className="request-facts" aria-label="Request details">
            <div><span>Recipient</span><strong>{request.recipient_name}</strong></div>
            <div><span>Job</span><strong>{request.job_number ?? 'Local stock'}</strong></div>
            <div><span>Cost code</span><strong>{request.cost_code ?? 'Not required'}</strong></div>
            <div><span>Claimed by</span><strong>{request.claimed_by_name ?? 'Unclaimed'}</strong></div>
          </section>

          {request.urgent_reason && <div className="urgent-reason"><strong>Urgent reason</strong><span>{request.urgent_reason}</span></div>}

          <section className="request-lines-section">
            <div className="section-heading"><div><p className="eyebrow">Material</p><h2>Request lines</h2></div><span className="count-label">{request.lines.length} lines</span></div>
            <div className="request-lines-table">
              {request.lines.map((line) => (
                <article className="request-detail-line" key={line.id}>
                  <div className="line-title"><strong>{line.sku}</strong><span>{line.description}</span><small>{line.inventory_path === 'spectrum_managed' ? 'Spectrum managed' : 'Local general use'} / {line.uom}</small></div>
                  <dl className="line-quantities">
                    <div><dt>Requested</dt><dd>{formatRequestQuantity(line.requested_qty)}</dd></div>
                    <div><dt>Allocated</dt><dd>{formatRequestQuantity(line.allocated_qty)}</dd></div>
                    <div><dt>Picked</dt><dd>{formatRequestQuantity(line.picked_qty)}</dd></div>
                    <div><dt>Issued</dt><dd>{formatRequestQuantity(line.issued_qty)}</dd></div>
                    <div className={Number(line.backordered_qty) > 0 ? 'short' : ''}><dt>Backordered</dt><dd>{formatRequestQuantity(line.backordered_qty)}</dd></div>
                  </dl>
                  {line.allocations.length > 0 && (
                    <div className="allocation-list">
                      {line.allocations.map((allocation) => (
                        <div key={allocation.id}>
                          <MapPin size={16} aria-hidden="true" />
                          <span>
                            <strong>{allocation.location_code} / {allocation.fulfillment_sku}</strong>
                            <small>{formatRequestQuantity(allocation.quantity)} {line.uom} allocated{allocation.is_substitute ? ` / substitute for ${line.sku}` : ''}</small>
                          </span>
                          {allocation.pick_confirmed && <CheckCircle2 size={18} aria-label="Pick confirmed" />}
                        </div>
                      ))}
                    </div>
                  )}
                </article>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  )
}
