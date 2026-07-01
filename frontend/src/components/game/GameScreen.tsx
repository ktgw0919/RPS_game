import { CollectingView } from '@/components/game/CollectingView';
import { JudgingView } from '@/components/game/JudgingView';
import { MatchEndView } from '@/components/game/MatchEndView';
import { RoundResultView } from '@/components/game/RoundResultView';
import { useGame } from '@/hooks/useGame';

export function GameScreen() {
  const { state } = useGame();
  const { match } = state;

  if (!match) return null;

  switch (match.state) {
    case 'COLLECTING':
      return <CollectingView />;
    case 'JUDGING':
      return <JudgingView />;
    case 'ROUND_RESULT':
      return <RoundResultView />;
    case 'MATCH_END':
      return <MatchEndView />;
    default:
      return null;
  }
}
