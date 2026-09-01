import { AlertTriangle, MapPin, PackageOpen, Search, X } from 'lucide-react'
import { useDeferredValue, useEffect, useState, type SyntheticEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../../api/client'
import type { InventoryItem } from '../../api/types'
import { useAuth } from '../../app/auth'
import { ManagerInventoryControls } from './ManagerInventoryControls'

interface InventoryResult {
  query: string | null
  items: InventoryItem[]
  error: string
}

function quantity(value: string) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 }).format(Number(value))
}

export function InventoryPage() {
  const { user } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState(searchParams.get('search') ?? '')
  const deferredQuery = useDeferredValue(query.trim())
  const [result, setResult] = useState<InventoryResult>({ query: null, items: [], error: '' })
  const [selectedId, setSelectedId] = useState<string | null>(searchParams.get('item'))
  const [refreshKey, setRefreshKey] = useState(0)
  const canManageInventory = user?.roles.includes('inventory_manager') ?? false
  const loading = result.query !== deferredQuery
  const items = result.items
  const error = result.query === deferredQuery ? result.error : ''
  const selectedItem = items.find((item) => item.id === selectedId) ?? null
  const itemNoun = items.length === 1 ? 'item' : 'items'
  const resultsLabel = loading ? 'Searching...' : `${items.length} ${itemNoun}`

  useEffect(() => {
    let active = true
    api
      .listInventory(deferredQuery)
      .then((inventory) => {
        if (active) setResult({ query: deferredQuery, items: inventory, error: '' })
      })
      .catch((error_: unknown) => {
        if (active) {
          setResult({
            query: deferredQuery,
            items: [],
            error: error_ instanceof ApiError ? error_.message : 'Inventory could not be loaded',
          })
        }
      })
    return () => {
      active = false
    }
  }, [deferredQuery, refreshKey])

  function selectItem(item: InventoryItem) {
    setSelectedId(item.id)
    setSearchParams({ item: item.id }, { replace: true })
  }

  function closeDetail() {
    setSelectedId(null)
    setSearchParams({}, { replace: true })
  }

  function clearSearch(event: SyntheticEvent<HTMLButtonElement>) {
    event.currentTarget.blur()
    setQuery('')
  }

  return (
    <div className="page inventory-page">
      <header className="page-heading inventory-heading">
        <div>
          <p className="eyebrow">Catalog / Stock positions</p>
          <h1>Find material</h1>
          <p>Search by item number, description, or warehouse location.</p>
        </div>
        <label className="search-field">
          <span className="sr-only">Search inventory</span>
          <Search size={20} aria-hidden="true" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Wire, breaker, WH1-A03..." />
          {query && (
            <button type="button" className="clear-button" onClick={clearSearch} title="Clear search">
              <X size={18} aria-hidden="true" />
              <span className="sr-only">Clear search</span>
            </button>
          )}
        </label>
      </header>

      {error && <div className="inline-alert error" role="alert">{error}</div>}

      <div className={`inventory-layout ${selectedItem ? 'detail-open' : ''}`}>
        <section className="inventory-results" aria-label="Inventory results">
          <div className="results-heading">
            <span>{resultsLabel}</span>
            <span>Live warehouse balance</span>
          </div>
          <ul className="inventory-table">
            {!loading && !error && items.length === 0 && (
              <li className="empty-state">
                <PackageOpen size={32} aria-hidden="true" />
                <h2>No matching material</h2>
                <p>Try an item number, description, aisle, or bay.</p>
              </li>
            )}
            {items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={`inventory-row ${selectedId === item.id ? 'selected' : ''}`}
                  onClick={() => selectItem(item)}
                >
                  <span className="item-identity"><strong>{item.sku}</strong><small>{item.description}</small></span>
                  <span className="item-location"><MapPin size={16} aria-hidden="true" />{item.locations[0]?.location_code ?? 'Unlocated'}</span>
                  <span className="quantity-stack"><strong>{quantity(item.on_hand)}</strong><small>on hand</small></span>
                  <span className="quantity-stack reserved"><strong>-{quantity(item.reserved_demand)}</strong><small>reserved</small></span>
                  <span className={`quantity-stack ${Number(item.shortage_qty) > 0 ? 'short' : 'free'}`}>
                    <strong>{quantity(Number(item.shortage_qty) > 0 ? item.shortage_qty : item.free_to_promise)}</strong>
                    <small>{Number(item.shortage_qty) > 0 ? 'short' : 'uncommitted'}</small>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        {selectedItem && (
          <aside className="item-detail" aria-label={`${selectedItem.sku} details`}>
            <div className="detail-topbar">
              <span className={`path-badge ${selectedItem.inventory_path}`}>
                {selectedItem.inventory_path === 'spectrum_managed' ? 'Spectrum managed' : 'Local general use'}
              </span>
              <button type="button" className="icon-button" onClick={closeDetail} title="Close item details">
                <X size={20} aria-hidden="true" />
                <span className="sr-only">Close item details</span>
              </button>
            </div>
            <p className="eyebrow">{selectedItem.uom}</p>
            <h2>{selectedItem.sku}</h2>
            <p className="detail-description">{selectedItem.description}</p>

            {Number(selectedItem.shortage_qty) > 0 && (
              <div className="inline-alert warning">
                <AlertTriangle size={19} aria-hidden="true" />
                <span><strong>{quantity(selectedItem.shortage_qty)} {selectedItem.uom} short</strong>Outstanding demand exceeds current coverage.</span>
              </div>
            )}

            <dl className="quantity-ledger">
              <div><dt>Usable on hand</dt><dd>{quantity(selectedItem.on_hand)}</dd></div>
              <div><dt>Reserved demand</dt><dd>-{quantity(selectedItem.reserved_demand)}</dd></div>
              <div><dt>Allocated</dt><dd>{quantity(selectedItem.allocated_qty)}</dd></div>
              <div className="ledger-total"><dt>Free to promise</dt><dd>{quantity(selectedItem.free_to_promise)}</dd></div>
            </dl>

            <section className="location-section">
              <div className="section-heading"><div><p className="eyebrow">Pick path</p><h3>Stock locations</h3></div></div>
              {selectedItem.locations.length === 0 && <p className="empty-copy">No warehouse position is assigned.</p>}
              {selectedItem.locations.map((location) => (
                <div className="location-row" key={location.stock_position_id}>
                  <MapPin size={18} aria-hidden="true" />
                  <span><strong>{location.location_code}</strong><small>Pick sequence {location.pick_sequence}</small></span>
                  <span><strong>{quantity(location.on_hand)}</strong><small>{selectedItem.uom}</small></span>
                </div>
              ))}
            </section>
            {canManageInventory && (
              <ManagerInventoryControls
                item={selectedItem}
                onChanged={() => setRefreshKey((current) => current + 1)}
              />
            )}
          </aside>
        )}
      </div>
    </div>
  )
}
