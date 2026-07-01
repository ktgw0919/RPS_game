"""Pure start-condition logic (ARCHITECTURE.md §4.2).

Side-effect free domain helpers: given a Room snapshot, compute the eligible
player set S and the minimum players required to start by rule type. The game
layer must not depend on routers/core (.cursor/rules/backend.mdc); it only reads
the shared domain models.

`START_GAME` (Phase 2 Step 6) re-validates these under the room lock before
committing the match (ARCHITECTURE.md §4/§7.1).
"""

from __future__ import annotations

from app.game.rules.boss_battle import boss_start_ok
from app.models import ConnectionState, Room, RuleType

# Minimum players to start, by rule (ARCHITECTURE.md §4.2). MVP enables NORMAL;
# the others are kept ready ("器") for Phase 3. BOSS additionally requires the
# nominated boss to be in S (§4.2/§8) — enforced when BOSS is implemented.
MIN_PLAYERS_BY_RULE: dict[RuleType, int] = {
    RuleType.NORMAL: 2,
    RuleType.MINORITY: 3,
    RuleType.BOSS: 2,
    RuleType.TOURNAMENT: 2,
}


def eligible_player_ids(room: Room) -> list[str]:
    """Set S: non-spectators that are CONNECTED or CPU (ARCHITECTURE.md §4.2).

    Order follows member insertion order so callers/tests are deterministic.
    """
    return [
        player.player_id
        for player in room.members.values()
        if not player.is_spectator
        and (player.is_cpu or player.connection_state is ConnectionState.CONNECTED)
    ]


def min_players_for(rule_type: RuleType) -> int:
    """Minimum size of S required to start the given rule (ARCHITECTURE.md §4.2)."""
    return MIN_PLAYERS_BY_RULE[rule_type]


def can_start(room: Room) -> bool:
    """True if the room's S meets the minimum-players gate for its rule (§4.2)."""
    eligible = eligible_player_ids(room)
    if len(eligible) < min_players_for(room.config.rule_type):
        return False
    if room.config.rule_type is RuleType.BOSS:
        return boss_start_ok(eligible, room.config.boss_player_id)
    return True
