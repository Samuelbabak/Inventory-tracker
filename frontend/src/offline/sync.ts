import { api } from '../api/client'
import type { MaterialRequest, OfflineCommandResult } from '../api/types'
import {
  applySyncResults,
  grantsForUser,
  pendingCommandsForGrant,
  updateOfflineSnapshot,
} from './store'

function resultRequest(result: OfflineCommandResult) {
  const request = result.result?.request
  if (!request || typeof request !== 'object' || !('id' in request)) return null
  return request as MaterialRequest
}

export async function synchronizeOfflineQueue(userId: string) {
  const grants = await grantsForUser(userId)
  for (const grant of grants) {
    const pending = await pendingCommandsForGrant(userId, grant.id)
    if (pending.length === 0) continue
    const response = await api.syncOfflineCommands(
      grant.id,
      grant.deviceId,
      pending.map((command) => ({
        client_command_id: command.id,
        sequence: command.sequence,
        command_type: command.commandType,
        payload: command.payload,
      })),
    )
    await applySyncResults(grant.id, response.request_version, response.commands)
    let latestRequest: MaterialRequest | null = null
    for (const result of response.commands) {
      latestRequest = resultRequest(result) ?? latestRequest
    }
    if (latestRequest) await updateOfflineSnapshot(grant.id, latestRequest)
  }
}
