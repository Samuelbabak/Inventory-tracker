import { openDB, type DBSchema } from 'idb'
import type { MaterialRequest, OfflineCommandType, OfflineGrant } from '../api/types'

export type LocalCommandStatus = 'pending' | 'conflict'

interface StoredKey {
  userId: string
  encryptionKey: CryptoKey
}

interface StoredGrant {
  id: string
  userId: string
  requestId: string
  deviceId: string
  requestVersion: number
  nextSequence: number
  expiresAt: string
  snapshotIv: ArrayBuffer
  encryptedSnapshot: ArrayBuffer
}

export interface StoredCommandSummary {
  id: string
  userId: string
  grantId: string
  requestId: string
  sequence: number
  commandType: OfflineCommandType
  status: LocalCommandStatus
  result: Record<string, unknown> | null
  createdAt: string
}

interface StoredCommand extends StoredCommandSummary {
  payloadIv: ArrayBuffer
  encryptedPayload: ArrayBuffer
}

interface OfflineDatabase extends DBSchema {
  keys: {
    key: string
    value: StoredKey
  }
  grants: {
    key: string
    value: StoredGrant
    indexes: {
      'by-user': string
      'by-user-request': [string, string]
    }
  }
  commands: {
    key: string
    value: StoredCommand
    indexes: {
      'by-user': string
      'by-grant': string
    }
  }
}

export interface LocalOfflineGrant {
  id: string
  userId: string
  requestId: string
  deviceId: string
  requestVersion: number
  nextSequence: number
  expiresAt: string
  snapshot: MaterialRequest
}

export interface PendingOfflineCommand extends StoredCommandSummary {
  payload: Record<string, unknown>
}

const database = openDB<OfflineDatabase>('haynes-inventory-offline', 1, {
  upgrade(db) {
    db.createObjectStore('keys', { keyPath: 'userId' })
    const grants = db.createObjectStore('grants', { keyPath: 'id' })
    grants.createIndex('by-user', 'userId')
    grants.createIndex('by-user-request', ['userId', 'requestId'], { unique: true })
    const commands = db.createObjectStore('commands', { keyPath: 'id' })
    commands.createIndex('by-user', 'userId')
    commands.createIndex('by-grant', 'grantId')
  },
})

function randomIv() {
  const value = crypto.getRandomValues(new Uint8Array(12))
  return value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength) as ArrayBuffer
}

async function userKey(userId: string) {
  const db = await database
  const existing = await db.get('keys', userId)
  if (existing) return existing.encryptionKey
  const encryptionKey = await crypto.subtle.generateKey(
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  )
  await db.put('keys', { userId, encryptionKey })
  return encryptionKey
}

async function encrypt(userId: string, value: unknown) {
  const key = await userKey(userId)
  const iv = randomIv()
  const plaintext = new TextEncoder().encode(JSON.stringify(value))
  const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, plaintext)
  return { iv, ciphertext }
}

async function decrypt<T>(userId: string, iv: ArrayBuffer, ciphertext: ArrayBuffer) {
  const key = await userKey(userId)
  const plaintext = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ciphertext)
  return JSON.parse(new TextDecoder().decode(plaintext)) as T
}

async function deleteGrant(grantId: string) {
  const db = await database
  const transaction = db.transaction(['grants', 'commands'], 'readwrite')
  const commandIds = await transaction.objectStore('commands').index('by-grant').getAllKeys(grantId)
  await Promise.all(commandIds.map((commandId) => transaction.objectStore('commands').delete(commandId)))
  await transaction.objectStore('grants').delete(grantId)
  await transaction.done
}

export function getDeviceId() {
  const storageKey = 'haynes.device-id'
  const existing = localStorage.getItem(storageKey)
  if (existing) return existing
  const deviceId = crypto.randomUUID()
  localStorage.setItem(storageKey, deviceId)
  return deviceId
}

export async function saveOfflineGrant(userId: string, grant: OfflineGrant) {
  const db = await database
  const existing = await db.getFromIndex('grants', 'by-user-request', [userId, grant.request_id])
  if (existing) await deleteGrant(existing.id)
  const snapshot = await encrypt(userId, grant.snapshot)
  await db.put('grants', {
    id: grant.id,
    userId,
    requestId: grant.request_id,
    deviceId: grant.device_id,
    requestVersion: grant.request_version,
    nextSequence: 1,
    expiresAt: grant.expires_at,
    snapshotIv: snapshot.iv,
    encryptedSnapshot: snapshot.ciphertext,
  })
}

export async function getOfflineGrant(userId: string, requestId: string) {
  const db = await database
  const stored = await db.getFromIndex('grants', 'by-user-request', [userId, requestId])
  if (!stored) return null
  if (new Date(stored.expiresAt).getTime() <= Date.now()) {
    await deleteGrant(stored.id)
    return null
  }
  return {
    ...stored,
    snapshot: await decrypt<MaterialRequest>(userId, stored.snapshotIv, stored.encryptedSnapshot),
  } satisfies LocalOfflineGrant
}

