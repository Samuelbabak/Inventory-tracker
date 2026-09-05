import type {
  AdminUser,
  AuditEvent,
  ApprovedAlternate,
  CatalogItem,
  CatalogSnapshot,
  CatalogUnit,
  CreateRequestPayload,
  CreatedQrToken,
  Device,
  InventoryEvent,
  InventoryItem,
  InventoryMutation,
  Location,
  LoginResponse,
  MaterialRequest,
  Notification,
  OfflineCommandInput,
  OfflineConflict,
  OfflineGrant,
  OfflineSyncResult,
  OutboxEvent,
  QrResolution,
  QrTargetType,
  QrToken,
  ReconciliationRun,
  Recipient,
  Role,
  SpectrumStatus,
  UnitConversion,
  UserContext,
} from './types'

const API_ROOT = '/api/v1'
const CSRF_STORAGE_KEY = 'haynes.csrf'

export class ApiError extends Error {
  readonly status: number
  readonly code?: string

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = init.method?.toUpperCase() ?? 'GET'
  const headers = new Headers(init.headers)
  if (init.body) headers.set('Content-Type', 'application/json')
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrfToken = localStorage.getItem(CSRF_STORAGE_KEY)
    if (csrfToken) headers.set('X-CSRF-Token', csrfToken)
  }
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    throw new ApiError(body.detail ?? 'Request failed', response.status, body.code)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  async login(username: string, password: string): Promise<UserContext> {
    const response = await request<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password, warehouse_code: 'WH1' }),
    })
    localStorage.setItem(CSRF_STORAGE_KEY, response.csrf_token)
    return response.user
  },
  me: () => request<UserContext>('/auth/me'),
  async logout(): Promise<void> {
    await request<void>('/auth/logout', { method: 'POST' })
    localStorage.removeItem(CSRF_STORAGE_KEY)
  },
  listUsers: () => request<AdminUser[]>('/users'),
  createUser: (payload: {
    username: string
    display_name: string
    password: string | null
    roles: Role[]
  }) => request<AdminUser>('/users', { method: 'POST', body: JSON.stringify(payload) }),
  updateUser: (userId: string, payload: {
    display_name: string
    is_active: boolean
    password: string | null
    roles: Role[]
    reason: string
  }) => request<AdminUser>(`/users/${userId}`, { method: 'PUT', body: JSON.stringify(payload) }),
  listInventory: (search = '') =>
    request<InventoryItem[]>(`/inventory?search=${encodeURIComponent(search)}`),
  getCatalog: () => request<CatalogSnapshot>('/catalog'),
  createCatalogUnit: (payload: { code: string; name: string; decimal_places: number }) =>
    request<CatalogUnit>('/catalog/units', { method: 'POST', body: JSON.stringify(payload) }),
  createCatalogItem: (payload: {
    sku: string
    description: string
    inventory_path: 'spectrum_managed' | 'local_general_use'
    spectrum_item_id: string | null
    uom_id: string
    reorder_point: number
  }) => request<CatalogItem>('/catalog/items', { method: 'POST', body: JSON.stringify(payload) }),
  updateCatalogItem: (itemId: string, payload: {
    description: string
    inventory_path: 'spectrum_managed' | 'local_general_use'
    spectrum_item_id: string | null
    reorder_point: number
    is_active: boolean
    reason: string
  }) => request<CatalogItem>(`/catalog/items/${itemId}`, { method: 'PUT', body: JSON.stringify(payload) }),
  saveUnitConversion: (payload: {
    item_id: string
    from_uom_id: string
    to_uom_id: string
    factor: number
    reason: string
  }) => request<UnitConversion>('/catalog/conversions', { method: 'POST', body: JSON.stringify(payload) }),
  approveAlternate: (payload: { item_id: string; alternate_item_id: string; reason: string }) =>
    request<ApprovedAlternate>('/catalog/alternates', { method: 'POST', body: JSON.stringify(payload) }),
  revokeAlternate: (alternateId: string, reason: string) =>
    request<ApprovedAlternate>(`/catalog/alternates/${alternateId}/revoke`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  listLocations: () => request<Location[]>('/locations'),
  createLocation: (payload: {
    code: string
    zone: string
    aisle: string
    bay: string
    shelf: string
    position: string
    pick_sequence: number
    is_staging: boolean
    grid_row: number | null
    grid_column: number | null
  }) => request<Location>('/locations', { method: 'POST', body: JSON.stringify(payload) }),
  updateLocation: (locationId: string, payload: {
    code: string
    zone: string
    aisle: string
    bay: string
    shelf: string
    position: string
    pick_sequence: number
    is_staging: boolean
    grid_row: number | null
    grid_column: number | null
    reason: string
  }) => request<Location>(`/locations/${locationId}`, { method: 'PUT', body: JSON.stringify(payload) }),
  listRecipients: () => request<Recipient[]>('/recipients'),
  listRequests: (mineOnly = false) =>
    request<MaterialRequest[]>(`/requests?mine_only=${mineOnly}`),
  getRequest: (requestId: string) => request<MaterialRequest>(`/requests/${requestId}`),
  createRequest: (payload: CreateRequestPayload) =>
    request<MaterialRequest>('/requests', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  submitRequest: (requestId: string) =>
    request<MaterialRequest>(`/requests/${requestId}/submit`, { method: 'POST' }),
  claimRequest: (requestId: string) =>
    request<MaterialRequest>(`/requests/${requestId}/claim`, { method: 'POST' }),
  claimNextRequest: () =>
    request<MaterialRequest | null>('/requests/queue/claim-next', { method: 'POST' }),
  recordPick: (
    requestId: string,
    payload: {
      allocation_id: string
      quantity: number
      scanned_location_code: string
      scanned_sku: string
      shortage_reason?: string
    },
  ) =>
    request<MaterialRequest>(`/requests/${requestId}/picks`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listSubstituteCandidates: (requestId: string, allocationId: string) =>
    request<SubstituteCandidateResponse[]>(`/requests/${requestId}/allocations/${allocationId}/substitutes`),
  substituteAllocation: (
    requestId: string,
    payload: SubstituteAllocationRequest,
  ) =>
    request<MaterialRequest>(`/requests/${requestId}/substitutions`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  reallocate: (payload: ReallocateStockRequest) =>
    request<ReallocationResponse>('/requests/reallocations', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  handoffRequest: (requestId: string) =>
    request<MaterialRequest>(`/requests/${requestId}/handoff`, { method: 'POST' }),
  cancelRequest: (requestId: string, reason: string) =>
    request<MaterialRequest>(`/requests/${requestId}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  withdrawGeneralUse: (payload: {
    stock_position_id: string
    recipient_id: string
    quantity: number
    note?: string
  }) =>
    request<InventoryMutation>('/inventory/general-use-withdrawals', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  receiveInventory: (payload: {
    stock_position_id: string
    quantity: number
    reason: string
  }) =>
    request<InventoryMutation>('/inventory/receipts', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  returnInventory: (payload: {
    stock_position_id: string
    quantity: number
    condition: 'usable' | 'quarantined'
    reason: string
  }) =>
    request<InventoryMutation>('/inventory/returns', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  moveInventory: (payload: {
    source_stock_position_id: string
    destination_stock_position_id: string
    quantity: number
    reason: string
  }) =>
    request<InventoryMutation>('/inventory/moves', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  adjustInventory: (payload: {
    stock_position_id: string
    counted_on_hand: number
    reason: string
  }) =>
    request<InventoryMutation>('/inventory/adjustments', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  quarantineInventory: (payload: {
    stock_position_id: string
    quantity: number
    reason: string
  }) =>
    request<InventoryMutation>('/inventory/quarantines', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  releaseInventory: (payload: {
    stock_position_id: string
    quantity: number
    reason: string
  }) =>
    request<InventoryMutation>('/inventory/releases', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listNotifications: () => request<Notification[]>('/notifications'),
  markNotificationRead: (notificationId: string) =>
    request<void>(`/notifications/${notificationId}/read`, { method: 'POST' }),
  listInventoryEvents: () => request<InventoryEvent[]>('/inventory/events'),
  listAuditEvents: () => request<AuditEvent[]>('/audit'),
  spectrumStatus: () => request<SpectrumStatus>('/integrations/spectrum/status'),
  listSpectrumEvents: () => request<OutboxEvent[]>('/integrations/spectrum/events'),
  retrySpectrumEvent: (eventId: string) =>
    request<OutboxEvent>(`/integrations/spectrum/events/${eventId}/retry`, { method: 'POST' }),
  listReconciliations: () => request<ReconciliationRun[]>('/integrations/spectrum/reconciliations'),
  runReconciliation: () =>
    request<ReconciliationRun>('/integrations/spectrum/reconciliations', { method: 'POST' }),
  enrollDevice: (deviceIdentifier: string, displayName: string) =>
    request<Device>('/devices/enroll', {
      method: 'POST',
      body: JSON.stringify({ device_identifier: deviceIdentifier, display_name: displayName }),
    }),
  listDevices: () => request<Device[]>('/devices'),
  revokeDevice: (deviceId: string, reason: string) =>
    request<Device>(`/devices/${deviceId}/revoke`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  listQrTokens: () => request<QrToken[]>('/qr'),
  createQrToken: (targetType: QrTargetType, targetId: string, expiresInHours: number | null) =>
    request<CreatedQrToken>('/qr', {
      method: 'POST',
      body: JSON.stringify({ target_type: targetType, target_id: targetId, expires_in_hours: expiresInHours }),
    }),
  resolveQrToken: (token: string) =>
    request<QrResolution>('/qr/resolve', {
      method: 'POST',
      body: JSON.stringify({ token }),
    }),
  revokeQrToken: (tokenId: string, reason: string) =>
    request<QrToken>(`/qr/${tokenId}/revoke`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  createOfflineGrant: (requestId: string, deviceId: string) =>
    request<OfflineGrant>('/offline/grants', {
      method: 'POST',
      body: JSON.stringify({ request_id: requestId, device_id: deviceId }),
    }),
  syncOfflineCommands: (grantId: string, deviceId: string, commands: OfflineCommandInput[]) =>
    request<OfflineSyncResult>('/offline/sync', {
      method: 'POST',
      body: JSON.stringify({ grant_id: grantId, device_id: deviceId, commands }),
    }),
  listOfflineConflicts: () => request<OfflineConflict[]>('/offline/conflicts'),
  rejectOfflineConflict: (commandId: string, reason: string) =>
    request<OfflineConflict>(`/offline/conflicts/${commandId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
}
