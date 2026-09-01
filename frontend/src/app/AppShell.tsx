import {
  Boxes,
  CircleUserRound,
  ClipboardList,
  ListChecks,
  LayoutDashboard,
  LogOut,
  PackageMinus,
  PackageSearch,
  PanelsTopLeft,
  Wifi,
  WifiOff,
} from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { OfflineQueueStatus } from '../offline/OfflineQueueStatus'
import { NotificationBell } from '../features/notifications/NotificationBell'
import { useAuth } from './auth'
import { useOnlineStatus } from './useOnlineStatus'

const roleLabels = {
  employee: 'Employee',
  foreman: 'Foreman',
  warehouse_worker: 'Warehouse worker',
  inventory_manager: 'Inventory manager',
  system_administrator: 'System administrator',
} as const

export function AppShell() {
  const { user, logout } = useAuth()
  const isOnline = useOnlineStatus()
  const primaryRole = user?.roles.at(-1)
  const canUseRequests = user?.roles.some((role) =>
    ['foreman', 'warehouse_worker', 'inventory_manager', 'system_administrator'].includes(role),
  )
  const canFulfill = user?.roles.some((role) => ['warehouse_worker', 'inventory_manager'].includes(role))
  const canWithdraw = user?.roles.some((role) => ['employee', 'warehouse_worker', 'inventory_manager'].includes(role))
  const canManage = user?.roles.some((role) => ['inventory_manager', 'system_administrator'].includes(role))

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <NavLink className="app-brand" to="/" aria-label="Haynes inventory home">
          <span className="brand-mark" aria-hidden="true">
            <Boxes size={25} strokeWidth={2.2} />
          </span>
          <span>
            <strong>HAYNES</strong>
            <small>INVENTORY</small>
          </span>
        </NavLink>

        <nav className="primary-nav" aria-label="Primary navigation">
          <NavLink to="/" end>
            <LayoutDashboard size={20} aria-hidden="true" />
            Overview
          </NavLink>
          <NavLink to="/inventory">
            <PackageSearch size={20} aria-hidden="true" />
            Inventory
          </NavLink>
          {canUseRequests && (
            <NavLink to="/requests">
              <ClipboardList size={20} aria-hidden="true" />
              Requests
            </NavLink>
          )}
          {canFulfill && (
            <NavLink to="/fulfillment">
              <ListChecks size={20} aria-hidden="true" />
              Fulfillment
            </NavLink>
          )}
          {canWithdraw && (
            <NavLink to="/general-use">
              <PackageMinus size={20} aria-hidden="true" />
              General use
            </NavLink>
          )}
          {canManage && (
            <NavLink to="/operations">
              <PanelsTopLeft size={20} aria-hidden="true" />
              Operations
            </NavLink>
          )}
        </nav>

        <div className="sidebar-footer">
          <div className="warehouse-chip">
            <span className="warehouse-code">{user?.warehouse_code}</span>
            <span>Main warehouse</span>
          </div>
          <button className="icon-button" type="button" onClick={() => void logout()} title="Sign out">
            <LogOut size={20} aria-hidden="true" />
            <span className="sr-only">Sign out</span>
          </button>
        </div>
      </aside>

      <div className="app-workspace">
        <header className="app-header">
          <NotificationBell />
          <OfflineQueueStatus />
          <output className={`network-status ${isOnline ? 'online' : 'offline'}`} aria-live="polite">
            {isOnline ? <Wifi size={17} aria-hidden="true" /> : <WifiOff size={17} aria-hidden="true" />}
            <span>{isOnline ? 'Live' : 'Offline'}</span>
          </output>
          <div className="user-summary">
            <CircleUserRound size={30} aria-hidden="true" />
            <span>
              <strong>{user?.display_name}</strong>
              <small>{primaryRole ? roleLabels[primaryRole] : 'Warehouse user'}</small>
            </span>
          </div>
        </header>

        <main className="app-main">
          <Outlet />
        </main>
      </div>

      <nav className="mobile-nav" aria-label="Mobile navigation">
        <NavLink to="/" end>
          <LayoutDashboard size={21} aria-hidden="true" />
          <span>Overview</span>
        </NavLink>
        <NavLink to="/inventory">
          <PackageSearch size={21} aria-hidden="true" />
          <span>Inventory</span>
        </NavLink>
        {canUseRequests && (
          <NavLink to="/requests">
            <ClipboardList size={21} aria-hidden="true" />
            <span>Requests</span>
          </NavLink>
        )}
        {canFulfill && (
          <NavLink to="/fulfillment">
            <ListChecks size={21} aria-hidden="true" />
            <span>Fulfill</span>
          </NavLink>
        )}
        {canWithdraw && (
          <NavLink to="/general-use">
            <PackageMinus size={21} aria-hidden="true" />
            <span>Take</span>
          </NavLink>
        )}
        {canManage && (
          <NavLink className="mobile-operations-link" to="/operations">
            <PanelsTopLeft size={21} aria-hidden="true" />
            <span>Ops</span>
          </NavLink>
        )}
      </nav>
    </div>
  )
}
