import { AlertTriangle, CheckCircle2, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { ReconciliationRun } from '../../api/types'

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function label(value: string) {
  return value.replaceAll('_', ' ')
}

export function ReconciliationPanel({ enabled }: Readonly<{ enabled: boolean }>) {
  const [runs, setRuns] = useState<ReconciliationRun[]>([])
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    api.listReconciliations()
      .then((records) => {
        if (active) setRuns(records)
      })
      .catch((error_: unknown) => {
        if (active) setError(error_ instanceof ApiError ? error_.message : 'Reconciliation history is unavailable')
      })
    return () => {
      active = false
    }
  }, [])

  async function reconcile() {
    setRunning(true)
    setError('')
    try {
      const run = await api.runReconciliation()
      setRuns((current) => [run, ...current])
      if (run.difference_count > 0) setExpandedId(run.id)
    } catch (error_) {
      setError(error_ instanceof ApiError ? error_.message : 'Reconciliation could not be completed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <section className="reconciliation-panel">
      <div className="section-heading">
        <div><p className="eyebrow">Local issue ledger / Spectrum</p><h2>Reconciliation</h2></div>
        <button className="button secondary" type="button" disabled={!enabled || running} onClick={() => void reconcile()}>
          <RefreshCw className={running ? 'spin' : ''} size={18} aria-hidden="true" />
          {running ? 'Comparing...' : 'Reconcile now'}
        </button>
      </div>
      {error && <div className="inline-alert error" role="alert">{error}</div>}
      <div className="operations-table reconciliation-list">
        {runs.map((run) => (
          <div className="reconciliation-run" key={run.id}>
            <button type="button" className="reconciliation-row" onClick={() => setExpandedId((current) => current === run.id ? null : run.id)}>
              <span className={`integration-state ${run.difference_count ? 'requires_review' : ''}`}>
                {run.difference_count ? <AlertTriangle size={17} aria-hidden="true" /> : <CheckCircle2 size={17} aria-hidden="true" />}
                <strong>{run.difference_count ? `${run.difference_count} differences` : 'Matched'}</strong>
              </span>
              <span><strong>{run.matched_count} of {run.checked_count} issue records matched</strong><small>{run.error ?? `Run ${run.id.slice(0, 8)}`}</small></span>
              <time dateTime={run.started_at}>{formatDate(run.started_at)}</time>
            </button>
            {expandedId === run.id && run.differences.length > 0 && (
              <div className="reconciliation-differences">
                {run.differences.map((difference) => (
                  <div key={difference.event_id}>
                    <span><strong>{difference.request_number || difference.business_reference}</strong><small>{difference.sku || 'Spectrum issue'}</small></span>
                    <span><strong>{label(difference.kind)}</strong><small>{difference.detail}</small></span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        {runs.length === 0 && <p className="empty-copy">No reconciliation runs have been recorded.</p>}
      </div>
    </section>
  )
}