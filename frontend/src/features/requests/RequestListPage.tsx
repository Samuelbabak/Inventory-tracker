import { ArrowRight, ClipboardList, Plus, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../../api/client'
import type { MaterialRequest, RequestState } from '../../api/types'
import { useAuth } from '../../app/auth'
import { formatRequestDate, formatRequestState, openRequestStates } from './requestUi'

interface RequestResult {
  requests: MaterialRequest[]
  error: string
}

type RequestFilter = 'open' | 'completed' | 'all'

export function RequestListPage() {
  const { user } = useAuth()
  const [result, setResult] = useState<RequestResult | null>(null)
  const [filter, setFilter] = useState<RequestFilter>('open')
  const [query, setQuery] = useState('')
  const canCreate = user?.roles.some((role) => ['foreman', 'warehouse_worker', 'inventory_manager'].includes(role))

  useEffect(() => {
    let active = true
    api
      .listRequests(false)
      .then((requests) => {
        if (active) setResult({ requests, error: '' })
      })
      .catch((error_: unknown) => {
        if (active) {
          setResult({
            requests: [],
            error: error_ instanceof ApiError ? error_.message : 'Requests could not be loaded',
          })
        }
      })
    return () => {
      active = false
    }
  }, [])

  const normalizedQuery = query.trim().toLocaleLowerCase()
  const visibleRequests = (result?.requests ?? []).filter((request) => {
    const matchesFilter =
      filter === 'all' ||
      (filter === 'open' && openRequestStates.has(request.state)) ||
      (filter === 'completed' && ['completed', 'cancelled'].includes(request.state))
    const matchesQuery =
      !normalizedQuery ||
      [request.request_number, request.recipient_name, request.job_number ?? '']
        .join(' ')
        .toLocaleLowerCase()
        .includes(normalizedQuery)
    return matchesFilter && matchesQuery
  })

  return (
    <div className="page requests-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">Material flow / Requests</p>
          <h1>{user?.roles.includes('foreman') ? 'My material requests' : 'Material requests'}</h1>
          <p>Track submitted demand, allocations, and fulfillment status.</p>
        </div>
        {canCreate && (
          <Link className="button primary" to="/requests/new">
            <Plus size={18} aria-hidden="true" />
            New request
          </Link>
        )}
      </header>

      {result?.error && <div className="inline-alert error" role="alert">{result.error}</div>}

      <div className="request-toolbar">
        <div className="segmented-control" aria-label="Filter requests">
          {(['open', 'completed', 'all'] as const).map((option) => (
            <button
              type="button"
              className={filter === option ? 'active' : ''}
              aria-pressed={filter === option}
              onClick={() => setFilter(option)}
              key={option}
            >
              {option}
            </button>
          ))}
        </div>
        <label className="compact-search">
          <span className="sr-only">Search requests</span>
          <Search size={18} aria-hidden="true" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Request, recipient, job" />
        </label>
      </div>

      <section className="request-board" aria-label="Request results">
        <div className="request-board-header">
          <span>{result ? `${visibleRequests.length} requests` : 'Loading requests...'}</span>
          <span>Most recent first</span>
        </div>
        {result && visibleRequests.length === 0 && !result.error && (
          <div className="empty-state">
            <ClipboardList size={32} aria-hidden="true" />
            <h2>No requests in this view</h2>
            <p>Change the filter or start a material request.</p>
          </div>
        )}
        {visibleRequests.map((request) => {
          const units = [...new Set(request.lines.map((line) => line.uom))].join(', ')
          return (
            <Link className="request-card" to={`/requests/${request.id}`} key={request.id}>
              <span className={`priority-marker ${request.priority}`} aria-label={`${request.priority} priority`} />
              <span className="request-main">
                <span><strong>{request.request_number}</strong><span className={`status-badge ${request.state}`}>{formatRequestState(request.state as RequestState)}</span></span>
                <small>{request.recipient_name} / {request.lines.length} {request.lines.length === 1 ? 'line' : 'lines'}{units ? ` / ${units}` : ''}</small>
              </span>
              <span className="request-context">
                <strong>{request.job_number ?? 'Local stock'}</strong>
                <small>{request.claimed_by_name ? `Claimed by ${request.claimed_by_name}` : formatRequestDate(request.created_at)}</small>
              </span>
              <ArrowRight size={19} aria-hidden="true" />
            </Link>
          )
        })}
      </section>
    </div>
  )
}
