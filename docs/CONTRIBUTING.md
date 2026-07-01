# Contributing / 開発ワークフロー

本プロジェクトの Git 運用方針を定める。設計の正本は `docs/`（`REQUIREMENTS.md` / `ARCHITECTURE.md` / `SCREENS.md` / `TODO.md`）であり、本書はそれらを変更・実装する際の**進め方**を規定する。

> 開発環境は **Windows / PowerShell** を前提とする（`.cursor/rules/00-project.mdc`）。コマンド例は PowerShell 構文で示す。

## 1. リモートは GitHub を使う（必須）

ローカル Git だけでは不十分で、**GitHub（private 可）の利用を必須**とする。

- **CI が GitHub 前提**: `.github/workflows/ci.yml` は `push: [main]` と `pull_request` で起動し、backend（ruff / mypy / pytest）と frontend（eslint / prettier / build）を自動実行する（`ARCHITECTURE.md` §11）。リモートが無いとこの品質ゲートが機能しない。
- **PR 単位の整合担保**: 後述の「front/back 同一 PR ルール」は PR とレビュー/CI があって初めて担保できる。
- **資産保全**: ゲーム進行状態は揮発前提（MVP）だが、コード資産はリモートで保全する。

## 2. ブランチ戦略（GitHub Flow）

- **`main` を唯一の長期ブランチ**とし、常にグリーン（CI 通過）を保つ。`develop` は設けない（MVP では過剰）。
- 作業は短命な feature ブランチで行い、**PR 経由でのみ `main` へマージ**する。`main` への直接 push は禁止。
- **ブランチ保護**（GitHub 側設定）: `main` で「PR 必須」「CI の必須通過（required status checks に `Backend (ruff / mypy / pytest)` と `Frontend (eslint / prettier / build)` を指定）」を有効化する。

### ブランチ命名

`type/簡潔な内容`（必要なら Phase/Step を添える）。

| 例 | 用途 |
|---|---|
| `feat/ws-connection-manager` | 機能追加 |
| `feat/phase2-step9-round-timer` | TODO の Phase/Step 対応 |
| `fix/round-timer-cancel` | バグ修正 |
| `docs/contributing` | ドキュメント |
| `chore/ci-cache` | 雑務・基盤 |

## 3. コミット規約（Conventional Commits）

`type(scope): subject` 形式で記述する。`subject` は命令形・現在形で簡潔に。

```
feat(ws): add ConnectionManager and JOIN token validation
fix(game): cancel round timer on early finish to avoid double judge
docs(arch): define set S for start condition (§4.2)
test(engine): cover three-kinds draw in normal rule
chore(ci): cache uv and npm dependencies
```

- **type**: `feat` / `fix` / `docs` / `test` / `refactor` / `chore` / `ci` / `perf` / `style`。
- **scope**（推奨・責務層に合わせる）: `ws` / `core` / `game` / `rooms` / `front` / `types` / `arch` / `docs` など。
- 破壊的変更は `feat(ws)!:` のように `!` を付ける（または本文に `BREAKING CHANGE:`）。

## 4. front/back 型の同一 PR ルール（重要）

WS payload / `ErrorCode` / `MatchConfig` を増減・変更する場合は、**frontend（`src/types`）と backend（Pydantic v2 モデル）を同一のコミット/PR で更新**する（封筒形式 `{ type, payload, v:1 }` と構造を一致させる）。

- `ErrorCode` の正本: `ARCHITECTURE.md` §4.1
- `MatchConfig` の範囲・既定の正本: `ARCHITECTURE.md` §9
- 出典: `.cursor/rules/00-project.mdc` / `.cursor/rules/backend.mdc`

## 5. プルリクエスト / マージ

1. feature ブランチを push し、PR を作成する。
2. PR 説明に「**変更概要**」「**関連する `docs/` 節 / TODO Step**」「**動作確認/テスト**」を書く。
3. CI（lint・型・test・build）を通す。**赤い PR はマージしない**。
4. ソロでもセルフレビュー（Files changed を一読）を行う。
5. **Squash and merge** を基本とする（PR 単位で履歴が1コミットにまとまり、Conventional Commits と整合）。マージ後はブランチを削除する。

### PR 説明テンプレ（人間・Agent 共通）

```markdown
## Summary
- （変更の要点を 1–3 行）

## Test plan
- [x] backend: `uv run ruff check .` / `ruff format --check .` / `mypy app` / `pytest`
- [x] frontend: `npm run lint` / `npm run format:check` / `npm run build`
- [ ] （必要なら手動確認）

## Related TODO Step
- Phase N Step M（`docs/TODO.md`）または MVP 残タスクの項目名
```

## 6. コミット前のローカルチェック

PR 前にローカルで品質チェックを通しておく（CI と同等）。

```powershell
# backend
cd backend; uv run ruff check .; uv run ruff format --check .; uv run mypy app; uv run pytest
# frontend
cd frontend; npm run lint; npm run format:check; npm run build
```

- **新規/変更ロジックには対応する層のテストを追加/更新**する（判定→純粋関数、FSM→状態ストア単体、WS フロー→結合。`.cursor/rules/backend.mdc` / `ARCHITECTURE.md` §11）。

## 7. タグ / リリース

