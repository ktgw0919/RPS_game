import { useCallback, useMemo } from 'react';

import { useDebouncedCallback } from '@/hooks/useDebouncedCallback';
import { useGame } from '@/hooks/useGame';
import {
  ADVANCE_MODE_LABELS,
  MINORITY_TIMING_LABELS,
  NORMAL_END_LABELS,
  RULE_LABELS,
} from '@/lib/labels';
import { eligiblePlayerIds, MATCH_CONFIG_LIMITS, minPlayersFor } from '@/lib/matchConfig';
import type {
  MatchConfig,
  MatchConfigUpdate,
  MinorityFinishTiming,
  PlayerView,
  RuleType,
} from '@/types';

interface SettingsPanelProps {
  config: MatchConfig;
  editable: boolean;
  members: PlayerView[];
}

export function SettingsPanel({ config, editable, members }: SettingsPanelProps) {
  const { send } = useGame();

  const pushUpdate = useCallback(
    (patch: MatchConfigUpdate) => {
      send('UPDATE_SETTINGS', { config: patch });
    },
    [send],
  );

  const debouncedPush = useDebouncedCallback(pushUpdate, 300);

  const onSlider = (field: keyof MatchConfig, value: number, debounce = true) => {
    const patch = { [field]: value } as MatchConfigUpdate;
    if (debounce) debouncedPush(patch);
    else pushUpdate(patch);
  };

  const eligible = useMemo(() => eligiblePlayerIds(members), [members]);

  const minorityThresholdMax = Math.max(
    MATCH_CONFIG_LIMITS.minority_finish_threshold.min,
    eligible.length - 1,
  );

  const bossCandidates = useMemo(
    () => members.filter((m) => eligible.includes(m.player_id)),
    [members, eligible],
  );

  const ruleOptions = useMemo(
    () =>
      (Object.keys(RULE_LABELS) as RuleType[]).map((key) => ({
        value: key,
        label: RULE_LABELS[key],
      })),
    [],
  );

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-400">
        {editable ? 'ゲーム設定（変更は全員に即時反映）' : 'ホストが設定中（読み取り専用）'}
      </p>

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-slate-400">ルール</span>
        <select
          disabled={!editable}
          value={config.rule_type}
          onChange={(e) => pushUpdate({ rule_type: e.target.value as RuleType })}
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 disabled:opacity-60"
        >
          {ruleOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>

      {config.rule_type === 'NORMAL' ? (
        <fieldset className="flex flex-col gap-2">
          <legend className="text-sm text-slate-400">終了方式</legend>
          <div className="flex gap-2">
            {(['ELIMINATION', 'SINGLE_ROUND'] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                disabled={!editable}
                onClick={() => pushUpdate({ normal_end_mode: mode })}
                className={`flex-1 rounded-lg border px-3 py-2 text-sm transition ${
                  config.normal_end_mode === mode
                    ? 'border-indigo-400 bg-indigo-500/20 text-indigo-200'
                    : 'border-slate-700 text-slate-300'
                } disabled:opacity-60`}
              >
                {NORMAL_END_LABELS[mode]}
              </button>
            ))}
          </div>
        </fieldset>
      ) : null}

      {config.rule_type === 'MINORITY' ? (
        <>
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="text-slate-400">NORMAL 移行閾値（生存者数）</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={
                  !editable ||
                  config.minority_finish_threshold <=
                    MATCH_CONFIG_LIMITS.minority_finish_threshold.min
                }
                onClick={() =>
                  onSlider('minority_finish_threshold', config.minority_finish_threshold - 1, false)
                }
                className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-700 text-lg disabled:opacity-40"
              >
                −
              </button>
              <span className="w-8 text-center font-mono text-slate-100">
                {config.minority_finish_threshold}
              </span>
              <button
                type="button"
                disabled={!editable || config.minority_finish_threshold >= minorityThresholdMax}
                onClick={() =>
                  onSlider('minority_finish_threshold', config.minority_finish_threshold + 1, false)
                }
                className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-700 text-lg disabled:opacity-40"
              >
                +
              </button>
            </div>
          </div>
          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm text-slate-400">NORMAL 移行タイミング</legend>
            <div className="flex gap-2">
              {(['IMMEDIATE', 'NEXT_MATCH'] as const).map((timing) => (
                <button
                  key={timing}
                  type="button"
                  disabled={!editable}
                  onClick={() => pushUpdate({ minority_finish_timing: timing })}
                  className={`flex-1 rounded-lg border px-3 py-2 text-sm transition ${
                    config.minority_finish_timing === timing
                      ? 'border-violet-400 bg-violet-500/20 text-violet-200'
                      : 'border-slate-700 text-slate-300'
                  } disabled:opacity-60`}
                >
                  {MINORITY_TIMING_LABELS[timing as MinorityFinishTiming]}
                </button>
              ))}
            </div>
          </fieldset>
          <p className="text-xs text-slate-500">
            開始には {minPlayersFor('MINORITY')} 人以上必要です
          </p>
        </>
      ) : null}

      {config.rule_type === 'BOSS' ? (
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-slate-400">ボス（代表）</span>
          <select
            disabled={!editable}
            value={config.boss_player_id ?? ''}
            onChange={(e) => pushUpdate({ boss_player_id: e.target.value ? e.target.value : null })}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 disabled:opacity-60"
          >
            <option value="">未選択</option>
            {bossCandidates.map((m) => (
              <option key={m.player_id} value={m.player_id}>
                {m.display_name}
                {m.is_cpu ? ' 🤖' : ''}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <label className="flex flex-col gap-2 text-sm">
        <span className="flex justify-between text-slate-400">
          <span>制限時間</span>
          <span className="font-mono text-slate-200">{config.round_time_limit_sec}秒</span>
        </span>
        <input
          type="range"
          disabled={!editable}
          min={MATCH_CONFIG_LIMITS.round_time_limit_sec.min}
          max={MATCH_CONFIG_LIMITS.round_time_limit_sec.max}
          step={MATCH_CONFIG_LIMITS.round_time_limit_sec.step}
          value={config.round_time_limit_sec}
          onChange={(e) => onSlider('round_time_limit_sec', Number(e.target.value))}
          className="w-full accent-indigo-500 disabled:opacity-60"
        />
      </label>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm text-slate-400">進行</legend>
        <div className="flex gap-2">
          {(['AUTO', 'MANUAL'] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              disabled={!editable}
              onClick={() => pushUpdate({ round_advance_mode: mode })}
              className={`flex-1 rounded-lg border px-3 py-2 text-sm transition ${
                config.round_advance_mode === mode
                  ? 'border-indigo-400 bg-indigo-500/20 text-indigo-200'
                  : 'border-slate-700 text-slate-300'
              } disabled:opacity-60`}
            >
              {ADVANCE_MODE_LABELS[mode]}
            </button>
          ))}
        </div>
      </fieldset>

      {config.round_advance_mode === 'AUTO' ? (
        <label className="flex flex-col gap-2 text-sm">
          <span className="flex justify-between text-slate-400">
            <span>結果表示時間</span>
            <span className="font-mono text-slate-200">{config.result_display_sec}秒</span>
          </span>
          <input
            type="range"
            disabled={!editable}
            min={MATCH_CONFIG_LIMITS.result_display_sec.min}
            max={MATCH_CONFIG_LIMITS.result_display_sec.max}
            step={MATCH_CONFIG_LIMITS.result_display_sec.step}
            value={config.result_display_sec}
            onChange={(e) => onSlider('result_display_sec', Number(e.target.value))}
            className="w-full accent-indigo-500 disabled:opacity-60"
          />
        </label>
      ) : null}

      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="text-slate-400">あいこ上限</span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={
              !editable || config.max_draw_rounds <= MATCH_CONFIG_LIMITS.max_draw_rounds.min
            }
            onClick={() => onSlider('max_draw_rounds', config.max_draw_rounds - 1, false)}
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-700 text-lg disabled:opacity-40"
          >
            −
          </button>
          <span className="w-8 text-center font-mono text-slate-100">{config.max_draw_rounds}</span>
          <button
            type="button"
            disabled={
              !editable || config.max_draw_rounds >= MATCH_CONFIG_LIMITS.max_draw_rounds.max
            }
            onClick={() => onSlider('max_draw_rounds', config.max_draw_rounds + 1, false)}
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-700 text-lg disabled:opacity-40"
          >
            +
          </button>
        </div>
      </div>

      <p className="text-xs text-slate-500">※ 設定はゲーム開始時に確定します</p>
    </div>
  );
}
