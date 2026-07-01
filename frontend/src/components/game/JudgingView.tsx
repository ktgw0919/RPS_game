import { Panel } from '@/components/ui/Panel';

export function JudgingView() {
  return (
    <Panel title="判定中">
      <div className="flex flex-col items-center gap-3 py-6">
        <div
          className="h-10 w-10 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent"
          aria-hidden
        />
        <p className="text-sm text-slate-300">じゃんけんを判定しています…</p>
      </div>
    </Panel>
  );
}
