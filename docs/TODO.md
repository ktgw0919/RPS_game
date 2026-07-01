# Project Implementation TODO

> 方針: ディレクトリ構成・責務分割は `ARCHITECTURE.md` §2 を正とする（backend は `routers/` / `core/` / `game/` の3層 ＋ 汎用ヘルパ `utils.py`、`python-decouple` 設定、front は `Layout`/`components`）。
> 雛形（`docs/TEMPLATE_NOTES.md`）を下敷きに uv / Vite+TypeScript / Pydantic v2 / `lifespan` へ更新し、WebSocket 層を新規に追加する。

## Phase 1: Environment Setup & Simple API
- [x] Step 1: `uv` で FastAPI プロジェクトを初期化し、`pyproject.toml` に必須依存（fastapi, uvicorn, **pymongo[async]**, pydantic v2, python-decouple）を追加する。**redis は MVP 必須から外し optional-dependencies（extras `[redis]`）** に切り出す（スケール時のみ導入）
- [x] Step 2: 構成雛形メモ（`docs/TEMPLATE_NOTES.md`）を参考に backend 骨格を作成する（`app/main.py` を `lifespan` 化、`config.py` で decouple 読み込み＋**必須設定の欠落/型不正を起動時に検査して fail-fast**（単一 `Settings` に集約）、`database.py` に **PyMongo Async（`AsyncMongoClient`）** 接続を分離、`routers/` ディレクトリを用意）
- [x] Step 3: MongoDB 接続テストと `.env` 整備（必須: `DB_URL`, `DB_NAME` ／ 任意: `REDIS_URL`, `ALLOW_CPU`, `CORS_ORIGINS`, 運用調整値 `HOST_TRANSFER_GRACE_SEC`/`GHOST_TTL_SEC`/`ROOM_IDLE_TTL_SEC`/`ROOM_CREATE_RATE_*`（既定値つき））。プロトコル/体感の固定値は `core/constants.py` 定数とする。ローカルは `docker-compose`（Mongo）と Atlas の両方式を README に併記し、`.env.example` を同梱する
- [x] Step 4: React プロジェクトを **Vite + TypeScript（strict）** で初期化し、Tailwind CSS をセットアップする
- [x] Step 5: HTTP REST API（`routers/rooms.py`）で「ルーム作成」「ルーム参加（バリデーション）」を Pydantic v2 モデルで実装する（エンドポイント・I/O・表示名制約は `ARCHITECTURE.md` §3.1/§3.2 を正とする）。応答で `playerId` / `playerToken` と初期 `RoomView` を返す（`core/security.py`）。ルーム作成には簡易レート制限を設ける
- [x] Step 6: 品質ツールと CI を整備する（backend: ruff + mypy + pytest、frontend: ESLint + Prettier + tsc strict、GitHub Actions で lint・型・test を自動実行）

