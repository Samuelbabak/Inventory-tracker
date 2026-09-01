import type { RequestState } from '../../api/types'

export const openRequestStates = new Set<RequestState>([
  'draft',
  'submitted',
  'claimed',
  'in_progress',
  'ready',
  'partially_fulfilled',
  'on_hold',
])

export function formatRequestState(state: RequestState) {
  return state.replaceAll('_', ' ')
}

export function formatRequestDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value))
}

export function formatRequestQuantity(value: string) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 }).format(Number(value))
}
