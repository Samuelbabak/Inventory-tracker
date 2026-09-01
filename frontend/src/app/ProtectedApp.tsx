import { Navigate, Route, Routes } from 'react-router-dom'
import { DashboardPage } from '../features/dashboard/DashboardPage'
import { FulfillmentQueuePage } from '../features/fulfillment/FulfillmentQueuePage'
import { PickRequestPage } from '../features/fulfillment/PickRequestPage'
import { GeneralUsePage } from '../features/general-use/GeneralUsePage'
import { InventoryPage } from '../features/inventory/InventoryPage'
import { NotificationsPage } from '../features/notifications/NotificationsPage'
import { OfflineReviewPage } from '../features/offline-sync/OfflineReviewPage'
import { OperationsPage } from '../features/operations/OperationsPage'
import { ScanPage } from '../features/qr/ScanPage'
import { RequestBuilderPage } from '../features/requests/RequestBuilderPage'
import { RequestDetailPage } from '../features/requests/RequestDetailPage'
import { RequestListPage } from '../features/requests/RequestListPage'
import { AppShell } from './AppShell'
import { useAuth } from './auth'

export function ProtectedApp() {
  const { user } = useAuth()
  const canFulfill = user?.roles.some((role) => ['warehouse_worker', 'inventory_manager'].includes(role))
  const canWithdraw = user?.roles.some((role) => ['employee', 'warehouse_worker', 'inventory_manager'].includes(role))
  const canManage = user?.roles.some((role) => ['inventory_manager', 'system_administrator'].includes(role))

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<DashboardPage />} />
        <Route path="inventory" element={<InventoryPage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="offline" element={<OfflineReviewPage />} />
        <Route path="scan" element={<ScanPage />} />
        <Route path="requests" element={<RequestListPage />} />
        <Route path="requests/new" element={<RequestBuilderPage />} />
        <Route path="requests/:requestId" element={<RequestDetailPage />} />
        {canFulfill && <Route path="fulfillment" element={<FulfillmentQueuePage />} />}
        {canFulfill && <Route path="fulfillment/:requestId" element={<PickRequestPage />} />}
        {canWithdraw && <Route path="general-use" element={<GeneralUsePage />} />}
        {canManage && <Route path="operations" element={<OperationsPage />} />}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
