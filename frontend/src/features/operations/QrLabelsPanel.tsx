import { Printer, QrCode, RotateCcw, ShieldOff } from 'lucide-react'
import { useEffect, useState, type SyntheticEvent } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { api, ApiError } from '../../api/client'
import type { CreatedQrToken, InventoryItem, Location, QrTargetType, QrToken } from '../../api/types'

interface QrLabelsPanelProps {
  inventory: InventoryItem[]
  locations: Location[]
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value))
}

export function QrLabelsPanel({ inventory, locations }: QrLabelsPanelProps) {
  const [tokens, setTokens] = useState<QrToken[]>([])
  const [created, setCreated] = useState<CreatedQrToken | null>(null)
  const [targetType, setTargetType] = useState<QrTargetType>('item')
  const [targetId, setTargetId] = useState('')
  const [expiresInHours, setExpiresInHours] = useState<number | null>(null)
  const [revokingId, setRevokingId] = useState<string | null>(null)
  const [revokeReason, setRevokeReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const options = targetType === 'item'
    ? inventory.map((item) => ({ id: item.id, label: `${item.sku} / ${item.description}` }))
    : locations.map((location) => ({ id: location.id, label: location.code }))

  useEffect(() => {
    let active = true
    api.listQrTokens()
      .then((records) => {
        if (active) setTokens(records)
      })
      .catch((error_: unknown) => {
        if (active) setError(error_ instanceof ApiError ? error_.message : 'QR labels are unavailable')
      })
    return () => {
      active = false
    }
  }, [])

  function changeTargetType(value: QrTargetType) {
    setTargetType(value)
    setTargetId('')
  }

  async function issueLabel(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const issued = await api.createQrToken(targetType, targetId, expiresInHours)
      setCreated(issued)
      setTokens((current) => [issued, ...current])
    } catch (error_) {
      setError(error_ instanceof ApiError ? error_.message : 'QR label could not be issued')
    } finally {
      setBusy(false)
    }
  }

  async function revokeLabel(event: SyntheticEvent<HTMLFormElement>, tokenId: string) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const revoked = await api.revokeQrToken(tokenId, revokeReason.trim())
      setTokens((current) => current.map((token) => token.id === tokenId ? revoked : token))
      if (created?.id === tokenId) setCreated(null)
      setRevokingId(null)
      setRevokeReason('')
    } catch (error_) {
      setError(error_ instanceof ApiError ? error_.message : 'QR label could not be revoked')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="operations-panel qr-label-panel" role="tabpanel">
      <div className="section-heading">
        <div><p className="eyebrow">Opaque live-record labels</p><h2>QR labels</h2></div>
        <span className="count-label">{tokens.length} issued</span>
      </div>
      {error && <div className="inline-alert error" role="alert">{error}</div>}
      <div className="qr-label-workspace">
        <form className="qr-label-controls" onSubmit={(event) => void issueLabel(event)}>
          <div className="segmented-control" aria-label="Label target type">
            <button type="button" className={targetType === 'item' ? 'active' : ''} onClick={() => changeTargetType('item')}>Item</button>
            <button type="button" className={targetType === 'location' ? 'active' : ''} onClick={() => changeTargetType('location')}>Location</button>
          </div>
          <label><span>Warehouse record</span><select value={targetId} onChange={(event) => setTargetId(event.target.value)} required><option value="">Select {targetType}</option>{options.map((option) => <option value={option.id} key={option.id}>{option.label}</option>)}</select></label>
          <label><span>Validity</span><select value={expiresInHours ?? ''} onChange={(event) => setExpiresInHours(event.target.value ? Number(event.target.value) : null)}><option value="">No expiry</option><option value="2160">90 days</option><option value="8760">1 year</option></select></label>
          <button className="button primary" type="submit" disabled={busy || !targetId}><QrCode size={18} aria-hidden="true" />{busy ? 'Issuing...' : 'Issue label'}</button>
        </form>

        {created ? (
          <article className="print-label">
            <div className="print-label-code"><QRCodeSVG value={`${window.location.origin}${created.scan_path}`} size={192} level="M" /></div>
            <div><p className="eyebrow">{created.target_type}</p><h3>{created.target_label}</h3><small>{created.expires_at ? `Expires ${formatDate(created.expires_at)}` : 'Permanent label'}</small></div>
            <button className="button secondary print-command" type="button" onClick={() => window.print()}><Printer size={18} aria-hidden="true" />Print label</button>
          </article>
        ) : (
          <div className="qr-label-placeholder"><QrCode size={42} aria-hidden="true" /><strong>Issue a label to preview it</strong></div>
        )}
      </div>

      <div className="section-heading qr-history-heading"><div><p className="eyebrow">Lifecycle register</p><h2>Issued labels</h2></div></div>
      <div className="operations-table qr-token-list">
        {tokens.map((token) => (
          <div className={`operations-row qr-token-row ${token.revoked_at ? 'revoked' : ''}`} key={token.id}>
            <span className={`integration-state ${token.revoked_at ? 'failed' : ''}`}>{token.revoked_at ? <ShieldOff size={17} aria-hidden="true" /> : <QrCode size={17} aria-hidden="true" />}<strong>{token.revoked_at ? 'Revoked' : 'Active'}</strong></span>
            <span><strong>{token.target_label}</strong><small>{token.target_type} / {token.id.slice(0, 8)}</small></span>
            <span><strong>{token.expires_at ? formatDate(token.expires_at) : 'No expiry'}</strong><small>{token.last_resolved_at ? `Scanned ${formatDate(token.last_resolved_at)}` : 'Not scanned'}</small></span>
            {!token.revoked_at && revokingId !== token.id && <button className="icon-button" type="button" title="Revoke QR label" onClick={() => setRevokingId(token.id)}><ShieldOff size={18} aria-hidden="true" /><span className="sr-only">Revoke QR label</span></button>}
            {revokingId === token.id && (
              <form className="qr-revoke-form" onSubmit={(event) => void revokeLabel(event, token.id)}>
                <label><span>Revocation reason</span><input value={revokeReason} onChange={(event) => setRevokeReason(event.target.value)} minLength={3} maxLength={500} required /></label>
                <button className="button primary" type="submit" disabled={busy}><ShieldOff size={17} aria-hidden="true" />Confirm</button>
                <button className="button secondary" type="button" onClick={() => { setRevokingId(null); setRevokeReason('') }}><RotateCcw size={17} aria-hidden="true" />Keep</button>
              </form>
            )}
          </div>
        ))}
        {tokens.length === 0 && <p className="empty-copy">No QR labels have been issued.</p>}
      </div>
    </section>
  )
}