## Phase 2: WebSocket & Game Loop (MVP)
> 雛形には WebSocket が無いため、この層は新規設計する。
- [x] Step 1: `core/connection_manager.py` に `ConnectionManager` を実装し、`routers/ws.py` で接続・切断・ルーム単位のブロードキャストを扱う。**トークンは接続直後の最初の `JOIN` メッセージで提示**（`?token=` クエリは不採用）し検証する。最初が `JOIN` でない/未知トークンは `INVALID_TOKEN` で切断。同一トークンの再接続は既存プレイヤーへ再紐付けし、接続直後に `STATE_SYNC` でスナップショットを返す
- [x] Step 2: `core/state_store.py` に `GameStateStore` インターフェースと**インメモリ実装**を作り、ゲーム進行状態をこの抽象越しに読み書きする（正本はインメモリ）
- [ ] Step 3:（任意・スケール時）`GameStateStore` の Redis 実装と複数 WebSocket 間の pub/sub を追加する。MVP では未実装でよい
- [x] Step 4: ドメインモデル（`Room` / `Player` / `Match` / `Round` / `MatchConfig` / `Hand`）と Match 状態遷移（FSM: COLLECTING → JUDGING → ROUND_RESULT → 継続/MATCH_END）を `models.py` と状態ストアに実装する。MVP は `rule_type = NORMAL` のみ
- [x] Step 5: ハートビート（`PING`/`PONG`・間隔 25s / タイムアウト 60s は front/back 共有定数）と封筒形式 `{type, payload, v}` の WS メッセージ I/O を整備する
- [x] Step 6: ホスト設定（`UPDATE_SETTINGS` → `SETTINGS_UPDATE`）を実装する。制限時間・進行モード（自動/手動）・あいこ上限などを `MatchConfig` で管理し、`START_GAME` で確定する
- [x] Step 7: クライアントからの `SUBMIT_HAND` を受け取り、`GameStateStore`（インメモリ）に一時保存するロジックの実装。送信者トークンと本人の一致を検証する（締切前は上書き可）
- [x] Step 8: 汎用的なじゃんけん勝敗判定エンジン（`game/engine.py`）を作成する（まずは通常ルール）。純粋ロジックとして pytest でユニットテストする
- [x] Step 9: サーバー側ラウンドタイマー（締切＝権威）を `asyncio.Task` で実装。`ROUND_START` で `deadline_at` / `server_now` を送り、生存者全員提出時はタイマーを `task.cancel()` して早期確定。判定はルーム単位 `asyncio.Lock` 内で「未判定か」を確認して1回だけ実行（二重判定防止）。生存者全員提出 or 締切到達で `ROUND_RESULT`/`MATCH_END` をブロードキャスト。未提出は敗北/脱落、あいこは進行モードに従い再ラウンド（手動時は `NEXT_ROUND` 待ち）。NORMAL のマッチ終了は `MatchConfig.normal_end_mode`（脱落式 ELIMINATION / 1ラウンド確定 SINGLE_ROUND）に従う
- [x] Step 10: `lifespan` 常駐タスクを実装する（確定値は `ARCHITECTURE.md` §10: 走査間隔60s・無操作30分・ホスト移譲猶予30s・ゴーストTTL120s）。①ルーム破棄スイープ（`ROOM_IDLE_TTL_SEC` 無操作で `CLOSED`＋`ROOM_CLOSED` 通知）②ホスト切断時の自動移譲（`HOST_TRANSFER_GRACE_SEC` 経過後、最古参の接続中プレイヤーへ＋`HOST_CHANGED`）③ハートビート欠落で `DISCONNECTED` 化＋WAITING の `GHOST_TTL_SEC` 超過ゴースト除去。終了時に全タスクを `cancel()` する
- [x] Step 11: `ERROR` コードを front/back 共有の定数として実装する（`ARCHITECTURE.md` §4.1 の一覧を正とする）
- [x] Step 12: テストを整備する（`ARCHITECTURE.md` §11）。①判定エンジン/各ルールの純粋関数テスト ②FSM 遷移の状態ストア単体テスト ③WebSocket 結合テスト（`pytest-asyncio` + Starlette テストクライアントで締切到達・早期確定・再接続復元・`SESSION_REPLACED`・二重判定防止）を CI で実行
- [x] Step 13:（開発/デモ用 CPU）`ALLOW_CPU`（`.env`）を `Settings` に追加し、ホストの `ADD_CPU`/`REMOVE_CPU`（ロビーのみ・`ALLOW_CPU=false` は `CPU_NOT_ALLOWED`）で CPU プレイヤーを増減する。CPU はトークン/接続を持たないプレイヤーとして `Player`（`is_cpu`/`cpu_strategy`）に追加し、定員・開始最小人数にカウントする。`ROUND_START` 時に `game/cpu.py` で手を生成（MVP は `RANDOM`）し、締切前に短いランダム遅延で自動提出する。ホスト自動移譲・破棄スイープ・切断検知から CPU を除外する。CPU を含めたソロ進行を結合テストで検証する（`ARCHITECTURE.md` §3/§5/§6/§10）

## Phase 3: Special Rules Implementation
- [x] Step 1: 「少数派勝利ルール (Minority Rule)」の集計・判定アルゴリズムの実装とテスト（`game/rules/minority.py`）。生存者が閾値以下で NORMAL 決着へ移行（閾値・タイミングは `MatchConfig`）
- [x] Step 2: 「代表ルール (Boss Battle)」の非対称ゲームロジックの実装（`game/rules/boss_battle.py`）。ボスはホスト指名・非参加者（勝者カウント対象外）
- [x] Step 3: 「1対1トーナメント」の自動進行（ブラケット生成・奇数は bye・ペアごとの独立判定・ペア内あいこ再戦）の実装（`game/rules/tournament.py`）。並行するペアはラウンド系メッセージの `segment_id`（`ARCHITECTURE.md` §4）で識別する
- [ ] Step 4: 各ルールの「あいこ」再戦フローと `MatchConfig.max_draw_rounds`（あいこ回数の上限到達時は引き分け終了）の厳密化。各ルールをユニットテストで検証

