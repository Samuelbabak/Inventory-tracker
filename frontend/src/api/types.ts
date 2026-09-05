export type Role =
  | 'employee'
  | 'foreman'
  | 'warehouse_worker'
  | 'inventory_manager'
  | 'system_administrator'

export type InventoryPath = 'spectrum_managed' | 'local_general_use'
export type RequestPriority = 'normal' | 'urgent'
export type RequestState =
  | 'draft'
  | 'submitted'
  | 'claimed'
  | 'in_progress'
  | 'ready'
  | 'partially_fulfilled'
  | 'completed'
  | 'on_hold'
  | 'cancelled'

export interface UserContext {
  id: string
  warehouse_id: string
  warehouse_code: string
  username: string
  display_name: string
  roles: Role[]
}

export interface LoginResponse {
  user: UserContext
  csrf_token: string
}

export interface AdminUser {
  id: string
  username: string
  display_name: string
  is_active: boolean
  roles: Role[]
  created_at: string
}

export interface StockLocation {
  stock_position_id: string
  location_id: string
  location_code: string
  pick_sequence: number
  on_hand: string
  quarantined_qty: string
}

export interface InventoryItem {
  id: string
  sku: string
  description: string
  inventory_path: InventoryPath
  uom: string
  on_hand: string
  quarantined_qty: string
  reserved_demand: string
  allocated_qty: string
  free_to_promise: string
  shortage_qty: string
  reorder_point: string
  locations: StockLocation[]
}

export interface CatalogUnit {
  id: string
  code: string
  name: string
  decimal_places: number
}

export interface CatalogItem {
  id: string
  sku: string
  description: string
  inventory_path: InventoryPath
  spectrum_item_id: string | null
  uom_id: string
  uom: string
  reorder_point: string
  is_active: boolean
}

export interface UnitConversion {
  id: string
  item_id: string
  from_uom_id: string
  from_uom: string
  to_uom_id: string
  to_uom: string
  factor: string
}

export interface SubstituteCandidateResponse {
  stock_position_id: string
  item_id: string
  sku: string
  description: string
  location_code: string
  available_qty: string
  uom: string
}

export interface SubstituteAllocationRequest {
  allocation_id: string
  alternate_stock_position_id: string
  quantity: number
  reason: string
}

export interface ReallocateStockRequest {
  source_allocation_id: string
  target_request_id: string
  quantity: number
  reason: string
}

export interface ReallocationResponse {
  status: 'success'
  message: string
}

export interface ApprovedAlternate {
  id: string
  item_id: string
  item_sku: string
  alternate_item_id: string
  alternate_sku: string
}

export interface CatalogSnapshot {
  items: CatalogItem[]
  units: CatalogUnit[]
  conversions: UnitConversion[]
  alternates: ApprovedAlternate[]
}

export interface Recipient {
  id: string
  employee_number: string
  display_name: string
}

export interface Location {
  id: string
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
}

export interface Allocation {
  id: string
  stock_position_id: string
  fulfillment_item_id: string
  fulfillment_sku: string
  fulfillment_description: string
  fulfillment_uom: string
  is_substitute: boolean
  location_code: string
  quantity: string
  picked_qty: string
  issued_qty: string
  released_qty: string
  pick_confirmed: boolean
}

export interface RequestLine {
  id: string
  item_id: string
  sku: string
  description: string
  inventory_path: InventoryPath
  uom: string
  requested_qty: string
  allocated_qty: string
  picked_qty: string
  issued_qty: string
  cancelled_qty: string
  backordered_qty: string
  allocations: Allocation[]
}

export interface MaterialRequest {
  id: string
  request_number: string
  state: RequestState
  priority: RequestPriority
  urgent_reason: string | null
  job_number: string | null
  cost_code: string | null
  creator_name: string
  recipient_name: string
  claimed_by_user_id: string | null
  claimed_by_name: string | null
  version: number
  created_at: string
  updated_at: string
  lines: RequestLine[]
}

export interface CreateRequestPayload {
  recipient_id: string
  priority: RequestPriority
  urgent_reason?: string
  job_number?: string
  cost_code?: string
  lines: Array<{ item_id: string; quantity: number }>
  submit: boolean
}

export interface Notification {
  id: string
  title: string
  message: string
  entity_type: string | null
  entity_id: string | null
  is_read: boolean
  created_at: string
}

export interface InventoryEvent {
  id: string
  event_type: string
  item_id: string
  sku: string
  location_code: string | null
  destination_location_code: string | null
  quantity: string
  uom: string
  reason: string | null
  actor_name: string
  created_at: string
}

export interface InventoryMutation {
  event_id: string
  stock_position_id: string
  event_type: string
  on_hand: string
}

export interface AuditEvent {
  id: string
  actor_name: string
  action: string
  entity_type: string
  entity_id: string
  reason: string | null
  changes: Record<string, unknown>
  created_at: string
}

export interface SpectrumStatus {
  health: Record<string, string>
  capabilities: Record<string, boolean>
  counts: Record<string, number>
}

export interface OutboxEvent {
  id: string
  event_type: string
  status: 'pending' | 'processing' | 'succeeded' | 'failed' | 'requires_review'
  attempt_count: number
  last_error: string | null
  created_at: string
  processed_at: string | null
}

export interface ReconciliationDifference {
  event_id: string
  business_reference: string
  request_number: string
  sku: string
  kind: 'delivery_state' | 'missing_remote' | 'reference_mismatch'
  detail: string
}

export interface ReconciliationRun {
  id: string
  status: string
  checked_count: number
  matched_count: number
  difference_count: number
  differences: ReconciliationDifference[]
  started_at: string
  finished_at: string | null
  error: string | null
}

export interface Device {
  id: string
  device_identifier: string
  display_name: string
  enrolled_by_user_id: string | null
  last_seen_at: string
  revoked_at: string | null
}

export type QrTargetType = 'item' | 'location' | 'request'

export interface QrToken {
  id: string
  target_type: QrTargetType
  target_id: string
  target_label: string
  target_route: string
  expires_at: string | null
  revoked_at: string | null
  last_resolved_at: string | null
  created_at: string
}

export interface CreatedQrToken extends QrToken {
  token: string
  scan_path: string
}

export interface QrResolution {
  target_type: QrTargetType
  target_id: string
  label: string
  route: string
}

export interface OfflineGrant {
  id: string
  request_id: string
  device_id: string
  request_version: number
  expires_at: string
  snapshot: MaterialRequest
}

export type OfflineCommandType = 'record_pick' | 'handoff'

export interface OfflineCommandInput {
  client_command_id: string
  sequence: number
  command_type: OfflineCommandType
  payload: Record<string, unknown>
}

export interface OfflineCommandResult {
  client_command_id: string
  sequence: number
  status: 'pending' | 'applied' | 'conflict' | 'rejected'
  result: Record<string, unknown> | null
}

export interface OfflineSyncResult {
  grant_id: string
  request_version: number
  commands: OfflineCommandResult[]
}

export interface OfflineConflict {
  id: string
  grant_id: string
  request_id: string
  request_number: string
  actor_user_id: string
  actor_name: string
  device_id: string
  sequence: number
  command_type: string
  payload: Record<string, unknown>
  status: 'conflict' | 'rejected'
  result: Record<string, unknown> | null
  created_at: string
}
