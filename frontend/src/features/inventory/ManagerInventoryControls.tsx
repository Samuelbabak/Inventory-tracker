import {
  ArchiveRestore,
  ClipboardCheck,
  MoveRight,
  PackagePlus,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react'
import { useState, type SyntheticEvent } from 'react'
import { api, ApiError } from '../../api/client'
import type { InventoryItem } from '../../api/types'

type InventoryAction = 'receive' | 'return' | 'move' | 'count' | 'quarantine' | 'release'

const actions = [
  { id: 'receive', label: 'Receive', icon: PackagePlus },
  { id: 'return', label: 'Return', icon: ArchiveRestore },
  { id: 'move', label: 'Move', icon: MoveRight },
  { id: 'count', label: 'Count', icon: ClipboardCheck },
  { id: 'quarantine', label: 'Quarantine', icon: ShieldAlert },
  { id: 'release', label: 'Release', icon: ShieldCheck },
] satisfies Array<{ id: InventoryAction; label: string; icon: typeof PackagePlus }>

export function ManagerInventoryControls({
  item,
  onChanged,
}: Readonly<{
  item: InventoryItem
  onChanged: () => void
}>) {
  const [action, setAction] = useState<InventoryAction>('receive')
  const [positionId, setPositionId] = useState(item.locations[0]?.stock_position_id ?? '')
  const [destinationId, setDestinationId] = useState('')
  const [quantity, setQuantity] = useState('')
  const [condition, setCondition] = useState<'usable' | 'quarantined'>('usable')
  const [reason, setReason] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const balanceActionsEnabled = item.inventory_path === 'local_general_use'
  const availableActions = actions.filter(({ id }) => balanceActionsEnabled || id === 'move')
  const selectedPosition = item.locations.find((position) => position.stock_position_id === positionId)

  function chooseAction(nextAction: InventoryAction) {
    setAction(nextAction)
    setMessage('')
    setError('')
    setQuantity('')
  }

  async function submit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    const numericQuantity = Number(quantity)
    if (!positionId || !Number.isFinite(numericQuantity) || numericQuantity < 0) {
      setError('Choose a stock position and enter a valid quantity')
      return
    }
    if (action !== 'count' && numericQuantity === 0) {
      setError('Quantity must be greater than zero')
      return
    }
    if (reason.trim().length < 3) {
      setError('Enter an operational reason of at least three characters')
      return
    }
    if (action === 'move' && !destinationId) {
      setError('Choose a destination stock position')
      return
    }
    setBusy(true)
    setError('')
    setMessage('')
    try {
      if (action === 'receive') {
        await api.receiveInventory({ stock_position_id: positionId, quantity: numericQuantity, reason: reason.trim() })
      } else if (action === 'return') {
        await api.returnInventory({
          stock_position_id: positionId,
          quantity: numericQuantity,
          condition,
          reason: reason.trim(),
        })
      } else if (action === 'move') {
        await api.moveInventory({
          source_stock_position_id: positionId,
          destination_stock_position_id: destinationId,
          quantity: numericQuantity,
          reason: reason.trim(),
        })
      } else if (action === 'count') {
        await api.adjustInventory({
          stock_position_id: positionId,
          counted_on_hand: numericQuantity,
          reason: reason.trim(),
        })
      } else if (action === 'quarantine') {
        await api.quarantineInventory({ stock_position_id: positionId, quantity: numericQuantity, reason: reason.trim() })
      } else {
        await api.releaseInventory({ stock_position_id: positionId, quantity: numericQuantity, reason: reason.trim() })
      }
      setMessage(`${actions.find(({ id }) => id === action)?.label ?? 'Inventory'} recorded`)
      setQuantity('')
      setReason('')
      onChanged()
    } catch (error_) {
      setError(error_ instanceof ApiError ? error_.message : 'Inventory operation could not be recorded')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="manager-stock-controls">
      <div className="section-heading">
        <div><p className="eyebrow">Manager controls</p><h3>Stock operation</h3></div>
      </div>
      {!balanceActionsEnabled && (
        <p className="control-note">Spectrum balance operations remain disabled until their posting capability is proven.</p>
      )}
      <div className="stock-action-tabs" role="tablist" aria-label="Stock operation">
        {availableActions.map(({ id, label, icon: Icon }) => (
          <button type="button" role="tab" aria-selected={action === id} className={action === id ? 'active' : ''} onClick={() => chooseAction(id)} key={id}>
            <Icon size={16} aria-hidden="true" />
            {label}
          </button>
        ))}
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      {message && <output className="inline-alert success">{message}</output>}
      <form className="stock-operation-form" onSubmit={(event) => void submit(event)}>
        <label>
          <span>{action === 'move' ? 'Source position' : 'Stock position'}</span>
          <select value={positionId} onChange={(event) => setPositionId(event.target.value)} required>
            {item.locations.map((position) => (
              <option value={position.stock_position_id} key={position.stock_position_id}>{position.location_code}</option>
            ))}
          </select>
        </label>
        {action === 'move' && (
          <label>
            <span>Destination position</span>
            <select value={destinationId} onChange={(event) => setDestinationId(event.target.value)} required>
              <option value="">Choose destination</option>
              {item.locations.filter((position) => position.stock_position_id !== positionId).map((position) => (
                <option value={position.stock_position_id} key={position.stock_position_id}>{position.location_code}</option>
              ))}
            </select>
          </label>
        )}
        {action === 'return' && (
          <label>
            <span>Return condition</span>
            <select value={condition} onChange={(event) => setCondition(event.target.value as 'usable' | 'quarantined')}>
              <option value="usable">Usable stock</option>
              <option value="quarantined">Quarantine for review</option>
            </select>
          </label>
        )}
        <label>
          <span>{action === 'count' ? 'Counted on hand' : `Quantity / ${item.uom}`}</span>
          <input type="number" inputMode="decimal" min="0" step="0.001" value={quantity} onChange={(event) => setQuantity(event.target.value)} required />
          {selectedPosition && <small>{selectedPosition.on_hand} on hand / {selectedPosition.quarantined_qty} quarantined</small>}
        </label>
        <label className="operation-reason">
          <span>Reason</span>
          <input value={reason} onChange={(event) => setReason(event.target.value)} minLength={3} maxLength={500} required />
        </label>
        <button className="button primary" type="submit" disabled={busy || item.locations.length === 0 || (action === 'move' && item.locations.length < 2)}>
          {busy ? 'Recording...' : `Record ${actions.find(({ id }) => id === action)?.label.toLocaleLowerCase()}`}
        </button>
      </form>
    </section>
  )
}