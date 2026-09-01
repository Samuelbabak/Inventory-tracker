import { AlertTriangle, ArrowRight, CloudUpload, RefreshCw, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../app/auth'
import { useOnlineStatus } from '../../app/useOnlineStatus'
import {
  discardOfflineConflict,
  listOfflineCommands,
  type StoredCommandSummary,
} from '../../offline/store'
import { synchronizeOfflineQueue } from '../../offline/sync'

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export function OfflineReviewPage() {
  const { user } = useAuth()
  const isOnline = useOnlineStatus()
  const [commands, setCommands] = useState<StoredCommandSummary[] | null>(null)
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    if (!user) return undefined
    const load = () => {
      void listOfflineCommands(user.id).then((items) => {
        if (active) setCommands(items)
      })
    }
    load()
    window.addEventListener('haynes:offline-queue', load)
    return () => {
      active = false
      window.removeEventListener('haynes:offline-queue', load)
    }
  }, [user])

  async function syncNow() {
    if (!user || !isOnline) return
    setSyncing(true)
    setError('')
    try {
      await synchronizeOfflineQueue(user.id)
      setCommands(await listOfflineCommands(user.id))
    } catch {
      setError('Offline changes could not be synchronized. They remain encrypted on this device.')
    } finally {
      setSyncing(false)
    }
  }

  async function removeConflict(commandId: string) {
    if (!user) return
    try {
      await discardOfflineConflict(user.id, commandId)
      setConfirmingId(null)
    } catch {
      setError('The local conflict could not be removed')
    }
  }

  const pending = commands?.filter((command) => command.status === 'pending') ?? []
  const conflicts = commands?.filter((command) => command.status === 'conflict') ?? []

  return (
    <div className="page offline-review-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">This device / Encrypted queue</p>
          <h1>Offline changes</h1>
          <p>Review commands waiting to synchronize and conflicts that need manager follow-up.</p>
        </div>
        <button className="button primary" type="button" onClick={() => void syncNow()} disabled={!isOnline || syncing || pending.length === 0}>
          <CloudUpload size={18} aria-hidden="true" />
          {syncing ? 'Synchronizing...' : 'Sync now'}
        </button>
      </header>

      {!isOnline && <div className="inline-alert offline-mode"><CloudUpload size={19} aria-hidden="true" /><span><strong>Device is offline</strong>Queued changes remain encrypted for this signed-in user.</span></div>}
      {error && <div className="inline-alert error" role="alert">{error}</div>}

      <section className="offline-command-section">
        <div className="section-heading"><div><p className="eyebrow">Awaiting server</p><h2>Pending sync</h2></div><span className="count-label">{pending.length} commands</span></div>
        <div className="offline-command-list">
          {commands && pending.length === 0 && <p className="empty-copy">No commands are waiting to synchronize.</p>}
          {pending.map((command) => (
            <article className="offline-command-row" key={command.id}>
              <RefreshCw size={18} aria-hidden="true" />
              <span><strong>{command.commandType.replaceAll('_', ' ')}</strong><small>Sequence {command.sequence} / {formatDate(command.createdAt)}</small></span>
              <Link className="text-link" to={`/fulfillment/${command.requestId}`}>Open task <ArrowRight size={15} aria-hidden="true" /></Link>
            </article>
          ))}
        </div>
      </section>

      <section className="offline-command-section">
        <div className="section-heading"><div><p className="eyebrow">Manager review</p><h2>Conflicts</h2></div><span className="count-label">{conflicts.length} commands</span></div>
        <div className="offline-command-list conflicts">
          {commands && conflicts.length === 0 && <p className="empty-copy">No local conflicts require attention.</p>}
          {conflicts.map((command) => (
            <article className="offline-command-row conflict" key={command.id}>
              <AlertTriangle size={19} aria-hidden="true" />
              <span>
                <strong>{command.commandType.replaceAll('_', ' ')}</strong>
                <small>{typeof command.result?.detail === 'string' ? command.result.detail : 'The server rejected this command.'}</small>
              </span>
              <Link className="text-link" to={`/fulfillment/${command.requestId}`}>Open task <ArrowRight size={15} aria-hidden="true" /></Link>
              {confirmingId === command.id ? (
                <span className="discard-confirmation">
                  <button className="icon-button" type="button" onClick={() => setConfirmingId(null)} title="Keep local conflict"><X size={18} aria-hidden="true" /><span className="sr-only">Keep local conflict</span></button>
                  <button className="button primary" type="button" onClick={() => void removeConflict(command.id)}>Confirm removal</button>
                </span>
              ) : (
                <button className="icon-button" type="button" onClick={() => setConfirmingId(command.id)} title="Remove reviewed local conflict"><Trash2 size={18} aria-hidden="true" /><span className="sr-only">Remove reviewed local conflict</span></button>
              )}
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}