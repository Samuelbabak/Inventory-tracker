import {
  Activity,
  AlertTriangle,
  BookOpenText,
  Boxes,
  CloudOff,
  History,
  LayoutGrid,
  Map as MapIcon,
  QrCode,
  RefreshCw,
  Search,
  ServerCog,
  ShieldOff,
  TabletSmartphone,
  Users,
} from 'lucide-react'
import { useEffect, useState, type SyntheticEvent } from 'react'
import { api, ApiError } from '../../api/client'
import type {
  AuditEvent,
  Device,
  InventoryEvent,
  InventoryItem,
  Location,
  OutboxEvent,
  SpectrumStatus,
} from '../../api/types'
import { useAuth } from '../../app/auth'
import { CatalogPanel } from '../catalog/CatalogPanel'
import { UserAdministrationPanel } from '../identity/UserAdministrationPanel'
import { LayoutEditor } from '../locations/LayoutEditor'
import { OfflineConflictsPanel } from './OfflineConflictsPanel'
import { QrLabelsPanel } from './QrLabelsPanel'
import { ReconciliationPanel } from './ReconciliationPanel'

type OperationsView = 'map' | 'ledger' | 'audit' | 'offline' | 'spectrum' | 'catalog' | 'layout' | 'labels' | 'devices' | 'users'

interface OperationsData {
  inventory: InventoryItem[]
  locations: Location[]
  inventoryEvents: InventoryEvent[]
  auditEvents: AuditEvent[]
  spectrumStatus: SpectrumStatus
  outboxEvents: OutboxEvent[]
  devices: Device[]
}

const views = [
  { id: 'map', label: 'Warehouse map', icon: MapIcon },
  { id: 'ledger', label: 'Inventory ledger', icon: History },
  { id: 'audit', label: 'Audit trail', icon: Activity },
  { id: 'catalog', label: 'Catalog', icon: BookOpenText },
  { id: 'layout', label: 'Layout editor', icon: LayoutGrid },
  { id: 'offline', label: 'Offline conflicts', icon: CloudOff },
  { id: 'spectrum', label: 'Spectrum', icon: ServerCog },
  { id: 'labels', label: 'QR labels', icon: QrCode },
  { id: 'devices', label: 'Devices', icon: TabletSmartphone },
  { id: 'users', label: 'Users', icon: Users },
] satisfies Array<{ id: OperationsView; label: string; icon: typeof MapIcon }>

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function formatQuantity(value: string) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 }).format(Number(value))
}

function label(value: string) {
  return value.replaceAll('_', ' ')
}

