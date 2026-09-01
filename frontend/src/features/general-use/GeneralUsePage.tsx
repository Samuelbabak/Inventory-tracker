import { CheckCircle2, MapPin, PackageMinus, ScanLine } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { InventoryItem, InventoryMutation, Recipient } from '../../api/types'

interface GeneralUseResources {
  inventory: InventoryItem[]
  recipients: Recipient[]
  error: string
}

export function GeneralUsePage() {
  const [resources, setResources] = useState<GeneralUseResources | null>(null)
  const [recipientId, setRecipientId] = useState('')
  const [itemId, setItemId] = useState('')
  const [positionId, setPositionId] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [note, setNote] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState('')
  const [completed, setCompleted] = useState<InventoryMutation | null>(null)

  useEffect(() => {
    let active = true
    Promise.all([api.listInventory(), api.listRecipients()])
      .then(([inventory, recipients]) => {
        if (active) {
          setResources({
            inventory: inventory.filter((item) => item.inventory_path === 'local_general_use'),
            recipients,
            error: '',
          })
        }
      })
      .catch((error_: unknown) => {
        if (active) {
          setResources({
            inventory: [],
            recipients: [],
            error: error_ instanceof ApiError ? error_.message : 'General-use stock could not be loaded',
          })
        }
      })
    return () => {
      active = false
    }
  }, [])

  const selectedItem = resources?.inventory.find((item) => item.id === itemId)
  const selectedPosition = selectedItem?.locations.find((position) => position.stock_position_id === positionId)
  const effectiveRecipientId = recipientId || (resources?.recipients.length === 1 ? resources.recipients[0].id : '')
  const usableAtPosition = selectedPosition
    ? Number(selectedPosition.on_hand) - Number(selectedPosition.quarantined_qty)
    : 0

  function changeItem(value: string) {
    setItemId(value)
    const item = resources?.inventory.find((candidate) => candidate.id === value)
    setPositionId(item?.locations.length === 1 ? item.locations[0].stock_position_id : '')
    setCompleted(null)
  }

  async function withdraw() {
    setFormError('')
    setCompleted(null)
    if (!effectiveRecipientId || !selectedPosition || !selectedItem) {
      setFormError('Select a recipient, item, and stock location')
      return
    }
    if (!quantity || Number(quantity) <= 0 || Number(quantity) > usableAtPosition) {
      setFormError(`Quantity must be between 0 and ${usableAtPosition}`)
      return
    }
    setSubmitting(true)
    try {
      const mutation = await api.withdrawGeneralUse({
        stock_position_id: selectedPosition.stock_position_id,
        recipient_id: effectiveRecipientId,
        quantity: Number(quantity),
        note: note.trim() || undefined,
      })
      const refreshed = await api.listInventory()
      setResources((current) => ({
        inventory: refreshed.filter((item) => item.inventory_path === 'local_general_use'),
        recipients: current?.recipients ?? [],
        error: '',
      }))
      setCompleted(mutation)
      setQuantity('1')
      setNote('')
    } catch (error_) {
      setFormError(error_ instanceof ApiError ? error_.message : 'Withdrawal could not be recorded')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page general-use-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">Local stock / Direct withdrawal</p>
          <h1>General-use material</h1>
          <p>Record supplies taken directly from a warehouse position.</p>
        </div>
      </header>

      {resources?.error && <div className="inline-alert error" role="alert">{resources.error}</div>}
      {formError && <div className="inline-alert error" role="alert">{formError}</div>}
      {completed && (
        <output className="inline-alert success" aria-live="polite">
          <CheckCircle2 size={20} aria-hidden="true" />
          <span><strong>Withdrawal recorded</strong>{completed.on_hand} {selectedItem?.uom} remain at this position.</span>
        </output>
      )}

      <div className="withdrawal-layout">
        <section className="withdrawal-form">
          <div className="section-heading"><div><p className="eyebrow">Transaction</p><h2>Material and recipient</h2></div></div>
          <div className="withdrawal-fields">
            <label>
              <span>Recipient</span>
              <select value={effectiveRecipientId} onChange={(event) => setRecipientId(event.target.value)} disabled={(resources?.recipients.length ?? 0) === 1}>
                <option value="">Select employee</option>
                {resources?.recipients.map((recipient) => <option value={recipient.id} key={recipient.id}>{recipient.display_name} / {recipient.employee_number}</option>)}
              </select>
            </label>
            <label>
              <span><ScanLine size={16} aria-hidden="true" /> Item</span>
              <select value={itemId} onChange={(event) => changeItem(event.target.value)}>
                <option value="">Select or scan item</option>
                {resources?.inventory.map((item) => <option value={item.id} key={item.id}>{item.sku} / {item.description}</option>)}
              </select>
            </label>
            <label>
              <span><MapPin size={16} aria-hidden="true" /> Stock location</span>
              <select value={positionId} onChange={(event) => setPositionId(event.target.value)} disabled={!selectedItem}>
                <option value="">Select position</option>
                {selectedItem?.locations.map((position) => <option value={position.stock_position_id} key={position.stock_position_id}>{position.location_code} / {Number(position.on_hand) - Number(position.quarantined_qty)} usable</option>)}
              </select>
            </label>
            <label>
              <span>Quantity {selectedItem ? `/ ${selectedItem.uom}` : ''}</span>
              <input type="number" inputMode="decimal" min="0.001" max={usableAtPosition || undefined} step="0.001" value={quantity} onChange={(event) => setQuantity(event.target.value)} />
            </label>
            <label className="note-field">
              <span>Note <small>Optional</small></span>
              <textarea rows={3} maxLength={500} value={note} onChange={(event) => setNote(event.target.value)} />
            </label>
          </div>
        </section>

        <aside className="withdrawal-summary">
          <span className="metric-icon blue"><PackageMinus size={22} aria-hidden="true" /></span>
          <p className="eyebrow">Confirm withdrawal</p>
          <h2>{selectedItem?.sku ?? 'No item selected'}</h2>
          <p>{selectedItem?.description ?? 'Select local general-use material.'}</p>
          <dl>
            <div><dt>Position</dt><dd>{selectedPosition?.location_code ?? '--'}</dd></div>
            <div><dt>Usable now</dt><dd>{selectedPosition ? `${usableAtPosition} ${selectedItem?.uom}` : '--'}</dd></div>
            <div><dt>After withdrawal</dt><dd>{selectedPosition && quantity ? `${usableAtPosition - Number(quantity)} ${selectedItem?.uom}` : '--'}</dd></div>
          </dl>
          <button type="button" className="button primary" disabled={submitting || !resources} onClick={() => void withdraw()}>
            <PackageMinus size={18} aria-hidden="true" /> {submitting ? 'Recording...' : 'Record withdrawal'}
          </button>
        </aside>
      </div>
    </div>
  )
}
