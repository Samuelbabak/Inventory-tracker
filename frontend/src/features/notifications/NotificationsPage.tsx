import { Bell, Check, CheckCheck, ExternalLink } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../../api/client'
import type { Notification } from '../../api/types'

type NotificationFilter = 'unread' | 'all'

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export function NotificationsPage() {
  const [notifications, setNotifications] = useState<Notification[] | null>(null)
  const [filter, setFilter] = useState<NotificationFilter>('unread')
  const [busyIds, setBusyIds] = useState<Set<string>>(() => new Set())
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    api.listNotifications()
      .then((items) => {
        if (active) setNotifications(items)
      })
      .catch((error_: unknown) => {
        if (active) setError(error_ instanceof ApiError ? error_.message : 'Notifications could not be loaded')
      })
    return () => {
      active = false
    }
  }, [])

  const visible = (notifications ?? []).filter((notification) => filter === 'all' || !notification.is_read)
  const unread = (notifications ?? []).filter((notification) => !notification.is_read)

  async function markRead(notificationId: string) {
    setBusyIds((current) => new Set(current).add(notificationId))
    setError('')
    try {
      await api.markNotificationRead(notificationId)
      setNotifications((current) => current?.map((notification) => (
        notification.id === notificationId ? { ...notification, is_read: true } : notification
      )) ?? null)
      window.dispatchEvent(new Event('haynes:notifications'))
    } catch (error_) {
      setError(error_ instanceof ApiError ? error_.message : 'Notification could not be updated')
    } finally {
      setBusyIds((current) => {
        const next = new Set(current)
        next.delete(notificationId)
        return next
      })
    }
  }

  async function markAllRead() {
    for (const notification of unread) {
      await markRead(notification.id)
    }
  }

  return (
    <div className="page notifications-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">Activity / In-app updates</p>
          <h1>Notifications</h1>
          <p>Allocation, fulfillment, and request changes that need your attention.</p>
        </div>
        <button className="button secondary" type="button" onClick={() => void markAllRead()} disabled={unread.length === 0 || busyIds.size > 0}>
          <CheckCheck size={18} aria-hidden="true" />
          Mark all read
        </button>
      </header>

      {error && <div className="inline-alert error" role="alert">{error}</div>}

      <div className="notification-toolbar">
        <div className="segmented-control" aria-label="Filter notifications">
          {(['unread', 'all'] as const).map((option) => (
            <button type="button" className={filter === option ? 'active' : ''} aria-pressed={filter === option} onClick={() => setFilter(option)} key={option}>
              {option}
            </button>
          ))}
        </div>
        <span className="count-label">{notifications ? `${unread.length} unread` : 'Loading updates...'}</span>
      </div>

      <section className="notification-list" aria-label="Notification results">
        {notifications && visible.length === 0 && (
          <div className="empty-state">
            <Bell size={32} aria-hidden="true" />
            <h2>No notifications in this view</h2>
            <p>New workflow updates will appear here.</p>
          </div>
        )}
        {visible.map((notification) => {
          const requestLink = notification.entity_type === 'material_request' && notification.entity_id
            ? `/requests/${notification.entity_id}`
            : null
          return (
            <article className={`notification-row ${notification.is_read ? '' : 'unread'}`} key={notification.id}>
              <span className="notification-indicator" aria-label={notification.is_read ? 'Read' : 'Unread'} />
              <span className="notification-copy">
                <strong>{notification.title}</strong>
                <span>{notification.message}</span>
                <time dateTime={notification.created_at}>{formatDate(notification.created_at)}</time>
              </span>
              {requestLink && (
                <Link className="text-link" to={requestLink}>
                  Open <ExternalLink size={15} aria-hidden="true" />
                </Link>
              )}
              {!notification.is_read && (
                <button className="icon-button" type="button" onClick={() => void markRead(notification.id)} disabled={busyIds.has(notification.id)} title="Mark notification read">
                  <Check size={18} aria-hidden="true" />
                  <span className="sr-only">Mark notification read</span>
                </button>
              )}
            </article>
          )
        })}
      </section>
    </div>
  )
}