- 各 Phase（`docs/TODO.md` の Phase 1–4）完了時に **SemVer タグ**を打つ（例: MVP 完了で `v0.1.0`）。
- CHANGELOG は Conventional Commits から後で自動生成できる（MVP では任意）。

## 8. 秘匿情報・`.gitignore`

- **`.env`（`DB_URL` 等の秘匿値）は絶対にコミットしない**。テンプレートとして `*.env.example` のみをコミットする（`.gitignore` で `.env` / `.env.*` を除外し `!.env.example` で例外化済み）。
- `playerToken` 等の秘匿値は URL・クエリ・ログに残さない方針（`ARCHITECTURE.md` §3）と同様、認証情報・接続文字列をリポジトリに残さない。
- 生成物・キャッシュ（`__pycache__/` / `.venv/` / `.mypy_cache/` / `node_modules/` / `dist/` など）は `.gitignore` 済み。新たな生成物が出たら `.gitignore` を更新する。

## 9. 実装完了時のドキュメント同期

`docs/TODO.md` の Step を完了した PR では、進捗ドキュメントを実装と同じ PR に含める。手順の詳細は `.cursor/rules/docs-sync.mdc` を正とする。

### チェックリスト

- [ ] `docs/TODO.md` の該当 Step を `[x]`（部分完了なら `[ ]` のまま「MVP 残タスク」へ追記）
- [ ] Phase 内の必須 Step がすべて `[x]` なら `README.md` の実装状況を更新
- [ ] ユーザーが体感できる製品能力が満たされたなら `docs/REQUIREMENTS.md` の該当項目を `[x]`（部分実装は注記）
- [ ] 画面・導線を変更したなら `docs/SCREENS.md` を更新（未実装注記の追加/削除）
- [ ] WS / FSM / ドメインの**設計**を変えたなら `docs/ARCHITECTURE.md` を更新（§番号で追記）
- [ ] backend の構成・起動手順を変えたなら `backend/README.md` を更新

### コミット例

```
docs(todo): mark Phase 2 Step 9 done
docs(readme): reflect Phase 2 completion
docs(req): check off MVP game loop; note match_history pending
```

### 設計ドキュメントと進捗ドキュメントの区別

| 種類 | ファイル | Step 完了時 |
|------|----------|-------------|
| 進捗の正本 | `docs/TODO.md` | 必ず更新 |
| 進捗サマリー | `README.md`, `docs/REQUIREMENTS.md` | 条件を満たしたとき |
| 設計の正本 | `docs/ARCHITECTURE.md` | プロトコル・型・FSM を変えたときのみ |

## 10. Cursor Agent による Git 操作

Cursor Agent（以降 **Agent**）が `docs/TODO.md` の実装や修正を行うとき、**人間が毎回「コミットして」「PR を作って」と指示しなくても**、完了したタスクについては本節と `.cursor/rules/agent-git.mdc` に従い Git 操作を進める。

### 10.1 役割分担

| 操作 | Agent | 人間（GitHub） |
|------|-------|----------------|
| feature ブランチ作成 | ✅ タスク開始〜完了時 | — |
| コミット・push | ✅ 完了かつ §6 通過後 | — |
| PR 作成 | ✅ | — |
| CI 失敗の修正 push | ✅ 同一 PR ブランチ | — |
| PR レビュー・マージ | — | ✅ Squash merge（§5） |
| `main` への直接 push | ❌ 禁止 | — |

**マージは Agent が行わない。** CI green と内容確認のあと、人間が GitHub 上でマージする。

### 10.2 自動で PR まで行う条件

次の**すべて**を満たすとき、追加の Git 指示なしで PR を作成する。

1. **実装系タスク**（TODO Step・MVP 残タスク・バグ修正・依頼されたドキュメント整備など）。質問・調査のみは対象外。
2. **スコープ完了** — Step の場合は受け入れ条件・テスト・`docs-sync.mdc` の進捗更新まで済んでいる（§9）。
3. **ローカル品質チェック**（§6）通過。コード変更が無い純ドキュメント PR は §6 のコード系を省略可。
4. **無関係な WIP** を同じ PR に含めない。

**部分実装**のときは `TODO.md` の Step を `[x]` にせず、**PR は作らない**（「MVP 残タスク」への追記のみ）。

### 10.3 典型フロー（Agent）

1. `git fetch` / `main` を最新化
2. `feat/phaseN-stepM-...` 等でブランチ作成（§2）
3. 実装 + テスト + 進捗ドキュメント（§9 / `docs-sync.mdc`）
4. §6 を実行
5. コミット（§3）→ `git push -u origin HEAD` → `gh pr create`（§5 テンプレ）
6. PR URL をユーザーに報告
7. CI が落ちたら同一ブランチで修正して再 push（人間の指示を待たない）
8. 人間がマージしたら、次タスク前または依頼時に `main` を `git pull` で同期

### 10.4 Agent が行わないこと

- `main` への直接 push、force push、hard reset、`git config` 変更
- テスト・lint 未通過のままの PR 作成
- `.env` 等の秘匿ファイルのコミット
- ユーザーが「まだ PR にしない」と明示した場合

詳細な分岐（既存 PR への push のみ、マージ後同期、WIP 保存など）は `.cursor/rules/agent-git.mdc` を正とする。
