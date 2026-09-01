import { AlertTriangle, CloudUpload, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../app/auth'
import { listOfflineCommands } from './store'
import { synchronizeOfflineQueue } from './sync'

interface QueueSummary {
  pending: number
  conflicts: number
}

export function OfflineQueueStatus() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [summary, setSummary] = useState<QueueSummary | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [syncError, setSyncError] = useState('')

  useEffect(() => {
    let active = true
    if (!user) return undefined

    const loadSummary = () => {
      void listOfflineCommands(user.id).then((commands) => {
        if (active) {
          setSummary({
            pending: commands.filter((command) => command.status === 'pending').length,
            conflicts: commands.filter((command) => command.status === 'conflict').length,
          })
        }
      })
    }
    const syncAndLoad = () => {
      if (!navigator.onLine) return
      void synchronizeOfflineQueue(user.id).then(loadSummary).catch(() => {
        if (active) setSyncError('Offline changes are waiting to sync')
      })
    }
    const queueChanged = () => loadSummary()

    loadSummary()
    syncAndLoad()
    window.addEventListener('online', syncAndLoad)
    window.addEventListener('haynes:offline-queue', queueChanged)
    return () => {
      active = false
      window.removeEventListener('online', syncAndLoad)
      window.removeEventListener('haynes:offline-queue', queueChanged)
    }
  }, [user])

  async function syncNow() {
    if ((summary?.conflicts ?? 0) > 0) {
      navigate('/offline')
      return
    }
    if (!user || !navigator.onLine) return
    setSyncing(true)
    setSyncError('')
    try {
      await synchronizeOfflineQueue(user.id)
      const commands = await listOfflineCommands(user.id)
      setSummary({
        pending: commands.filter((command) => command.status === 'pending').length,
        conflicts: commands.filter((command) => command.status === 'conflict').length,
      })
    } catch {
      setSyncError('Offline changes are waiting to sync')
    } finally {
      setSyncing(false)
    }
  }

  if (!summary || (summary.pending === 0 && summary.conflicts === 0 && !syncError)) return null

  const hasConflict = summary.conflicts > 0
  const conflictNoun = summary.conflicts === 1 ? 'conflict' : 'conflicts'
  const label = hasConflict
    ? `${summary.conflicts} offline ${conflictNoun}`
    : `${summary.pending} pending sync`

  return (
    <button
      type="button"
      className={`offline-queue-status ${hasConflict ? 'conflict' : ''}`}
      onClick={() => void syncNow()}
      disabled={syncing || (!navigator.onLine && !hasConflict)}
      title={syncError || label}
    >
      {hasConflict ? <AlertTriangle size={17} aria-hidden="true" /> : <CloudUpload size={17} aria-hidden="true" />}
      <span>{label}</span>
      {syncing && <RefreshCw className="spin" size={15} aria-hidden="true" />}
    </button>
  )
}
