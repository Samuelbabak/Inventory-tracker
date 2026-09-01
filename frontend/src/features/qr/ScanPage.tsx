import { CircleAlert, LoaderCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../../api/client'

export function ScanPage() {
  const navigate = useNavigate()
  const [token] = useState(() => window.location.hash.slice(1))
  const [error, setError] = useState('')

  useEffect(() => {
    if (!token) return
    window.history.replaceState(
      window.history.state,
      '',
      `${window.location.pathname}${window.location.search}`,
    )
    let active = true
    api.resolveQrToken(token)
      .then((resolution) => {
        if (active) navigate(resolution.route, { replace: true })
      })
      .catch((error_: unknown) => {
        if (active) {
          setError(error_ instanceof ApiError ? error_.message : 'QR label could not be resolved')
        }
      })
    return () => {
      active = false
    }
  }, [navigate, token])

  const message = token ? error : 'This QR label does not contain a token'
  return (
    <div className="page scan-page">
      <section className={`scan-state ${message ? 'failed' : ''}`}>
        {message ? <CircleAlert size={32} aria-hidden="true" /> : <LoaderCircle className="spin" size={32} aria-hidden="true" />}
        <div>
          <p className="eyebrow">Warehouse QR</p>
          <h1>{message ? 'Label unavailable' : 'Opening label'}</h1>
          <p>{message || 'Resolving the live warehouse record...'}</p>
        </div>
        {message && <Link className="button secondary" to="/inventory">Open inventory</Link>}
      </section>
    </div>
  )
}