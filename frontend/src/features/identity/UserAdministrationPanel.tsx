import { KeyRound, Plus, Save, ShieldCheck, UserRound, UserRoundX } from 'lucide-react'
import { useEffect, useState, type SyntheticEvent } from 'react'
import { api, ApiError } from '../../api/client'
import type { AdminUser, Role } from '../../api/types'
import { useAuth } from '../../app/auth'

interface UserDraft {
  username: string
  displayName: string
  password: string
  roles: Role[]
  isActive: boolean
  reason: string
}

const roleOptions: Array<{ value: Role; label: string }> = [
  { value: 'employee', label: 'Employee' },
  { value: 'foreman', label: 'Foreman' },
  { value: 'warehouse_worker', label: 'Warehouse worker' },
  { value: 'inventory_manager', label: 'Inventory manager' },
  { value: 'system_administrator', label: 'System administrator' },
]

const emptyDraft: UserDraft = {
  username: '',
  displayName: '',
  password: '',
  roles: ['employee'],
  isActive: true,
  reason: '',
}

function draftFromUser(user: AdminUser): UserDraft {
  return {
    username: user.username,
    displayName: user.display_name,
    password: '',
    roles: user.roles,
    isActive: user.is_active,
    reason: '',
  }
}

function roleLabel(role: Role) {
  return roleOptions.find((option) => option.value === role)?.label ?? role
}

export function UserAdministrationPanel() {
  const { user: currentUser } = useAuth()
  const [users, setUsers] = useState<AdminUser[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [draft, setDraft] = useState<UserDraft>(emptyDraft)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    api.listUsers()
      .then((records) => {
        if (active) setUsers(records)
      })
      .catch((error_: unknown) => {
        if (active) setError(error_ instanceof ApiError ? error_.message : 'User directory is unavailable')
      })
    return () => {
      active = false
    }
  }, [])

  function startNew() {
    setSelectedId(null)
    setDraft(emptyDraft)
    setError('')
  }

  function selectUser(user: AdminUser) {
    setSelectedId(user.id)
    setDraft(draftFromUser(user))
    setError('')
  }

  function toggleRole(role: Role) {
    setDraft((current) => ({
      ...current,
      roles: current.roles.includes(role)
        ? current.roles.filter((assigned) => assigned !== role)
        : [...current.roles, role],
    }))
  }

  async function save(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    if (draft.roles.length === 0) {
      setError('Assign at least one role')
      return
    }
    setBusy(true)
    setError('')
    try {
      const saved = selectedId
        ? await api.updateUser(selectedId, {
            display_name: draft.displayName.trim(),
            is_active: draft.isActive,
            password: draft.password || null,
            roles: draft.roles,
            reason: draft.reason.trim(),
          })
        : await api.createUser({
            username: draft.username.trim(),
            display_name: draft.displayName.trim(),
            password: draft.password || null,
            roles: draft.roles,
          })
      setUsers((current) => {
        const next = current.some((account) => account.id === saved.id)
          ? current.map((account) => account.id === saved.id ? saved : account)
          : [...current, saved]
        return next.sort((left, right) => left.display_name.localeCompare(right.display_name))
      })
      setSelectedId(saved.id)
      setDraft(draftFromUser(saved))
    } catch (error_) {
      setError(error_ instanceof ApiError ? error_.message : 'User could not be saved')
    } finally {
      setBusy(false)
    }
  }

  const editingSelf = selectedId === currentUser?.id

  return (
    <section className="operations-panel user-administration" role="tabpanel">
      <div className="section-heading">
        <div><p className="eyebrow">Accounts / Roles / Access state</p><h2>User administration</h2></div>
        <button className="button secondary" type="button" onClick={startNew}><Plus size={18} aria-hidden="true" />New user</button>
      </div>
      {error && <div className="inline-alert error" role="alert">{error}</div>}
      <div className="user-administration-grid">
        <div className="user-directory" aria-label="Warehouse users">
          {users.map((account) => (
            <button className={`user-directory-row ${selectedId === account.id ? 'selected' : ''}`} type="button" onClick={() => selectUser(account)} key={account.id}>
              <span className={`user-state-icon ${account.is_active ? '' : 'inactive'}`}>{account.is_active ? <UserRound size={19} aria-hidden="true" /> : <UserRoundX size={19} aria-hidden="true" />}</span>
              <span><strong>{account.display_name}</strong><small>@{account.username}</small></span>
              <span className="user-role-summary">{account.roles.map(roleLabel).join(', ')}</span>
            </button>
          ))}
          {users.length === 0 && <p className="empty-copy">No user accounts are configured.</p>}
        </div>

        <form className="user-admin-form" onSubmit={(event) => void save(event)}>
          <div className="form-heading"><ShieldCheck size={21} aria-hidden="true" /><span><strong>{selectedId ? 'Edit access' : 'Provision user'}</strong><small>{selectedId ? 'Saving signs this user out of active sessions' : 'Local credentials are optional'}</small></span></div>
          <label><span>Username</span><input value={draft.username} onChange={(event) => setDraft((current) => ({ ...current, username: event.target.value }))} disabled={selectedId !== null} autoComplete="off" required /></label>
          <label><span>Display name</span><input value={draft.displayName} onChange={(event) => setDraft((current) => ({ ...current, displayName: event.target.value }))} required /></label>
          <label className="password-field"><span><KeyRound size={14} aria-hidden="true" />{selectedId ? 'Reset local password' : 'Temporary local password'}</span><input type="password" minLength={8} maxLength={200} value={draft.password} onChange={(event) => setDraft((current) => ({ ...current, password: event.target.value }))} autoComplete="new-password" placeholder="Optional" /></label>
          <fieldset className="role-selector">
            <legend>Assigned roles</legend>
            {roleOptions.map((role) => (
              <label key={role.value}>
                <input type="checkbox" checked={draft.roles.includes(role.value)} disabled={editingSelf && role.value === 'system_administrator'} onChange={() => toggleRole(role.value)} />
                <span>{role.label}</span>
              </label>
            ))}
          </fieldset>
          {selectedId && <label className="account-active"><input type="checkbox" checked={draft.isActive} disabled={editingSelf} onChange={(event) => setDraft((current) => ({ ...current, isActive: event.target.checked }))} /><span>Account active</span></label>}
          {selectedId && <label><span>Change reason</span><input value={draft.reason} onChange={(event) => setDraft((current) => ({ ...current, reason: event.target.value }))} minLength={3} maxLength={500} required /></label>}
          <button className="button primary" type="submit" disabled={busy || draft.roles.length === 0}><Save size={18} aria-hidden="true" />{busy ? 'Saving...' : 'Save user'}</button>
        </form>
      </div>
    </section>
  )
}