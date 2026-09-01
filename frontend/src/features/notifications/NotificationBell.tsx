import { Bell } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'

export function NotificationBell() {
  const [unreadCount, setUnreadCount] = useState(0)

  useEffect(() => {
    let active = true
    const load = () => {
      void api.listNotifications().then((notifications) => {
        if (active) setUnreadCount(notifications.filter((notification) => !notification.is_read).length)
      }).catch(() => undefined)
    }
    load()
    const timer = window.setInterval(load, 60_000)
    window.addEventListener('haynes:notifications', load)
    return () => {
      active = false
      window.clearInterval(timer)
      window.removeEventListener('haynes:notifications', load)
    }
  }, [])

  return (
    <Link className="notification-bell" to="/notifications" aria-label={`${unreadCount} unread notifications`}>
      <Bell size={20} aria-hidden="true" />
      {unreadCount > 0 && <span>{unreadCount > 99 ? '99+' : unreadCount}</span>}
    </Link>
  )
}