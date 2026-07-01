import { useGame } from '@/hooks/useGame';

export function useWsConnected(): boolean {
  const { state } = useGame();
  return state.connectionStatus === 'connected';
}

/** Host-only controls that require an active WebSocket (Phase 6 Step 2). */
export function useHostControlsEnabled(): boolean {
  const { state } = useGame();
  const { room, you, connectionStatus } = state;
  if (!room || !you || connectionStatus !== 'connected') return false;
  return you.is_host && you.player_id === room.host_player_id;
}
