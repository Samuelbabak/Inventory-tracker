import { Grid2X2, MapPin, Plus, Save, X } from 'lucide-react'
import { useEffect, useState, type SyntheticEvent } from 'react'
import { api, ApiError } from '../../api/client'
import type { Location } from '../../api/types'

interface LocationDraft {
  code: string
  zone: string
  aisle: string
  bay: string
  shelf: string
  position: string
  pickSequence: string
  isStaging: boolean
  gridRow: string
  gridColumn: string
  reason: string
}

const emptyDraft: LocationDraft = {
  code: '',
  zone: '',
  aisle: '',
  bay: '',
  shelf: '',
  position: '',
  pickSequence: '0',
  isStaging: false,
  gridRow: '',
  gridColumn: '',
  reason: '',
}

function draftFromLocation(location: Location): LocationDraft {
  return {
    code: location.code,
    zone: location.zone,
    aisle: location.aisle,
    bay: location.bay,
    shelf: location.shelf,
    position: location.position,
    pickSequence: String(location.pick_sequence),
    isStaging: location.is_staging,
    gridRow: location.grid_row === null ? '' : String(location.grid_row),
    gridColumn: location.grid_column === null ? '' : String(location.grid_column),
    reason: '',
  }
}

export function LayoutEditor() {
  const [locations, setLocations] = useState<Location[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [draft, setDraft] = useState<LocationDraft>(emptyDraft)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    api.listLocations()
      .then((records) => {
        if (active) setLocations(records)
      })
      .catch((error_: unknown) => {
        if (active) setError(error_ instanceof ApiError ? error_.message : 'Warehouse layout is unavailable')
      })
    return () => {
      active = false
    }
  }, [])

  function selectLocation(location: Location) {
    setSelectedId(location.id)
    setDraft(draftFromLocation(location))
  }

  function startNew() {
    setSelectedId(null)
    setDraft(emptyDraft)
  }

  async function save(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    const payload = {
      code: draft.code.trim(),
      zone: draft.zone.trim(),
      aisle: draft.aisle.trim(),
      bay: draft.bay.trim(),
      shelf: draft.shelf.trim(),
      position: draft.position.trim(),
      pick_sequence: Number(draft.pickSequence),
      is_staging: draft.isStaging,
      grid_row: draft.gridRow === '' ? null : Number(draft.gridRow),
      grid_column: draft.gridColumn === '' ? null : Number(draft.gridColumn),
    }
    try {
      const saved = selectedId
        ? await api.updateLocation(selectedId, { ...payload, reason: draft.reason.trim() })
        : await api.createLocation(payload)
      setLocations((current) => {
        const next = current.some((location) => location.id === saved.id)
          ? current.map((location) => location.id === saved.id ? saved : location)
          : [...current, saved]
        return next.sort((left, right) => left.pick_sequence - right.pick_sequence)
      })
      setSelectedId(saved.id)
      setDraft(draftFromLocation(saved))
    } catch (error_) {
      setError(error_ instanceof ApiError ? error_.message : 'Location could not be saved')
    } finally {
      setBusy(false)
    }
  }

  const mapped = locations.filter((location) => location.grid_row !== null && location.grid_column !== null)
  const rowCount = Math.max(1, ...mapped.map((location) => (location.grid_row ?? 0) + 1))
  const columnCount = Math.max(1, ...mapped.map((location) => (location.grid_column ?? 0) + 1))

  return (
    <section className="operations-panel layout-editor" role="tabpanel">
      <div className="section-heading">
        <div><p className="eyebrow">Stable IDs / Configurable coordinates</p><h2>Warehouse layout</h2></div>
        <button className="button secondary" type="button" onClick={startNew}><Plus size={18} aria-hidden="true" />New location</button>
      </div>
      {error && <div className="inline-alert error" role="alert">{error}</div>}
      <div className="layout-editor-grid">
        <form className="location-form" onSubmit={(event) => void save(event)}>
          <div className="form-heading"><MapPin size={21} aria-hidden="true" /><span><strong>{selectedId ? 'Edit location' : 'New location'}</strong><small>{selectedId ? selectedId.slice(0, 8) : 'A stable ID is assigned on save'}</small></span></div>
          <label className="location-code-field"><span>Readable code</span><input value={draft.code} onChange={(event) => setDraft((current) => ({ ...current, code: event.target.value }))} maxLength={80} required /></label>
          <label><span>Zone</span><input value={draft.zone} onChange={(event) => setDraft((current) => ({ ...current, zone: event.target.value }))} required /></label>
          <label><span>Aisle</span><input value={draft.aisle} onChange={(event) => setDraft((current) => ({ ...current, aisle: event.target.value }))} required /></label>
          <label><span>Bay</span><input value={draft.bay} onChange={(event) => setDraft((current) => ({ ...current, bay: event.target.value }))} required /></label>
          <label><span>Shelf</span><input value={draft.shelf} onChange={(event) => setDraft((current) => ({ ...current, shelf: event.target.value }))} required /></label>
          <label><span>Position</span><input value={draft.position} onChange={(event) => setDraft((current) => ({ ...current, position: event.target.value }))} required /></label>
          <label><span>Pick sequence</span><input type="number" min="0" value={draft.pickSequence} onChange={(event) => setDraft((current) => ({ ...current, pickSequence: event.target.value }))} required /></label>
          <label><span>Grid row</span><input type="number" min="0" max="999" value={draft.gridRow} onChange={(event) => setDraft((current) => ({ ...current, gridRow: event.target.value }))} /></label>
          <label><span>Grid column</span><input type="number" min="0" max="999" value={draft.gridColumn} onChange={(event) => setDraft((current) => ({ ...current, gridColumn: event.target.value }))} /></label>
          <label className="checkbox-field"><input type="checkbox" checked={draft.isStaging} onChange={(event) => setDraft((current) => ({ ...current, isStaging: event.target.checked }))} /><span>Staging location</span></label>
          {selectedId && <label className="location-reason"><span>Change reason</span><input value={draft.reason} onChange={(event) => setDraft((current) => ({ ...current, reason: event.target.value }))} minLength={3} maxLength={500} required /></label>}
          <button className="button primary" type="submit" disabled={busy}><Save size={18} aria-hidden="true" />{busy ? 'Saving...' : 'Save location'}</button>
          {selectedId && <button className="icon-button" type="button" title="Close editor" onClick={startNew}><X size={18} aria-hidden="true" /><span className="sr-only">Close editor</span></button>}
        </form>

        <div className="layout-preview">
          <div className="form-heading"><Grid2X2 size={21} aria-hidden="true" /><span><strong>Schematic grid</strong><small>{mapped.length} of {locations.length} locations placed</small></span></div>
          <div className="warehouse-map editable-map" style={{ gridTemplateColumns: `repeat(${columnCount}, minmax(112px, 1fr))`, gridTemplateRows: `repeat(${rowCount}, minmax(88px, auto))` }}>
            {mapped.map((location) => (
              <button type="button" className={`map-cell ${location.is_staging ? 'staging' : ''} ${selectedId === location.id ? 'selected' : ''}`} style={{ gridRow: (location.grid_row ?? 0) + 1, gridColumn: (location.grid_column ?? 0) + 1 }} onClick={() => selectLocation(location)} key={location.id}>
                <span>{location.code}</span><strong>{location.zone} / {location.aisle}</strong><small>Pick {location.pick_sequence}</small>
              </button>
            ))}
          </div>
          <div className="unmapped-locations">
            {locations.filter((location) => location.grid_row === null).map((location) => <button type="button" onClick={() => selectLocation(location)} key={location.id}><MapPin size={15} aria-hidden="true" />{location.code}</button>)}
          </div>
        </div>
      </div>
    </section>
  )
}