import {
  AlertTriangle,
  ArrowRight,
  Bell,
  ClipboardList,
  PackageCheck,
  PackageSearch,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../../api/client'
import type { InventoryItem, MaterialRequest, Notification } from '../../api/types'
import { useAuth } from '../../app/auth'

interface DashboardData {
  inventory: InventoryItem[]
  requests: MaterialRequest[]
  notifications: Notification[]
}

const openStates = new Set(['draft', 'submitted', 'claimed', 'in_progress', 'ready', 'partially_fulfilled'])

function formatQuantity(value: number) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 }).format(value)
}

export function DashboardPage() {
  const { user } = useAuth()
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    Promise.all([api.listInventory(), api.listRequests(false), api.listNotifications()])
      .then(([inventory, requests, notifications]) => {
        if (active) setData({ inventory, requests, notifications })
      })
      .catch((error_: unknown) => {
        if (active) setError(error_ instanceof ApiError ? error_.message : 'Warehouse data is unavailable')
      })
    return () => {
      active = false
    }
  }, [])

  const shortageItems = data?.inventory.filter((item) => Number(item.shortage_qty) > 0) ?? []
  const openRequests = data?.requests.filter((request) => openStates.has(request.state)) ?? []
  const urgentRequests = openRequests.filter((request) => request.priority === 'urgent')
  const itemsWithUncommittedStock = data?.inventory.filter((item) => Number(item.free_to_promise) > 0).length ?? 0
  const unreadNotifications = data?.notifications.filter((notification) => !notification.is_read).length ?? 0

  return (
    <div className="page dashboard-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">{user?.warehouse_code} / Live operations</p>
          <h1>Warehouse overview</h1>
          <p>Current demand, stock position, and work requiring attention.</p>
        </div>
        <Link className="button primary" to="/inventory">
          <PackageSearch size={18} aria-hidden="true" />
          Find material
        </Link>
      </header>

      {error && <div className="inline-alert error" role="alert">{error}</div>}

      <section className="metric-grid" aria-label="Warehouse summary">
        <article className="metric-card">
          <span className="metric-icon green"><PackageCheck size={21} aria-hidden="true" /></span>
          <div><span>Active inventory</span><strong>{data ? data.inventory.length : '--'}</strong></div>
          <small>{data ? `${itemsWithUncommittedStock} items have uncommitted stock` : 'Loading stock coverage'}</small>
        </article>
        <article className="metric-card">
          <span className="metric-icon blue"><ClipboardList size={21} aria-hidden="true" /></span>
          <div><span>Open requests</span><strong>{data ? openRequests.length : '--'}</strong></div>
          <small>{urgentRequests.length} marked urgent</small>
        </article>
        <article className={`metric-card ${shortageItems.length ? 'attention' : ''}`}>
          <span className="metric-icon amber"><AlertTriangle size={21} aria-hidden="true" /></span>
          <div><span>Items short</span><strong>{data ? shortageItems.length : '--'}</strong></div>
          <small>Demand beyond available stock</small>
        </article>
        <article className="metric-card">
          <span className="metric-icon red"><Bell size={21} aria-hidden="true" /></span>
          <div><span>Unread updates</span><strong>{data ? unreadNotifications : '--'}</strong></div>
          <small>Request and allocation activity</small>
        </article>
      </section>

      <div className="dashboard-columns">
        <section className="data-section">
          <div className="section-heading">
            <div><p className="eyebrow">Fulfillment</p><h2>Active request queue</h2></div>
            <span className="count-label">{openRequests.length} open</span>
          </div>
          <div className="request-list compact-list">
            {!data && !error && <p className="empty-copy">Loading current requests...</p>}
            {data && openRequests.length === 0 && <p className="empty-copy">No requests are waiting for fulfillment.</p>}
            {openRequests.slice(0, 5).map((request) => (
              <article className="request-row" key={request.id}>
                <span className={`priority-marker ${request.priority}`} aria-label={`${request.priority} priority`} />
                <div>
                  <strong>{request.request_number}</strong>
                  <span>{request.recipient_name} / {request.lines.length} {request.lines.length === 1 ? 'line' : 'lines'}</span>
                </div>
                <span className={`status-badge ${request.state}`}>{request.state.replaceAll('_', ' ')}</span>
              </article>
            ))}
          </div>
        </section>

        <section className="data-section">
          <div className="section-heading">
            <div><p className="eyebrow">Inventory</p><h2>Shortage watch</h2></div>
            <Link className="text-link" to="/inventory">
              All stock <ArrowRight size={16} aria-hidden="true" />
            </Link>
          </div>
          <div className="shortage-list compact-list">
            {!data && !error && <p className="empty-copy">Calculating stock coverage...</p>}
            {data && shortageItems.length === 0 && <p className="empty-copy">No item shortages are recorded.</p>}
            {shortageItems.slice(0, 5).map((item) => (
              <Link className="shortage-row" to={`/inventory?item=${item.id}`} key={item.id}>
                <span><strong>{item.sku}</strong><small>{item.description}</small></span>
                <span><strong>{formatQuantity(Number(item.shortage_qty))}</strong><small>short</small></span>
              </Link>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
