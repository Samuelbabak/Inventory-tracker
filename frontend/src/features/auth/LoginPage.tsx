import { ArrowRight, Boxes, LockKeyhole, UserRound } from 'lucide-react'
import { useState, type SyntheticEvent } from 'react'
import { ApiError } from '../../api/client'
import { useAuth } from '../../app/auth'

export function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState('manager')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await login(username, password)
    } catch (error_) {
      setError(error_ instanceof ApiError ? error_.message : 'Unable to reach the warehouse')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-brand" aria-label="Haynes Inventory">
        <div className="brand-lockup">
          <span className="brand-mark"><Boxes size={31} aria-hidden="true" /></span>
          <span>HAYNES</span>
        </div>
        <div className="login-message">
          <p className="eyebrow">Warehouse operations</p>
          <h1>Material, where it belongs.</h1>
          <p>Live stock, accountable handoffs, and a clear morning queue.</p>
        </div>
        <div className="location-stripe" aria-hidden="true">
          <span>A01</span><span>B04</span><span>S02</span><span>P01</span>
        </div>
      </section>
      <section className="login-panel">
        <form onSubmit={submit}>
          <header>
            <p className="eyebrow">WH1 / Main warehouse</p>
            <h2>Sign in</h2>
          </header>
          <label>
            <span>Username</span>
            <span className="input-wrap">
              <UserRound size={18} aria-hidden="true" />
              <input
                autoComplete="username"
                autoFocus
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                required
              />
            </span>
          </label>
          <label>
            <span>Password</span>
            <span className="input-wrap">
              <LockKeyhole size={18} aria-hidden="true" />
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={8}
              />
            </span>
          </label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button type="submit" className="button primary login-submit" disabled={submitting}>
            {submitting ? 'Signing in...' : 'Continue'}
            {!submitting && <ArrowRight size={18} aria-hidden="true" />}
          </button>
        </form>
        <footer>Authorized Haynes personnel only</footer>
      </section>
    </main>
  )
}