export function OperationsPage() {
  const { user } = useAuth()
  const isAdministrator = user?.roles.includes('system_administrator') ?? false
  const [view, setView] = useState<OperationsView>('map')
  const [data, setData] = useState<OperationsData | null>(null)
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [retryingId, setRetryingId] = useState<string | null>(null)
  const [revokingId, setRevokingId] = useState<string | null>(null)
  const [revokeReason, setRevokeReason] = useState('')

  useEffect(() => {
    let active = true
    Promise.all([
      api.listInventory(),
      api.listLocations(),
      api.listInventoryEvents(),
      api.listAuditEvents(),
      api.spectrumStatus(),
      api.listSpectrumEvents(),
      isAdministrator ? api.listDevices() : Promise.resolve([]),
    ])
      .then(([inventory, locations, inventoryEvents, auditEvents, spectrumStatus, outboxEvents, devices]) => {
        if (active) {
          setData({ inventory, locations, inventoryEvents, auditEvents, spectrumStatus, outboxEvents, devices })
        }
      })
      .catch((error_: unknown) => {
        if (active) setError(error_ instanceof ApiError ? error_.message : 'Operations data is unavailable')
      })
    return () => {
      active = false
    }
  }, [isAdministrator])

  const normalizedQuery = query.trim().toLocaleLowerCase()
  const positionByCode = new Map(
    (data?.inventory ?? []).flatMap((item) =>
      item.locations.map((position) => [
        position.location_code,
        { sku: item.sku, description: item.description, quantity: position.on_hand, uom: item.uom },
      ] as const),
    ),
  )
  const mappedLocations = (data?.locations ?? []).filter(
    (location) => location.grid_row !== null && location.grid_column !== null,
  )
  const rowCount = Math.max(1, ...mappedLocations.map((location) => (location.grid_row ?? 0) + 1))
  const columnCount = Math.max(1, ...mappedLocations.map((location) => (location.grid_column ?? 0) + 1))
  const inventoryEvents = (data?.inventoryEvents ?? []).filter((event) =>
    !normalizedQuery ||
    [event.sku, event.event_type, event.location_code ?? '', event.actor_name, event.reason ?? '']
      .join(' ')
      .toLocaleLowerCase()
      .includes(normalizedQuery),
  )
  const auditEvents = (data?.auditEvents ?? []).filter((event) =>
    !normalizedQuery ||
    [event.actor_name, event.action, event.entity_type, event.reason ?? '']
      .join(' ')
      .toLocaleLowerCase()
      .includes(normalizedQuery),
  )

  async function retryEvent(eventId: string) {
    setRetryingId(eventId)
    setError('')
    try {
      const updated = await api.retrySpectrumEvent(eventId)
      setData((current) => current && ({
        ...current,
        outboxEvents: current.outboxEvents.map((event) => event.id === eventId ? updated : event),
        spectrumStatus: {
          ...current.spectrumStatus,
          counts: {
            ...current.spectrumStatus.counts,
            pending: (current.spectrumStatus.counts.pending ?? 0) + 1,
            requires_review: Math.max(0, (current.spectrumStatus.counts.requires_review ?? 0) - 1),
          },
        },
      }))
    } catch (error_) {
      setError(error_ instanceof ApiError ? error_.message : 'Spectrum event could not be retried')
    } finally {
      setRetryingId(null)
    }
  }

  async function revokeDevice(event: SyntheticEvent<HTMLFormElement>, deviceId: string) {
    event.preventDefault()
    setError('')
    try {
      const updated = await api.revokeDevice(deviceId, revokeReason.trim())
      setData((current) => current && ({
        ...current,
        devices: current.devices.map((device) => device.id === deviceId ? updated : device),
      }))
      setRevokingId(null)
      setRevokeReason('')
    } catch (error_) {
      setError(error_ instanceof ApiError ? error_.message : 'Device could not be revoked')
    }
  }

  return (
    <div className="page operations-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">Control room / Warehouse administration</p>
          <h1>Operations</h1>
          <p>Inspect physical layout, immutable movement history, and integration health.</p>
        </div>
      </header>

      {error && <div className="inline-alert error" role="alert">{error}</div>}

      <div className="operations-tabs" role="tablist" aria-label="Operations views">
        {views.filter(({ id }) => !['devices', 'layout', 'users'].includes(id) || isAdministrator).map(({ id, label: viewLabel, icon: Icon }) => (
          <button
            type="button"
            role="tab"
            aria-selected={view === id}
            className={view === id ? 'active' : ''}
            onClick={() => setView(id)}
            key={id}
          >
            <Icon size={18} aria-hidden="true" />
            {viewLabel}
          </button>
        ))}
      </div>

      {view === 'map' && (
        <section className="operations-panel" role="tabpanel">
          <div className="section-heading">
            <div><p className="eyebrow">Live positions</p><h2>Warehouse grid</h2></div>
            <span className="count-label">{data ? `${mappedLocations.length} mapped locations` : 'Loading map...'}</span>
          </div>
          {data && mappedLocations.length === 0 && <p className="empty-copy">No mapped locations are configured.</p>}
          <div
            className="warehouse-map"
            style={{ gridTemplateColumns: `repeat(${columnCount}, minmax(108px, 1fr))`, gridTemplateRows: `repeat(${rowCount}, minmax(92px, auto))` }}
          >
            {mappedLocations.map((location) => {
              const position = positionByCode.get(location.code)
              return (
                <article
                  className={`map-cell ${location.is_staging ? 'staging' : ''} ${position ? 'stocked' : ''}`}
                  style={{ gridRow: (location.grid_row ?? 0) + 1, gridColumn: (location.grid_column ?? 0) + 1 }}
                  key={location.id}
                >
                  <span>{location.code}</span>
                  <strong>{position?.sku ?? (location.is_staging ? 'Staging' : 'Open')}</strong>
                  <small>{position ? `${formatQuantity(position.quantity)} ${position.uom}` : `Pick ${location.pick_sequence}`}</small>
                </article>
              )
            })}
          </div>
        </section>
      )}

      {(view === 'ledger' || view === 'audit') && (
        <section className="operations-panel" role="tabpanel">
          <div className="operations-toolbar">
            <div>
              <p className="eyebrow">{view === 'ledger' ? 'Append-only stock movement' : 'Administrative actions'}</p>
              <h2>{view === 'ledger' ? 'Inventory ledger' : 'Audit trail'}</h2>
            </div>
            <label className="compact-search">
              <span className="sr-only">Search {view === 'ledger' ? 'inventory ledger' : 'audit trail'}</span>
              <Search size={18} aria-hidden="true" />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Action, item, actor, location" />
            </label>
          </div>
          <div className="operations-table" role="table" aria-label={view === 'ledger' ? 'Inventory ledger' : 'Audit trail'}>
            {view === 'ledger' && inventoryEvents.map((event) => (
              <div className="operations-row ledger-row" role="row" key={event.id}>
                <span><strong>{event.sku}</strong><small>{event.location_code ?? 'No stock position'}</small></span>
                <span><strong>{label(event.event_type)}</strong><small>{event.reason ?? 'Operational movement'}</small></span>
                <span className="numeric"><strong>{formatQuantity(event.quantity)} {event.uom}</strong><small>{event.actor_name}</small></span>
                <time dateTime={event.created_at}>{formatDate(event.created_at)}</time>
              </div>
            ))}
            {view === 'audit' && auditEvents.map((event) => (
              <div className="operations-row audit-row" role="row" key={event.id}>
                <span><strong>{label(event.action)}</strong><small>{label(event.entity_type)}</small></span>
                <span><strong>{event.actor_name}</strong><small>{event.reason ?? 'No reason supplied'}</small></span>
                <code>{event.entity_id.slice(0, 8)}</code>
                <time dateTime={event.created_at}>{formatDate(event.created_at)}</time>
              </div>
            ))}
            {data && ((view === 'ledger' && inventoryEvents.length === 0) || (view === 'audit' && auditEvents.length === 0)) && (
              <p className="empty-copy">No matching events.</p>
            )}
          </div>
        </section>
      )}

      {view === 'offline' && <OfflineConflictsPanel />}

      {view === 'catalog' && <CatalogPanel />}

      {view === 'layout' && isAdministrator && <LayoutEditor />}

      {view === 'users' && isAdministrator && <UserAdministrationPanel />}

      {view === 'labels' && <QrLabelsPanel inventory={data?.inventory ?? []} locations={data?.locations ?? []} />}

      {view === 'spectrum' && (
        <section className="operations-panel" role="tabpanel">
          <div className="spectrum-summary">
            <span className="metric-icon green"><ServerCog size={21} aria-hidden="true" /></span>
            <span><strong>Spectrum adapter</strong><small>{data?.spectrumStatus.health.status ?? 'Checking health...'}</small></span>
            <dl>
              <div><dt>Pending</dt><dd>{data?.spectrumStatus.counts.pending ?? '--'}</dd></div>
              <div><dt>Succeeded</dt><dd>{data?.spectrumStatus.counts.succeeded ?? '--'}</dd></div>
              <div><dt>Review</dt><dd>{data?.spectrumStatus.counts.requires_review ?? '--'}</dd></div>
            </dl>
          </div>
          <div className="section-heading">
            <div><p className="eyebrow">Transactional outbox</p><h2>Delivery events</h2></div>
            <span className="count-label">{data ? `${data.outboxEvents.length} recent events` : 'Loading events...'}</span>
          </div>
          <div className="operations-table">
            {data?.outboxEvents.map((event) => (
              <div className="operations-row spectrum-row" key={event.id}>
                <span className={`integration-state ${event.status}`}>
                  {event.status === 'requires_review' ? <AlertTriangle size={17} aria-hidden="true" /> : <Boxes size={17} aria-hidden="true" />}
                  <strong>{label(event.status)}</strong>
                </span>
                <span><strong>{label(event.event_type)}</strong><small>{event.last_error ?? `Attempt ${event.attempt_count}`}</small></span>
                <time dateTime={event.created_at}>{formatDate(event.created_at)}</time>
                {event.status === 'requires_review' ? (
                  <button
                    className="icon-button"
                    type="button"
                    onClick={() => void retryEvent(event.id)}
                    disabled={retryingId === event.id}
                    title="Retry Spectrum delivery"
                  >
                    <RefreshCw className={retryingId === event.id ? 'spin' : ''} size={18} aria-hidden="true" />
                    <span className="sr-only">Retry Spectrum delivery</span>
                  </button>
                ) : <span />}
              </div>
            ))}
            {data?.outboxEvents.length === 0 && <p className="empty-copy">No Spectrum deliveries have been recorded.</p>}
          </div>
          <ReconciliationPanel enabled={data?.spectrumStatus.capabilities.reconcile ?? false} />
        </section>
      )}

      {view === 'devices' && isAdministrator && (
        <section className="operations-panel" role="tabpanel">
          <div className="section-heading">
            <div><p className="eyebrow">Enrolled browsers and handhelds</p><h2>Warehouse devices</h2></div>
            <span className="count-label">{data ? `${data.devices.length} enrolled` : 'Loading devices...'}</span>
          </div>
          <div className="operations-table">
            {data?.devices.map((device) => (
              <div className={`operations-row device-row ${device.revoked_at ? 'revoked' : ''}`} key={device.id}>
                <span className={`integration-state ${device.revoked_at ? 'failed' : ''}`}>
                  {device.revoked_at ? <ShieldOff size={17} aria-hidden="true" /> : <TabletSmartphone size={17} aria-hidden="true" />}
                  <strong>{device.revoked_at ? 'Revoked' : 'Active'}</strong>
                </span>
                <span><strong>{device.display_name}</strong><small>{device.device_identifier}</small></span>
                <time dateTime={device.last_seen_at}>Seen {formatDate(device.last_seen_at)}</time>
                {!device.revoked_at && revokingId !== device.id && (
                  <button className="button secondary" type="button" onClick={() => setRevokingId(device.id)}>Revoke</button>
                )}
                {revokingId === device.id && (
                  <form className="device-revoke-form" onSubmit={(event) => void revokeDevice(event, device.id)}>
                    <label><span>Revocation reason</span><input value={revokeReason} onChange={(event) => setRevokeReason(event.target.value)} minLength={3} maxLength={500} required /></label>
                    <button className="button primary" type="submit"><ShieldOff size={17} aria-hidden="true" />Confirm revoke</button>
                    <button className="button secondary" type="button" onClick={() => { setRevokingId(null); setRevokeReason('') }}>Keep active</button>
                  </form>
                )}
              </div>
            ))}
            {data?.devices.length === 0 && <p className="empty-copy">No warehouse devices have enrolled yet.</p>}
          </div>
        </section>
      )}
    </div>
  )
}