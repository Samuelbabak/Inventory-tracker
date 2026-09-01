import { AlertTriangle, ArrowLeft, Minus, PackagePlus, Plus, Send } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../../api/client'
import type { InventoryItem, MaterialRequest, Recipient, RequestPriority } from '../../api/types'

interface BuilderResources {
  inventory: InventoryItem[]
  recipients: Recipient[]
  error: string
}

interface DraftLine {
  item_id: string
  sku: string
  description: string
  inventory_path: InventoryItem['inventory_path']
  uom: string
  quantity: string
}

interface RepeatState {
  repeat?: MaterialRequest
}

export function RequestBuilderPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const repeatedRequest = (location.state as RepeatState | null)?.repeat
  const [resources, setResources] = useState<BuilderResources | null>(null)
  const [recipientId, setRecipientId] = useState('')
  const [priority, setPriority] = useState<RequestPriority>(repeatedRequest?.priority ?? 'normal')
  const [urgentReason, setUrgentReason] = useState(repeatedRequest?.urgent_reason ?? '')
  const [jobNumber, setJobNumber] = useState(repeatedRequest?.job_number ?? '')
  const [costCode, setCostCode] = useState(repeatedRequest?.cost_code ?? '')
  const [selectedItemId, setSelectedItemId] = useState('')
  const [lines, setLines] = useState<DraftLine[]>(() =>
    repeatedRequest?.lines.map((line) => ({
      item_id: line.item_id,
      sku: line.sku,
      description: line.description,
      inventory_path: line.inventory_path,
      uom: line.uom,
      quantity: line.requested_qty,
    })) ?? [],
  )
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')

  useEffect(() => {
    let active = true
    Promise.all([api.listInventory(), api.listRecipients()])
      .then(([inventory, recipients]) => {
        if (active) setResources({ inventory, recipients, error: '' })
      })
      .catch((error_: unknown) => {
        if (active) {
          setResources({
            inventory: [],
            recipients: [],
            error: error_ instanceof ApiError ? error_.message : 'Request data could not be loaded',
          })
        }
      })
    return () => {
      active = false
    }
  }, [])

  const selectedItem = resources?.inventory.find((item) => item.id === selectedItemId)
  const includesSpectrum = lines.some((line) => line.inventory_path === 'spectrum_managed')

  function addItem() {
    if (!selectedItem) return
    setLines((current) => {
      if (current.some((line) => line.item_id === selectedItem.id)) return current
      return [
        ...current,
        {
          item_id: selectedItem.id,
          sku: selectedItem.sku,
          description: selectedItem.description,
          inventory_path: selectedItem.inventory_path,
          uom: selectedItem.uom,
          quantity: '1',
        },
      ]
    })
    setSelectedItemId('')
  }

  function changeQuantity(itemId: string, value: string) {
    setLines((current) => current.map((line) => (line.item_id === itemId ? { ...line, quantity: value } : line)))
  }

  function removeLine(itemId: string) {
    setLines((current) => current.filter((line) => line.item_id !== itemId))
  }

  async function createRequest(submit: boolean) {
    setFormError('')
    if (!recipientId) {
      setFormError('Select a material recipient')
      return
    }
    if (lines.length === 0 || lines.some((line) => !line.quantity || Number(line.quantity) <= 0)) {
      setFormError('Add at least one item with a quantity greater than zero')
      return
    }
    if (priority === 'urgent' && !urgentReason.trim()) {
      setFormError('Urgent requests require a reason')
      return
    }
    if (includesSpectrum && !jobNumber.trim()) {
      setFormError('Spectrum-managed material requires a job number')
      return
    }

    setSaving(true)
    try {
      const created = await api.createRequest({
        recipient_id: recipientId,
        priority,
        urgent_reason: urgentReason.trim() || undefined,
        job_number: jobNumber.trim() || undefined,
        cost_code: costCode.trim() || undefined,
        lines: lines.map((line) => ({ item_id: line.item_id, quantity: Number(line.quantity) })),
        submit,
      })
      navigate(`/requests/${created.id}`, { replace: true })
    } catch (error_) {
      setFormError(error_ instanceof ApiError ? error_.message : 'The request could not be created')
      setSaving(false)
    }
  }

  return (
    <div className="page request-builder-page">
      <header className="page-heading builder-heading">
        <div>
          <Link className="back-link" to="/requests"><ArrowLeft size={17} aria-hidden="true" /> Requests</Link>
          <p className="eyebrow">Material request / Draft</p>
          <h1>{repeatedRequest ? `Repeat ${repeatedRequest.request_number}` : 'New material request'}</h1>
        </div>
      </header>

      {resources?.error && <div className="inline-alert error" role="alert">{resources.error}</div>}
      {formError && <div className="inline-alert error" role="alert">{formError}</div>}

      <div className="builder-layout">
        <div className="builder-main">
          <section className="form-section">
            <div className="section-number">01</div>
            <div className="form-section-content">
              <div className="section-heading"><div><p className="eyebrow">Request details</p><h2>Recipient and priority</h2></div></div>
              <div className="form-grid two-columns">
                <label>
                  <span>Material recipient</span>
                  <select value={recipientId} onChange={(event) => setRecipientId(event.target.value)}>
                    <option value="">Select employee</option>
                    {resources?.recipients.map((recipient) => <option value={recipient.id} key={recipient.id}>{recipient.display_name} / {recipient.employee_number}</option>)}
                  </select>
                </label>
                <fieldset>
                  <legend>Priority</legend>
                  <div className="segmented-control priority-control">
                    <label><input type="radio" name="priority" value="normal" checked={priority === 'normal'} onChange={() => setPriority('normal')} /><span>Normal</span></label>
                    <label><input type="radio" name="priority" value="urgent" checked={priority === 'urgent'} onChange={() => setPriority('urgent')} /><span>Urgent</span></label>
                  </div>
                </fieldset>
              </div>
              {priority === 'urgent' && (
                <label className="full-field">
                  <span>Urgent reason</span>
                  <textarea value={urgentReason} onChange={(event) => setUrgentReason(event.target.value)} maxLength={500} rows={3} />
                </label>
              )}
            </div>
          </section>

          <section className="form-section">
            <div className="section-number">02</div>
            <div className="form-section-content">
              <div className="section-heading"><div><p className="eyebrow">Line items</p><h2>Requested material</h2></div><span className="count-label">{lines.length} {lines.length === 1 ? 'line' : 'lines'}</span></div>
              <div className="item-adder">
                <label>
                  <span className="sr-only">Select inventory item</span>
                  <select value={selectedItemId} onChange={(event) => setSelectedItemId(event.target.value)}>
                    <option value="">Search catalog by item</option>
                    {resources?.inventory.map((item) => <option value={item.id} key={item.id}>{item.sku} / {item.description}</option>)}
                  </select>
                </label>
                <button type="button" className="button secondary" onClick={addItem} disabled={!selectedItem}>
                  <Plus size={18} aria-hidden="true" /> Add
                </button>
              </div>

              <div className="draft-lines">
                {lines.length === 0 && <div className="empty-line"><PackagePlus size={25} aria-hidden="true" /><span>No material added</span></div>}
                {lines.map((line) => (
                  <div className="draft-line" key={line.item_id}>
                    <span className="item-identity"><strong>{line.sku}</strong><small>{line.description}</small></span>
                    <label className="quantity-input">
                      <span>Quantity / {line.uom}</span>
                      <input type="number" inputMode="decimal" min="0.001" step="0.001" value={line.quantity} onChange={(event) => changeQuantity(line.item_id, event.target.value)} />
                    </label>
                    <button type="button" className="icon-button" onClick={() => removeLine(line.item_id)} title={`Remove ${line.sku}`}>
                      <Minus size={18} aria-hidden="true" /><span className="sr-only">Remove {line.sku}</span>
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {includesSpectrum && (
            <section className="form-section">
              <div className="section-number">03</div>
              <div className="form-section-content">
                <div className="section-heading"><div><p className="eyebrow">Spectrum accounting</p><h2>Job assignment</h2></div></div>
                <div className="inline-alert warning"><AlertTriangle size={19} aria-hidden="true" /><span>Spectrum-managed items post actual issued quantities after handoff.</span></div>
                <div className="form-grid two-columns">
                  <label><span>Job number</span><input value={jobNumber} onChange={(event) => setJobNumber(event.target.value)} maxLength={80} /></label>
                  <label><span>Cost code</span><input value={costCode} onChange={(event) => setCostCode(event.target.value)} maxLength={80} /></label>
                </div>
              </div>
            </section>
          )}
        </div>

        <aside className="builder-actions">
          <p className="eyebrow">Request summary</p>
          <h2>{lines.length} {lines.length === 1 ? 'material line' : 'material lines'}</h2>
          <dl>
            <div><dt>Recipient</dt><dd>{resources?.recipients.find((recipient) => recipient.id === recipientId)?.display_name ?? 'Not selected'}</dd></div>
            <div><dt>Priority</dt><dd className={priority}>{priority}</dd></div>
            <div><dt>Accounting</dt><dd>{includesSpectrum ? 'Spectrum job' : 'Local stock'}</dd></div>
          </dl>
          <button type="button" className="button primary" disabled={saving || !resources} onClick={() => void createRequest(true)}>
            <Send size={18} aria-hidden="true" /> {saving ? 'Saving...' : 'Submit request'}
          </button>
          <button type="button" className="button secondary" disabled={saving || !resources} onClick={() => void createRequest(false)}>Save draft</button>
        </aside>
      </div>
    </div>
  )
}
