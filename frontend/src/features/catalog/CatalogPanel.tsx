import { ArrowRight, BookOpenText, Pencil, Plus, Save, Trash2, X } from 'lucide-react'
import { useEffect, useState, type SyntheticEvent } from 'react'
import { api, ApiError } from '../../api/client'
import type { CatalogItem, CatalogSnapshot, InventoryPath } from '../../api/types'

type CatalogView = 'items' | 'units' | 'alternates'

const emptyItem = {
  sku: '',
  description: '',
  inventoryPath: 'local_general_use' as InventoryPath,
  spectrumItemId: '',
  uomId: '',
  reorderPoint: '0',
}

export function CatalogPanel() {
  const [catalog, setCatalog] = useState<CatalogSnapshot | null>(null)
  const [view, setView] = useState<CatalogView>('items')
  const [itemDraft, setItemDraft] = useState(emptyItem)
  const [editing, setEditing] = useState<CatalogItem | null>(null)
  const [editReason, setEditReason] = useState('')
  const [unitDraft, setUnitDraft] = useState({ code: '', name: '', decimalPlaces: '0' })
  const [conversion, setConversion] = useState({ itemId: '', fromUomId: '', toUomId: '', factor: '', reason: '' })
  const [alternate, setAlternate] = useState({ itemId: '', alternateItemId: '', reason: '' })
  const [revokingId, setRevokingId] = useState<string | null>(null)
  const [revokeReason, setRevokeReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    api.getCatalog()
      .then((snapshot) => {
        if (active) setCatalog(snapshot)
      })
      .catch((error_: unknown) => {
        if (active) setError(error_ instanceof ApiError ? error_.message : 'Catalog is unavailable')
      })
    return () => {
      active = false
    }
  }, [])

  async function createItem(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const item = await api.createCatalogItem({
        sku: itemDraft.sku.trim(),
        description: itemDraft.description.trim(),
        inventory_path: itemDraft.inventoryPath,
        spectrum_item_id: itemDraft.inventoryPath === 'spectrum_managed' ? itemDraft.spectrumItemId.trim() : null,
        uom_id: itemDraft.uomId,
        reorder_point: Number(itemDraft.reorderPoint),
      })
      setCatalog((current) => current && ({ ...current, items: [...current.items, item].sort((left, right) => left.sku.localeCompare(right.sku)) }))
      setItemDraft(emptyItem)
    } catch (error_) {
      setError(error_ instanceof ApiError ? error_.message : 'Catalog item could not be created')
    } finally {
      setBusy(false)
    }
  }

  async function updateItem(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editing) return
    setBusy(true)
    setError('')
    try {
      const item = await api.updateCatalogItem(editing.id, {
        description: editing.description.trim(),
        inventory_path: editing.inventory_path,
        spectrum_item_id: editing.inventory_path === 'spectrum_managed' ? editing.spectrum_item_id?.trim() || null : null,
        reorder_point: Number(editing.reorder_point),
        is_active: editing.is_active,
        reason: editReason.trim(),
      })
      setCatalog((current) => current && ({ ...current, items: current.items.map((record) => record.id === item.id ? item : record) }))
      setEditing(null)
      setEditReason('')
    } catch (error_) {
      setError(error_ instanceof ApiError ? error_.message : 'Catalog item could not be updated')
    } finally {
      setBusy(false)
    }
  }

  async function createUnit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const unit = await api.createCatalogUnit({
        code: unitDraft.code.trim(),
        name: unitDraft.name.trim(),
        decimal_places: Number(unitDraft.decimalPlaces),
      })
      setCatalog((current) => current && ({ ...current, units: [...current.units, unit].sort((left, right) => left.code.localeCompare(right.code)) }))
      setUnitDraft({ code: '', name: '', decimalPlaces: '0' })
    } catch (error_) {
      setError(error_ instanceof ApiError ? error_.message : 'Unit of measure could not be created')
    } finally {
      setBusy(false)
    }
  }

  async function saveConversion(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const saved = await api.saveUnitConversion({
        item_id: conversion.itemId,
        from_uom_id: conversion.fromUomId,
        to_uom_id: conversion.toUomId,
        factor: Number(conversion.factor),
        reason: conversion.reason.trim(),
      })
      setCatalog((current) => current && ({
        ...current,
        conversions: current.conversions.some((record) => record.id === saved.id)
          ? current.conversions.map((record) => record.id === saved.id ? saved : record)
          : [...current.conversions, saved],
      }))
      setConversion({ itemId: '', fromUomId: '', toUomId: '', factor: '', reason: '' })
    } catch (error_) {
      setError(error_ instanceof ApiError ? error_.message : 'Unit conversion could not be saved')
    } finally {
      setBusy(false)
    }
  }

  async function approveAlternate(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const saved = await api.approveAlternate({
        item_id: alternate.itemId,
        alternate_item_id: alternate.alternateItemId,
        reason: alternate.reason.trim(),
      })
      setCatalog((current) => current && ({ ...current, alternates: [...current.alternates, saved] }))
      setAlternate({ itemId: '', alternateItemId: '', reason: '' })
    } catch (error_) {
      setError(error_ instanceof ApiError ? error_.message : 'Alternate could not be approved')
    } finally {
      setBusy(false)
    }
  }

  async function revokeAlternate(event: SyntheticEvent<HTMLFormElement>, alternateId: string) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.revokeAlternate(alternateId, revokeReason.trim())
      setCatalog((current) => current && ({ ...current, alternates: current.alternates.filter((record) => record.id !== alternateId) }))
      setRevokingId(null)
      setRevokeReason('')
    } catch (error_) {
      setError(error_ instanceof ApiError ? error_.message : 'Alternate approval could not be revoked')
    } finally {
      setBusy(false)
    }
  }

  const activeItems = catalog?.items.filter((item) => item.is_active) ?? []

  return (
    <section className="operations-panel catalog-panel" role="tabpanel">
      <div className="section-heading">
        <div><p className="eyebrow">Classification and quantity rules</p><h2>Catalog</h2></div>
        <span className="count-label">{catalog ? `${catalog.items.length} items / ${catalog.units.length} units` : 'Loading catalog...'}</span>
      </div>
      {error && <div className="inline-alert error" role="alert">{error}</div>}
      <div className="segmented-control catalog-segments" aria-label="Catalog view">
        <button type="button" className={view === 'items' ? 'active' : ''} onClick={() => setView('items')}>Items</button>
        <button type="button" className={view === 'units' ? 'active' : ''} onClick={() => setView('units')}>UOM rules</button>
        <button type="button" className={view === 'alternates' ? 'active' : ''} onClick={() => setView('alternates')}>Alternates</button>
      </div>

      {view === 'items' && (
        <div className="catalog-layout">
          <form className="catalog-form" onSubmit={(event) => void createItem(event)}>
            <div className="form-heading"><BookOpenText size={21} aria-hidden="true" /><span><strong>New item</strong><small>Assign the accounting path once.</small></span></div>
            <label><span>SKU</span><input value={itemDraft.sku} onChange={(event) => setItemDraft((current) => ({ ...current, sku: event.target.value }))} maxLength={80} required /></label>
            <label><span>Description</span><input value={itemDraft.description} onChange={(event) => setItemDraft((current) => ({ ...current, description: event.target.value }))} maxLength={240} required /></label>
            <label><span>Inventory path</span><select value={itemDraft.inventoryPath} onChange={(event) => setItemDraft((current) => ({ ...current, inventoryPath: event.target.value as InventoryPath, spectrumItemId: '' }))}><option value="local_general_use">Local general use</option><option value="spectrum_managed">Spectrum managed</option></select></label>
            {itemDraft.inventoryPath === 'spectrum_managed' && <label><span>Spectrum item ID</span><input value={itemDraft.spectrumItemId} onChange={(event) => setItemDraft((current) => ({ ...current, spectrumItemId: event.target.value }))} required /></label>}
            <label><span>Base UOM</span><select value={itemDraft.uomId} onChange={(event) => setItemDraft((current) => ({ ...current, uomId: event.target.value }))} required><option value="">Select unit</option>{catalog?.units.map((unit) => <option value={unit.id} key={unit.id}>{unit.code} / {unit.name}</option>)}</select></label>
            <label><span>Reorder point</span><input type="number" min="0" step="0.001" value={itemDraft.reorderPoint} onChange={(event) => setItemDraft((current) => ({ ...current, reorderPoint: event.target.value }))} required /></label>
            <button className="button primary" type="submit" disabled={busy}><Plus size={18} aria-hidden="true" />Add item</button>
          </form>
          <div className="catalog-register">
            {catalog?.items.map((item) => (
              <div className={`catalog-item-row ${item.is_active ? '' : 'inactive'}`} key={item.id}>
                <span><strong>{item.sku}</strong><small>{item.description}</small></span>
                <span><strong>{item.uom}</strong><small>{item.inventory_path.replaceAll('_', ' ')}</small></span>
                <button className="icon-button" type="button" title={`Edit ${item.sku}`} onClick={() => { setEditing({ ...item }); setEditReason('') }}><Pencil size={18} aria-hidden="true" /><span className="sr-only">Edit {item.sku}</span></button>
              </div>
            ))}
            {catalog?.items.length === 0 && <p className="empty-copy">No catalog items.</p>}
          </div>
        </div>
      )}

      {editing && (
        <form className="catalog-edit-form" onSubmit={(event) => void updateItem(event)}>
          <div className="form-heading"><Pencil size={20} aria-hidden="true" /><span><strong>{editing.sku}</strong><small>{editing.uom} remains the base UOM</small></span></div>
          <label><span>Description</span><input value={editing.description} onChange={(event) => setEditing((current) => current && ({ ...current, description: event.target.value }))} required /></label>
          <label><span>Inventory path</span><select value={editing.inventory_path} onChange={(event) => setEditing((current) => current && ({ ...current, inventory_path: event.target.value as InventoryPath, spectrum_item_id: null }))}><option value="local_general_use">Local general use</option><option value="spectrum_managed">Spectrum managed</option></select></label>
          {editing.inventory_path === 'spectrum_managed' && <label><span>Spectrum item ID</span><input value={editing.spectrum_item_id ?? ''} onChange={(event) => setEditing((current) => current && ({ ...current, spectrum_item_id: event.target.value }))} required /></label>}
          <label><span>Reorder point</span><input type="number" min="0" step="0.001" value={editing.reorder_point} onChange={(event) => setEditing((current) => current && ({ ...current, reorder_point: event.target.value }))} required /></label>
          <label className="checkbox-field"><input type="checkbox" checked={editing.is_active} onChange={(event) => setEditing((current) => current && ({ ...current, is_active: event.target.checked }))} /><span>Active item</span></label>
          <label className="catalog-reason"><span>Change reason</span><input value={editReason} onChange={(event) => setEditReason(event.target.value)} minLength={3} maxLength={500} required /></label>
          <button className="button primary" type="submit" disabled={busy}><Save size={18} aria-hidden="true" />Save</button>
          <button className="icon-button" type="button" title="Close editor" onClick={() => setEditing(null)}><X size={18} aria-hidden="true" /><span className="sr-only">Close editor</span></button>
        </form>
      )}

      {view === 'units' && (
        <div className="catalog-rule-grid">
          <form className="catalog-form" onSubmit={(event) => void createUnit(event)}>
            <div className="form-heading"><Plus size={21} aria-hidden="true" /><span><strong>New unit</strong><small>Fixed decimal precision.</small></span></div>
            <label><span>Code</span><input value={unitDraft.code} onChange={(event) => setUnitDraft((current) => ({ ...current, code: event.target.value }))} maxLength={16} required /></label>
            <label><span>Name</span><input value={unitDraft.name} onChange={(event) => setUnitDraft((current) => ({ ...current, name: event.target.value }))} maxLength={64} required /></label>
            <label><span>Decimal places</span><input type="number" min="0" max="3" value={unitDraft.decimalPlaces} onChange={(event) => setUnitDraft((current) => ({ ...current, decimalPlaces: event.target.value }))} required /></label>
            <button className="button primary" type="submit" disabled={busy}><Plus size={18} aria-hidden="true" />Add unit</button>
          </form>
          <form className="catalog-form conversion-form" onSubmit={(event) => void saveConversion(event)}>
            <div className="form-heading"><ArrowRight size={21} aria-hidden="true" /><span><strong>Conversion rule</strong><small>One source unit equals the factor in destination units.</small></span></div>
            <label><span>Item</span><select value={conversion.itemId} onChange={(event) => setConversion((current) => ({ ...current, itemId: event.target.value }))} required><option value="">Select item</option>{activeItems.map((item) => <option value={item.id} key={item.id}>{item.sku}</option>)}</select></label>
            <label><span>From</span><select value={conversion.fromUomId} onChange={(event) => setConversion((current) => ({ ...current, fromUomId: event.target.value }))} required><option value="">Source unit</option>{catalog?.units.map((unit) => <option value={unit.id} key={unit.id}>{unit.code}</option>)}</select></label>
            <label><span>To</span><select value={conversion.toUomId} onChange={(event) => setConversion((current) => ({ ...current, toUomId: event.target.value }))} required><option value="">Destination unit</option>{catalog?.units.map((unit) => <option value={unit.id} key={unit.id}>{unit.code}</option>)}</select></label>
            <label><span>Factor</span><input type="number" min="0.000001" step="0.000001" value={conversion.factor} onChange={(event) => setConversion((current) => ({ ...current, factor: event.target.value }))} required /></label>
            <label className="catalog-reason"><span>Rule reason</span><input value={conversion.reason} onChange={(event) => setConversion((current) => ({ ...current, reason: event.target.value }))} minLength={3} maxLength={500} required /></label>
            <button className="button primary" type="submit" disabled={busy}><Save size={18} aria-hidden="true" />Save conversion</button>
          </form>
          <div className="catalog-rules-list">
            {catalog?.conversions.map((rule) => <div key={rule.id}><strong>{catalog.items.find((item) => item.id === rule.item_id)?.sku}</strong><span>{rule.from_uom} <ArrowRight size={15} aria-hidden="true" /> {rule.factor} {rule.to_uom}</span></div>)}
            {catalog?.conversions.length === 0 && <p className="empty-copy">No conversion rules.</p>}
          </div>
        </div>
      )}

      {view === 'alternates' && (
        <div className="catalog-layout">
          <form className="catalog-form" onSubmit={(event) => void approveAlternate(event)}>
            <div className="form-heading"><ArrowRight size={21} aria-hidden="true" /><span><strong>Approve alternate</strong><small>Paths and base UOMs must match.</small></span></div>
            <label><span>Requested item</span><select value={alternate.itemId} onChange={(event) => setAlternate((current) => ({ ...current, itemId: event.target.value }))} required><option value="">Select item</option>{activeItems.map((item) => <option value={item.id} key={item.id}>{item.sku}</option>)}</select></label>
            <label><span>Approved substitute</span><select value={alternate.alternateItemId} onChange={(event) => setAlternate((current) => ({ ...current, alternateItemId: event.target.value }))} required><option value="">Select substitute</option>{activeItems.filter((item) => item.id !== alternate.itemId).map((item) => <option value={item.id} key={item.id}>{item.sku}</option>)}</select></label>
            <label><span>Approval reason</span><input value={alternate.reason} onChange={(event) => setAlternate((current) => ({ ...current, reason: event.target.value }))} minLength={3} maxLength={500} required /></label>
            <button className="button primary" type="submit" disabled={busy}><Plus size={18} aria-hidden="true" />Approve</button>
          </form>
          <div className="catalog-register">
            {catalog?.alternates.map((approval) => (
              <div className="catalog-alternate-row" key={approval.id}>
                <span><strong>{approval.item_sku}</strong><small>Requested</small></span><ArrowRight size={17} aria-hidden="true" /><span><strong>{approval.alternate_sku}</strong><small>Approved substitute</small></span>
                {revokingId !== approval.id && <button className="icon-button" type="button" title="Revoke alternate" onClick={() => setRevokingId(approval.id)}><Trash2 size={18} aria-hidden="true" /><span className="sr-only">Revoke alternate</span></button>}
                {revokingId === approval.id && <form className="alternate-revoke-form" onSubmit={(event) => void revokeAlternate(event, approval.id)}><label><span>Revocation reason</span><input value={revokeReason} onChange={(event) => setRevokeReason(event.target.value)} minLength={3} required /></label><button className="button primary" type="submit" disabled={busy}>Revoke</button><button className="button secondary" type="button" onClick={() => setRevokingId(null)}>Keep</button></form>}
              </div>
            ))}
            {catalog?.alternates.length === 0 && <p className="empty-copy">No approved alternates.</p>}
          </div>
        </div>
      )}
    </section>
  )
}