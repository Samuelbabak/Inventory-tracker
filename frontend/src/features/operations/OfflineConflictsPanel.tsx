import { AlertTriangle, Check, ExternalLink, ShieldX } from 'lucide-react'
import { useEffect, useState, type SyntheticEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../../api/client'
import type { OfflineConflict } from '../../api/types'

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export function OfflineConflictsPanel() {
  const [conflicts, setConflicts] = useState<OfflineConflict[] | null>(null)
  const [reviewingId, setReviewingId] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    api.listOfflineConflicts()
      .then((items) => {
        if (active) setConflicts(items)
      })
      .catch((error_: unknown) => {
        if (active) setError(error_ instanceof ApiError ? error_.message : 'Offline conflicts could not be loaded')
      })
    return () => {
      active = false
    }
  }, [])

  async function reject(event: SyntheticEvent<HTMLFormElement>, commandId: string) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.rejectOfflineConflict(commandId, reason.trim())
      setConflicts((current) => current?.filter((conflict) => conflict.id !== commandId) ?? null)
      setReviewingId(null)
      setReason('')
    } catch (error_) {
      setError(error_ instanceof ApiError ? error_.message : 'Offline conflict could not be resolved')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="operations-panel" role="tabpanel">
      <div className="section-heading">
        <div><p className="eyebrow">No silent overwrite</p><h2>Offline exception queue</h2></div>
        <span className="count-label">{conflicts ? `${conflicts.length} conflicts` : 'Loading conflicts...'}</span>
      </div>
      {error && <div className="inline-alert error" role="alert">{error}</div>}
      <div className="operations-table offline-conflict-list">
        {conflicts?.map((conflict) => {
          const detail = typeof conflict.result?.detail === 'string'
            ? conflict.result.detail
            : 'The command could not be applied to the current request version.'
          return (
            <article className="offline-conflict-row" key={conflict.id}>
              <span className="integration-state requires_review"><AlertTriangle size={18} aria-hidden="true" /><strong>Conflict</strong></span>
              <span className="conflict-request">
                <strong>{conflict.request_number}</strong>
                <small>{conflict.command_type.replaceAll('_', ' ')} / sequence {conflict.sequence}</small>
              </span>
              <span><strong>{conflict.actor_name}</strong><small>Device {conflict.device_id.slice(0, 8)}</small></span>
              <time dateTime={conflict.created_at}>{formatDate(conflict.created_at)}</time>
              <Link className="icon-button" to={`/requests/${conflict.request_id}`} title="Open affected request">
                <ExternalLink size={17} aria-hidden="true" />
                <span className="sr-only">Open affected request</span>
              </Link>
              <button className="button secondary" type="button" onClick={() => setReviewingId(reviewingId === conflict.id ? null : conflict.id)}>
                <ShieldX size={17} aria-hidden="true" /> Review
              </button>
              <p className="conflict-detail">{detail}</p>
              {reviewingId === conflict.id && (
                <form className="conflict-resolution-form" onSubmit={(event) => void reject(event, conflict.id)}>
                  <label><span>Reason for rejecting stale command</span><input value={reason} onChange={(event) => setReason(event.target.value)} minLength={3} maxLength={500} required /></label>
                  <button className="button primary" type="submit" disabled={busy}><Check size={17} aria-hidden="true" />{busy ? 'Resolving...' : 'Reject command'}</button>
                </form>
              )}
            </article>
          )
        })}
        {conflicts?.length === 0 && <p className="empty-copy">No offline commands require manager review.</p>}
      </div>
    </section>
  )
}