export async function updateOfflineSnapshot(grantId: string, snapshot: MaterialRequest) {
  const db = await database
  const grant = await db.get('grants', grantId)
  if (!grant) throw new Error('Offline grant not found')
  const encrypted = await encrypt(grant.userId, snapshot)
  await db.put('grants', {
    ...grant,
    snapshotIv: encrypted.iv,
    encryptedSnapshot: encrypted.ciphertext,
  })
}

export async function queueOfflineCommand(
  grantId: string,
  commandType: OfflineCommandType,
  payload: Record<string, unknown>,
  snapshot: MaterialRequest,
) {
  const db = await database
  const grant = await db.get('grants', grantId)
  if (!grant) throw new Error('Offline grant not found')
  const encryptedPayload = await encrypt(grant.userId, payload)
  const encryptedSnapshot = await encrypt(grant.userId, snapshot)
  const command: StoredCommand = {
    id: crypto.randomUUID(),
    userId: grant.userId,
    grantId,
    requestId: grant.requestId,
    sequence: grant.nextSequence,
    commandType,
    status: 'pending',
    result: null,
    createdAt: new Date().toISOString(),
    payloadIv: encryptedPayload.iv,
    encryptedPayload: encryptedPayload.ciphertext,
  }
  const transaction = db.transaction(['grants', 'commands'], 'readwrite')
  await transaction.objectStore('commands').put(command)
  await transaction.objectStore('grants').put({
    ...grant,
    nextSequence: grant.nextSequence + 1,
    snapshotIv: encryptedSnapshot.iv,
    encryptedSnapshot: encryptedSnapshot.ciphertext,
  })
  await transaction.done
  window.dispatchEvent(new Event('haynes:offline-queue'))
  return command.id
}

export async function listOfflineCommands(userId: string) {
  const db = await database
  const commands = await db.getAllFromIndex('commands', 'by-user', userId)
  return commands
    .map((command) => ({
      id: command.id,
      userId: command.userId,
      grantId: command.grantId,
      requestId: command.requestId,
      sequence: command.sequence,
      commandType: command.commandType,
      status: command.status,
      result: command.result,
      createdAt: command.createdAt,
    }))
    .sort((left, right) => left.createdAt.localeCompare(right.createdAt))
}

export async function discardOfflineConflict(userId: string, commandId: string) {
  const db = await database
  const command = await db.get('commands', commandId)
  if (command?.userId !== userId || command?.status !== 'conflict') {
    throw new Error('Offline conflict not found')
  }
  await db.delete('commands', commandId)
  window.dispatchEvent(new Event('haynes:offline-queue'))
}

export async function pendingCommandsForGrant(userId: string, grantId: string) {
  const db = await database
  const commands = await db.getAllFromIndex('commands', 'by-grant', grantId)
  const pending = commands.filter((command) => command.userId === userId && command.status === 'pending')
  pending.sort((left, right) => left.sequence - right.sequence)
  return Promise.all(
    pending.map(async (command) => ({
      ...command,
      payload: await decrypt<Record<string, unknown>>(
        command.userId,
        command.payloadIv,
        command.encryptedPayload,
      ),
    })),
  )
}

export async function grantsForUser(userId: string) {
  const db = await database
  const grants = await db.getAllFromIndex('grants', 'by-user', userId)
  const active: StoredGrant[] = []
  for (const grant of grants) {
    if (new Date(grant.expiresAt).getTime() <= Date.now()) {
      await deleteGrant(grant.id)
    } else {
      active.push(grant)
    }
  }
  return active
}

export async function listOfflineGrants(userId: string) {
  const grants = await grantsForUser(userId)
  return Promise.all(
    grants.map(async (grant) => ({
      ...grant,
      snapshot: await decrypt<MaterialRequest>(
        userId,
        grant.snapshotIv,
        grant.encryptedSnapshot,
      ),
    } satisfies LocalOfflineGrant)),
  )
}

export async function applySyncResults(
  grantId: string,
  requestVersion: number,
  results: Array<{ client_command_id: string; status: string; result: Record<string, unknown> | null }>,
) {
  const db = await database
  const transaction = db.transaction(['grants', 'commands'], 'readwrite')
  const grant = await transaction.objectStore('grants').get(grantId)
  if (grant) await transaction.objectStore('grants').put({ ...grant, requestVersion })
  for (const result of results) {
    if (result.status === 'applied') {
      await transaction.objectStore('commands').delete(result.client_command_id)
    } else {
      const command = await transaction.objectStore('commands').get(result.client_command_id)
      if (command) {
        await transaction.objectStore('commands').put({
          ...command,
          status: 'conflict',
          result: result.result,
        })
      }
    }
  }
  await transaction.done
  window.dispatchEvent(new Event('haynes:offline-queue'))
}