## Phase 4: Frontend Integration & Polish
- [x] Step 1: `src/hooks/useWebSocket.ts` を作成し、WebSocket でゲームループを扱う。ゲーム状態は React Context + `useReducer` で管理し、`STATE_SYNC` をスナップショット・他メッセージを差分アクションとして reducer で適用する（SWR は MVP では導入せず、REST は軽量 fetch ラッパーのみ）
- [x] Step 2: `src/types` に WebSocket メッセージ型・ドメイン型（`PlayerView`/`RoomView`/`MatchView` 等）を定義し、Pydantic v2 モデル・封筒形式 `{type, payload, v}` と整合させる。`ErrorCode`（`SESSION_REPLACED` 含む）を front/back 共有定数として定義し、時刻は UTC ISO8601（ミリ秒・`Z`）、`segment_id` は任意フィールドとして型に含める
- [x] Step 3: ロビー画面、ホスト設定画面、手札選択画面、結果発表画面のUIコンポーネント実装（`Layout`/`components` 構成を踏襲）。ホスト設定は `UPDATE_SETTINGS`/`SETTINGS_UPDATE` と連動し全員にライブ反映、手動進行時はホストに「次へ」操作を表示。観戦者は手の提出 UI を出さず結果を読み取り専用で表示する
- [x] Step 4: 各種エッジケース（途中で通信が切れたプレイヤーの再接続復帰、未提出のタイムアウト、ホスト切断時の移譲）のバグフィックス。クライアントは `deadline_at` と `server_now` の差分で残り時間を表示する
- [x] Step 5:（開発/デモ用 CPU）ロビーに「＋CPUを追加」ボタン（ホストのみ・`ALLOW_CPU` 有効時のみ・`ADD_CPU`/`REMOVE_CPU` と連動）と、参加者一覧の CPU バッジ（🤖）＋削除ボタンを実装する。`PlayerView.is_cpu` を `types` に追加し、ソロ＋CPU で「ゲーム開始」が活性化することを確認する（`SCREENS.md` §4/§5）

## Phase 5: Match History Read & UI
> 書き込み（`match_history` 永続化）は完了済み。本フェーズでルーム単位の読み取り REST とロビー UI を追加する。グローバルスコアボードは対象外（アカウント連携後フェーズ）。
- [x] Step 1: `MatchHistoryRepository.list_by_room` と `GET /rooms/{code}/matches` を実装（Pydantic DTO・`limit` クエリ・`ended_at` 降順・DB 障害時 `503`）。**インメモリのルーム有無に依存せず** MongoDB を `room_code` で直接検索する。pytest で書き込み→読み取り結合テスト
- [x] Step 2: `ARCHITECTURE.md` §3.1 / §4.1 の確定内容に沿い、front `types` / `api.ts` / **SWR 導入**（`useMatchHistory` フック）
- [x] Step 3: ロビーに `MatchHistoryPanel`（`SCREENS.md` §4.6）。`WAITING` 表示時・`RETURN_TO_LOBBY` 後に再取得。`MATCH_END` 画面には履歴を出さない（直前結果は WS の `MATCH_END` で表示済み）
- [x] Step 4: `REQUIREMENTS.md` の対戦履歴閲覧を `[x]`、`README.md` 実装状況を更新

## MVP 残タスク（Phase 1–4 外の仕上げ）

設計上は MVP 要件だが、上記フェーズの Step には含まれていない、または UI のみ未着手の項目。

- [x] **`match_history` 永続化**（`ARCHITECTURE.md` §6）: マッチ終了時に MongoDB へ確定結果を保存（`core/match_history.py`）
- [x] **QR コード共有**（`SCREENS.md` §4.1.1）: 参加リンク（`/join/:code`）の QR をモーダル表示（`ShareQrModal` / `react-qr-code`）。コード・リンクのコピーは `SharePanel` に実装済み
- [x] **ルーム操作 UI**（`SCREENS.md` §4.7）: `RoomActionsPanel`・`useExitRoom`・退室／別ルーム参加／新規作成（試合中は移動系非活性）
- [ ] **フロント E2E テスト**（任意）: Playwright 等でのブラウザ結合テスト
