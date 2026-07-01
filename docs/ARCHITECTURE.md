# Architecture Specification

## 1. Technical Stack
- **Frontend**: React 18 + **Vite** + **TypeScript（strict モード）** (SPA), Tailwind CSS
  - リアルタイム同期: WebSocket（`useWebSocket` カスタムフック）
  - **ゲーム状態管理**: React Context + `useReducer`。`STATE_SYNC` をスナップショット、その他 WS メッセージを差分アクションとして reducer で適用する（追加ライブラリは導入しない）。
  - **REST 取得（SWR）**: Phase 1–4（MVP）では見送り、軽量な `fetch` ラッパーのみ。**Phase 5**（対戦履歴読み取り）で SWR を導入し、`GET /rooms/{code}/matches` の取得に用いる。グローバルスコアボードはアカウント連携後フェーズで SWR を拡張利用する。
- **Backend**: FastAPI (Python 3.12+), **`uv` + `pyproject.toml`** for dependency management
  - **Pydantic v2** でスキーマ定義（`model_config` / `field_validator`）
  - アプリのライフサイクルは `lifespan`（`@app.on_event` は使用しない）
- **Database**: MongoDB（**PyMongo Async**: `AsyncMongoClient` を使う公式の非同期 API。Motor は将来非推奨方向のため新規採用しない）。接続は `database.py` に分離。対戦履歴・スコアの永続化に利用
- **State (ゲーム進行状態)**: **MVP では単一プロセスのインメモリ**（`ConnectionManager` / 状態ストアが保持）。
  - 状態アクセスは `GameStateStore` のような**インターフェース越しに抽象化**し、後から実装を差し替え可能にする。
  - **Redis は任意（スケール時のみ）**: 水平スケール（複数プロセス/ワーカー）で状態共有・WebSocket 間 pub/sub が必要になった段階で `GameStateStore` の Redis 実装を追加する。
  - ⚠️ 制約: インメモリ実装のままだと **uvicorn の `--workers` を 2 以上にすると状態が壊れる**（プロセス間で共有されない）。MVP は単一ワーカー前提とし、複数ワーカー時は Redis 実装が前提。
- **Config**: `python-decouple` で `.env`（`DB_URL`, `DB_NAME` は必須、`REDIS_URL`, `ALLOW_CPU` は任意）を読み込む。設定は単一の `Settings` オブジェクトに集約し、**起動時に必須値（`DB_URL`/`DB_NAME`）の欠落・型不正を検査して欠落なら即例外で起動失敗（fail-fast）**する。`ALLOW_CPU`（bool・既定 `true`）は開発/デモ用 CPU プレイヤーの有効化フラグで、**本番は `false` を推奨**する。
  - **CORS**: `CORS_ORIGINS`（任意・カンマ区切り、既定は開発用ローカルオリジン）で許可オリジンを設定する。
  - **運用調整値（任意・既定値つき）**: 環境ごとに変えうる値は `Settings` に**既定値つき**で持たせ、必要時のみ `.env` で上書きする（**fail-fast 検査の対象外**）。`HOST_TRANSFER_GRACE_SEC`（既定 `30`）/ `GHOST_TTL_SEC`（既定 `120`）/ `ROOM_IDLE_TTL_SEC`（既定 `1800`）/ `ROOM_CREATE_RATE_MAX`（既定 `10`）/ `ROOM_CREATE_RATE_WINDOW_SEC`（既定 `600`）。
  - **固定値（定数・`.env` に出さない）**: プロトコル不変条件や体感に直結する値は `core/constants.py` に定数として置く。ハートビート間隔/タイムアウト（§4）、WS メッセージサイズ上限（§11）、CPU 提出遅延（§6）、ルーム破棄スイープ実行間隔（§10）が該当する。ハートビート間隔は front/back 一致が必須のため frontend 側にも同値の定数を持ち**同時更新**する。
- **Protocol**: ルーム作成/参加は HTTP (REST API)、ゲームループは WebSocket

> 設計方針: 構成雛形メモ（`docs/TEMPLATE_NOTES.md`）の「`routers/` 分割・`Layout`/`components` 構成・`python-decouple` 設定・シードスクリプト」を踏襲する。
> ただし雛形は REST のみで非 CRUD ロジックが薄いため、責務分割は雛形の `utils/` 一括ではなく **`routers/`（I/O 境界）/ `core/`（接続・状態・セキュリティの基盤）/ `game/`（副作用の無い純粋なゲームドメイン）** の3層に拡張する（依存方向は `routers → core → game`、`game` は他層に依存しない）。`utils.py` は時刻整形・ルームコード生成などの**汎用ヘルパ専用**とし、ドメイン/基盤ロジックは置かない。リアルタイム層（`ws` ルーター・`ConnectionManager`・判定エンジン）は本プロジェクトで新規に追加する。
> また依存管理（uv）・フロント（Vite+TypeScript）・Pydantic v2・`lifespan` は雛形（pip / CRA / Pydantic v1）から本プロジェクト向けに更新する。

## 2. Directory Structure
```text
.
├── backend/                      # FastAPI Project (uv 管理)
│   ├── pyproject.toml            # Managed by uv
│   ├── .env                      # DB_URL, DB_NAME（必須）/ REDIS_URL, ALLOW_CPU, CORS_ORIGINS, *_TTL_SEC, ROOM_CREATE_RATE_* （任意・python-decouple）
│   └── app/
│       ├── main.py               # Entrypoint, CORS, lifespan, include_router
│       ├── config.py             # decouple による設定読み込み
│       ├── database.py           # MongoDB 接続 (PyMongo Async: AsyncMongoClient)
│       ├── models.py             # Pydantic v2 スキーマ (Room, Player, Match, Round, MatchConfig, Hand, CpuStrategy)
│       ├── routers/
│       │   ├── rooms.py          # REST: ルーム作成・参加バリデーション
│       │   └── ws.py             # WebSocket: ゲームループ
│       ├── core/
│       │   ├── connection_manager.py  # WebSocket 接続管理 (雛形に無い追加要素)
│       │   ├── state_store.py         # GameStateStore インターフェース + InMemory 実装 (Redis 実装は任意で追加)
│       │   ├── match_history.py       # Match 終了時の MongoDB 永続化 (match_history コレクション)
│       │   ├── security.py            # プレイヤートークンの発行・検証
│       │   └── constants.py           # プロトコル/体感の固定値 (ハートビート間隔・WS サイズ上限・CPU 遅延・スイープ間隔)
│       ├── game/
│       │   ├── engine.py         # 通常じゃんけん勝敗判定
│       │   ├── cpu.py            # CPU プレイヤーの手生成 (CpuStrategy。MVP は RANDOM)
│       │   └── rules/            # minority.py / boss_battle.py / tournament.py
│       ├── utils.py              # 汎用ヘルパのみ (時刻整形・ルームコード生成など。ドメイン/基盤ロジックは置かない)
│       └── seed.py               # 初期データ投入スクリプト (任意)
├── frontend/                     # React + Vite + TypeScript Project
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx              # エントリ (BrowserRouter)
│       ├── App.tsx
│       ├── components/           # Layout, Header, Footer, Lobby, GameBoard, HandPicker, ResultView
│       ├── hooks/                # useWebSocket.ts でリアルタイム同期
│       └── types/                # WebSocket メッセージ型・ドメイン型
└── docs/
    ├── ARCHITECTURE.md
    ├── REQUIREMENTS.md
    ├── SCREENS.md                 # 画面遷移仕様
    ├── TEMPLATE_NOTES.md          # 構成雛形メモ (旧 chapter9 由来)
    └── TODO.md
```

## 3. プレイヤー識別・セッション設計
認証は行わないが、**WebSocket の再接続後に同一プレイヤーへ再紐付けできる**ように、軽量なプレイヤートークンで識別する。

- **トークン発行**: ルーム作成/参加（REST: `routers/rooms.py`）の応答で `playerId` と `playerToken` をサーバーが発行する。`playerToken` は **128bit 以上のエントロピー**を持つランダム文字列とし（実装例: `secrets.token_urlsafe(32)`）、サーバーは状態ストアに保持して `JOIN` 時に定数時間比較で検証する。
- **クライアント保持**: フロントは `playerId` / `playerToken` / `roomCode` を **LocalStorage** に保存する（Cookie でも可）。
  - ⚠️ **セキュリティ前提**: 認証を行わないため `playerToken` が唯一の本人性であり、XSS で奪取されるとなりすましが可能になる。フロントは外部由来の文字列を `dangerouslySetInnerHTML` 等で DOM に注入しない方針とし、本番は `wss`/HTTPS 必須（§11）でトークンの平文流出を防ぐ。
- **WS への引き渡し**: WebSocket 接続直後の最初の `JOIN` メッセージでトークンを提示する（`?token=...` のクエリ方式は**採用しない**。クエリはアクセスログ/プロキシに残りトークンが漏洩しうるため）。サーバーはトークンを検証し、未知なら `ERROR`（`INVALID_TOKEN`）で接続を閉じる。最初のメッセージが `JOIN` でない接続も拒否する。
- **再接続の再紐付け**: 同一 `playerToken` での再接続は「切断していた既存プレイヤーの復帰」として扱い、新規プレイヤーとして二重登録しない。
- **同時接続（last-wins）**: 既存の接続が生きたまま同一 `playerToken` で新規接続が来た場合（多重タブ・別端末など）は、**新しい接続を採用し、古い接続には `ERROR`（`SESSION_REPLACED`）を送って閉じる**。これにより二重ブロードキャストやゴースト接続を防ぐ。直後に新接続へ `STATE_SYNC` を返して状態を復元する。
- **送信者の同一性検証**: 各 WS メッセージはトークンに紐づくプレイヤーの操作として処理する。**他人の代理 `SUBMIT_HAND` は不可**、`START_GAME` は**ホストのトークンのみ**許可する。
- **CPU プレイヤー（開発/デモ用）**: CPU は**トークン・WebSocket 接続を持たないサーバー制御プレイヤー**で、`JOIN` 検証・再接続・`SESSION_REPLACED`・ハートビートの対象外。`ConnectionManager` に接続エントリを持たないため、ブロードキャストの送信先にならず `STATE_SYNC` も送られない。CPU は**ホストにならず**、ホスト自動移譲（§10）の候補からも除外する。追加/削除はホストの WS 操作（§4 `ADD_CPU`/`REMOVE_CPU`）で行い、`ALLOW_CPU=false` のときは拒否する（§4.1 `CPU_NOT_ALLOWED`）。

### 3.1 REST API エンドポイント（ルーム作成・参加）
ルーム作成/参加は REST（`routers/rooms.py`）で行い、応答でトークンと初期スナップショットを返す。設計は**リソース指向**とする。リクエスト/レスポンスは Pydantic v2 で定義し、時刻は §4 の規約（UTC ISO8601・ミリ秒・`Z`）に従う。

| メソッド / パス | 用途 | リクエスト body | 成功レスポンス | 主なエラー（`code` / HTTP） |
|---|---|---|---|---|
| `POST /rooms` | ルーム作成（作成者がホスト） | `{ display_name: string }` | `201` `{ room_code, player_id, player_token, room: RoomView }` | `DISPLAY_NAME_INVALID` / 422 |
| `POST /rooms/{code}/players` | ルーム参加 | `{ display_name: string }` | `201` `{ player_id, player_token, room: RoomView }` | `ROOM_NOT_FOUND` / 404、`ROOM_FULL` / 409、`ROOM_CLOSED` / 410、`DISPLAY_NAME_INVALID` / 422 |
| `GET /rooms/{code}` | 存在確認・初期状態取得（任意） | — | `200` `{ room: RoomView }` | `ROOM_NOT_FOUND` / 404、`ROOM_CLOSED` / 410 |
| `GET /rooms/{code}/matches` | ルーム内の確定マッチ履歴一覧（Phase 5） | —（クエリ `limit` 任意） | `200` `MatchHistoryListResponse`（下記） | 不正 `code` / 422、`SERVICE_UNAVAILABLE` / 503 |

- **`GET /rooms/{code}/matches`（Phase 5）**
  - **データ源**: `match_history` コレクションを **`room_code` で直接検索**する。`GameStateStore`（インメモリ）上のルーム有無・`CLOSED` 状態に依存しない（プロセス再起動後も履歴は取得可能）。
  - **クエリ**: `limit`（任意・既定 `20`・最大 `50`）。`ended_at` **降順**（新しい試合が先）。
  - **認可（MVP）**: ルームコードを知っていれば取得可能（トークン不要）。参加リンクと同程度の共有範囲とする。在室者限定化は後フェーズで検討。
  - **DB 障害時**: `503` + `{ code: "SERVICE_UNAVAILABLE", message }`（空配列は返さない。クライアントは「履歴未取得」と区別する）。
  - **成功レスポンス** `MatchHistoryListResponse`:
    - `{ room_code: string, matches: MatchHistoryEntry[], has_more: boolean }`
    - `has_more`: 返却件数が `limit` に達したとき `true`（さらに古い履歴がある可能性）。
  - **`MatchHistoryEntry`**（各要素。時刻は §4 規約の ISO8601 文字列）:
    - `{ match_id, rule_type, players: [{ player_id, display_name, is_cpu }], winner_ids, scores, started_at, ended_at }`
    - 書き込みスキーマ（§5 `match_history`）と同一構造。MongoDB の `_id` はクライアントに露出しない。
  - **WS 通知なし**: 新規マッチ確定時に履歴用メッセージは送らない。クライアントはロビー表示時・`RETURN_TO_LOBBY` 後に REST で再取得する。
  - **任意（Phase 5 外）**: `GET /rooms/{code}/matches/{match_id}`（単件詳細）は MVP では不要（一覧で足りる）。

- **エラー形式**: REST も `{ code, message }` を本文に返し、`code` は §4.1 の `ErrorCode` を共有する（HTTP ステータスは上表の対応）。
- **定員（`ROOM_FULL`）の基準**: 在室人数は **接続中（CONNECTED）／切断中（DISCONNECTED）の人間・観戦者・CPU を合算**して数える（DISCONNECTED も枠を占有する）。プルーニングの扱いは §6 / §10 を参照。
- **レート制限**: `POST /rooms` には簡易レート制限（IP 単位など）を設けスパム作成を抑止する。既定は **同一 IP あたり 10 件 / 600 秒（10 分）**（`ROOM_CREATE_RATE_MAX` / `ROOM_CREATE_RATE_WINDOW_SEC` で `.env` 調整可）。リバースプロキシ配下では `X-Forwarded-For` で実 IP を判定（後続で強化）。
- **トークンは応答 body のみ**で返し、URL やログに残さない。参加後は §3 のとおり最初の WS `JOIN` で提示する。

### 3.2 表示名（`display_name`）の制約
- **長さ**: 前後空白をトリムした後 **1〜20 文字**。空（トリム後0文字）は `DISPLAY_NAME_INVALID`。
- **文字種**: Unicode を許容（**絵文字・多言語OK**）。ただし**制御文字（改行・タブ・ゼロ幅等）は禁止**し、サーバーでトリム/正規化する。
- **重複**: **同名を許容**する（同一人物の保証はしない）。識別は常に `player_id` で行い、UI は同名が複数いる場合に小さな識別子（末尾の短い ID 等）を添えて区別する。
- 検証は**サーバー側を正**とし（クライアントの入力チェックは UX 補助）、違反時は `DISPLAY_NAME_INVALID`（422）。

## 4. リアルタイム通信設計 (WebSocket)
- クライアントは `/ws/rooms/{room_code}` に接続し（トークンを上記の方法で提示）、`ConnectionManager` が各ルームの接続集合を保持する。
- 全メッセージは封筒形式 `{ "type": ..., "payload": ..., "v": 1 }` に統一し、`frontend/src/types` と Pydantic v2 モデルの双方で型定義して整合を取る。

全メッセージは封筒形式 `{ "type": T, "payload": P, "v": 1 }`。以下の `payload` 列は TypeScript 風の表記で示し、`frontend/src/types` と Pydantic v2 モデルの双方で同一構造を定義する。`Hand = "ROCK" | "SCISSORS" | "PAPER"`。`CpuStrategy = "RANDOM"`（MVP は `RANDOM` のみ。器として列挙を用意し、後フェーズで mimic / 難易度などを追加）。

**クライアント → サーバー**

| type | 送信者 | payload |
|---|---|---|
| `JOIN` | 接続者 | `{ token: string }`（REST 発行のトークンを提示。再接続もこのトークンで再紐付け） |
| `UPDATE_SETTINGS` | ホスト | `{ config: Partial<MatchConfig> }`（変更分のみ） |
| `ADD_CPU` | ホスト | `{ count?: number, strategy?: CpuStrategy }`（開発/デモ用。ロビーのみ。既定 `count=1` / `strategy="RANDOM"`。`ALLOW_CPU=false` は `CPU_NOT_ALLOWED`。定員（20人）を超える追加は枠の残り分のみ追加せず `ROOM_FULL` を返す（接続は閉じない）） |
| `REMOVE_CPU` | ホスト | `{ player_id?: string }`（CPU を削除。`player_id` 省略時は最後に追加した CPU を削除。ロビーのみ） |
| `START_GAME` | ホスト | `{}`（現在の `MatchConfig` で開始） |
| `SUBMIT_HAND` | 生存者 | `{ round_no: number, hand: Hand, segment_id?: string \| null }`（締切前は上書き可。`segment_id` は TOURNAMENT のペア識別用。他ルールは省略/`null`） |
| `NEXT_ROUND` | ホスト | `{}`（手動進行モード時のみ有効） |
| `RETURN_TO_LOBBY` | ホスト | `{}`（`MATCH_END` からロビーへ戻す。`Room.status` を `WAITING` に） |
| `LEAVE` | 本人 | `{}` |
| `PING` | 任意 | `{}` |

**サーバー → クライアント（個別 or ブロードキャスト）**

| type | 宛先 | payload |
|---|---|---|
| `STATE_SYNC` | 個別 | `{ room: RoomView, members: PlayerView[], you: PlayerView, match: MatchView \| null, server_now: string }`（接続/再接続直後のスナップショット。`members` で参加者一覧、`server_now` で残り時間計算の基準を復元する。受信側はこれを権威としてローカル状態を完全リセットする） |
| `LOBBY_UPDATE` | broadcast | `{ members: PlayerView[], host_player_id: string, config: MatchConfig }`（**名簿/ホストの権威スナップショット**。名称は歴史的経緯で、WAITING / IN_GAME を問わずメンバー増減・ホスト交代・`connection_state` 変化のたびに送る） |
| `SETTINGS_UPDATE` | broadcast | `{ config: MatchConfig }` |
| `ROUND_START` | broadcast | `{ round_no: number, deadline_at: string, server_now: string, alive_player_ids: string[], segment_id?: string \| null }` |
| `SUBMISSION_UPDATE` | broadcast | `{ round_no: number, submitted_player_ids: string[], expected_count: number, segment_id?: string \| null }`（**手の内容は含めない**） |
| `ROUND_RESULT` | broadcast | `{ round_no: number, hands: Record<string, Hand>, is_draw: boolean, winner_ids: string[], eliminated_player_ids: string[], alive_player_ids: string[], scores: Record<string, number>, segment_id?: string \| null }` |
| `MATCH_END` | broadcast | `{ match_id: string, winner_ids: string[], scores: Record<string, number>, reason: "DECIDED" \| "DRAW_MAX_ROUNDS" }` |
| `PLAYER_JOINED` | broadcast | `{ player: PlayerView }`（**UX 通知専用**・名簿の権威ではない。随伴する `LOBBY_UPDATE` が真実） |
| `PLAYER_LEFT` | broadcast | `{ player_id: string }`（**UX 通知専用**・名簿の権威ではない） |
| `HOST_CHANGED` | broadcast | `{ host_player_id: string }`（**UX 通知専用**・ホストの権威は `LOBBY_UPDATE` / `STATE_SYNC`） |
| `ERROR` | 個別 | `{ code: ErrorCode, message: string }`（コードは §4.1） |
| `PONG` | 個別 | `{}` |

**ビュー型（payload 内で使う集約 DTO）**
- `PlayerView`: `{ player_id, display_name, is_host: boolean, connection_state: "CONNECTED" | "DISCONNECTED", is_spectator: boolean, is_cpu: boolean }`（`token` は**含めない**。CPU は常に `is_cpu=true` / `connection_state="CONNECTED"`、UI はロボットバッジで区別する）
- `RoomView`: `{ room_code, status, host_player_id, member_count: number, capacity: number, config: MatchConfig }`（`member_count` は定員カウント対象（接続中/切断中の人間・観戦者・CPU の合算。§3.1）の現在人数、`capacity` は定員（MVP は 20）。参加前に人数表示や満員判定ができるよう REST 応答にも含める。詳細な参加者一覧は `STATE_SYNC` / `LOBBY_UPDATE` の `members` を用いる）
- `MatchView`: `{ match_id, rule_type, state, current_round_no, alive_player_ids, scores, deadline_at: string | null, my_submitted: boolean, boss_player_id?: string | null }`（`boss_player_id` は BOSS 時のみ。UI は当該プレイヤーを「ボス」表示）

- **名簿（roster）の権威**: クライアントの参加者一覧は常に `STATE_SYNC.members` / `LOBBY_UPDATE.members` の**フルスナップショットを唯一の真実**とし、reducer はこの2メッセージ受信時に `members` を**全置換**する。`LOBBY_UPDATE` は WAITING / IN_GAME を問わず、メンバー増減・ホスト交代・`connection_state`（CONNECTED/DISCONNECTED）変化のたびにブロードキャストする（試合中の切断/復帰・観戦者の途中参加もこれで反映）。`PLAYER_JOINED` / `PLAYER_LEFT` / `HOST_CHANGED` は **UX 通知専用**（トースト/アニメーション用）で、名簿の真実をこれらから導出しない（必ず `LOBBY_UPDATE` が随伴/後続する）。`config` は `SETTINGS_UPDATE`（config のみ）と `LOBBY_UPDATE` の双方に現れ、どちらも config に対して権威でよい。
- **`scores` の意味**: `ROUND_RESULT` / `MATCH_END` / `MatchView` の `scores` は **BOSS など加点制ルールでの得点**を表す。**NORMAL（`ELIMINATION` / `SINGLE_ROUND`）では加点を行わず `scores` は空 `{}`** とし、勝敗は `winner_ids` / `alive_player_ids` / `eliminated_player_ids` で表現する。
- **区画識別子（`segment_id`）**: ラウンド系メッセージ（`ROUND_START` / `SUBMISSION_UPDATE` / `ROUND_RESULT` / `SUBMIT_HAND`）に**任意の `segment_id`** を持たせる。NORMAL / MINORITY / BOSS では `null`（ルーム全体で単一ラウンド）。**TOURNAMENT では並行するペアごとに一意の `segment_id`** を割り当て、クライアントは自分の所属ペアの `segment_id` のみを描画・送信に用いる。これにより `v:1` のまま単一ラウンドと並行ペアの双方を表現でき、Phase 3 で破壊的変更を避ける。
- **時刻表現（規約）**: すべての時刻フィールド（`deadline_at` / `server_now` / `started_at` / `ended_at` など）は **UTC・ISO8601・ミリ秒付き・末尾 `Z`**（例 `2026-06-29T08:00:00.000Z`）で表現する。クライアントは端末時計に依存せず、`server_now` と `deadline_at` の差分から残り時間を算出する。

- **メッセージ検証（不正・未知の扱い）**: 受信メッセージは封筒形式・スキーマを検証し、次の方針で処理する（いずれも**接続は維持**し、状態は変更しない）。
  - **未知の `type`**: 個別 `ERROR`（`INVALID_PAYLOAD`）を返して破棄する。
  - **`v` 不一致（`v != 1`）**: 個別 `ERROR`（`INVALID_PAYLOAD`、`message` にサポートバージョンを補足）を返して破棄する。将来バージョンを増やす場合もこの分岐で互換判定する。
  - **payload スキーマ不正・JSON でない・`type` 欠落**: `INVALID_PAYLOAD` を返して破棄する。
  - **サイズ超過（§11、例 8KB 超）**: 破棄する（必要に応じて接続保護のため切断してよい）。
- **ハートビート**: `PING`/`PONG` を **25秒間隔**（`HEARTBEAT_INTERVAL_SEC`）で送り、アイドル切断（プロキシ等）防止と切断検知に用いる。**PONG が約2回分＝60秒（`HEARTBEAT_TIMEOUT_SEC`）途絶えたら `DISCONNECTED`** とする。これらは front/back 一致が必須のプロトコル値で `core/constants.py`（および frontend の同名定数）に置き、`.env` には出さず同時更新する。
- 全員の手が揃う or 制限時間到達で `game/engine.py`（または各 `rules/`）が判定し、結果をルーム全員へブロードキャストする。
- **並行性**: ルーム状態への書き込みは**ルーム単位の単一ロック（`asyncio.Lock`）で全て直列化**する。判定（「全員提出」と「締切到達」の競合による二重判定防止）だけでなく、`JOIN` / `LEAVE` / `ADD_CPU` / `REMOVE_CPU` / `UPDATE_SETTINGS` / `START_GAME` などロビー操作も同じルーム状態を並行に書き換えうるため、これらも同一ロック配下で処理し、定員チェック・FSM 遷移・ホスト判定のレースを防ぐ（詳細は §7.1）。

### 4.1 エラーコード一覧
`ERROR` の `code` は front/back で共有する定数とし、本表を正とする（`backend` は `ErrorCode` 列挙、`frontend` は同名の型/定数）。クライアントは `code` で導線（`SCREENS.md` §5）を分岐し、`message` は補助表示に用いる。

| code | 意味 | 主な発生契機 | 接続を閉じるか |
|---|---|---|---|
| `ROOM_NOT_FOUND` | ルームが存在しない | REST join / WS 接続 | 閉じる |
| `ROOM_FULL` | 定員（20人）超過 | REST join / WS `ADD_CPU` | REST join は閉じる／`ADD_CPU` は閉じない |
| `ROOM_CLOSED` | 解散済み（30分無操作など） | join / WS | 閉じる |
| `INVALID_TOKEN` | トークンが不正・未知 | WS `JOIN` | 閉じる |
| `SESSION_REPLACED` | 同一トークンの新規接続に置き換えられた（last-wins） | WS 同時接続検知 | 閉じる（古い接続側） |
| `DISPLAY_NAME_INVALID` | 表示名が空/長すぎ/不正 | REST join | — |
| `NOT_HOST` | ホスト専用操作を非ホストが実行 | `UPDATE_SETTINGS`/`START_GAME`/`NEXT_ROUND` | — |
| `NOT_ALIVE` | 生存者でない者が手を提出 | `SUBMIT_HAND` | — |
| `INVALID_STATE` | 現在の状態で許可されない操作 | 各種（FSM 違反） | — |
| `INVALID_PAYLOAD` | payload がスキーマ不正 | 各種 | — |
| `START_CONDITION_UNMET` | 開始条件未達（最小人数・ボス未選択等） | `START_GAME` | — |
| `CPU_NOT_ALLOWED` | `ALLOW_CPU=false` の環境で CPU 操作を実行 | `ADD_CPU`/`REMOVE_CPU` | — |
| `SERVICE_UNAVAILABLE` | MongoDB 等の永続化層が利用不可 | `GET /rooms/{code}/matches` | — |

### 4.2 開始条件と alive 初期集合
`START_GAME` の可否と、マッチ開始時の生存者集合は次の**単一集合 `S`** で定義する（サーバーはルーム単位ロック配下で再検証し、未達は `START_CONDITION_UNMET`）。クライアントの開始ボタン非活性（`SCREENS.md` §4.4）は UX 補助で、最終検証はサーバー側で行う。

- `S = { メンバーのうち is_spectator=false かつ (connection_state=CONNECTED または is_cpu=true) }`
- **最小人数ゲート**: `|S|` ≥ ルール別最小（NORMAL≥2 / MINORITY≥3 / BOSS≥2＋ボス / TOURNAMENT≥2）。BOSS は `boss_player_id ∈ S` を必須とする（§8）。
- **alive 初期集合**: `START_GAME` 確定時点の `S` をそのまま `Match.alive_player_ids` とする（ゲート母集団と alive を一致させ「開始できた人数 = 戦う人数」とする）。
- **開始時 DISCONNECTED の人間**: slot は保持するが `S` に含めず、そのマッチは**観戦者（`is_spectator=true`）**として扱い、`MATCH_END → ロビー` 合流時（§6）に通常参加へ戻す。これにより提出不能な phantom を alive に入れず、§7 の「DISCONNECTED が alive にいると毎ラウンド締切待ち」を避ける。
- CPU は常に CONNECTED 扱いのため `S` に含まれ、**ソロ＋CPU で開始可能**（§3/§6）。

## 5. ゲームドメインモデル
状態は **Room > Match > Round** の3層で表現する。ライブ状態は `GameStateStore`（インメモリ）が保持し、確定結果のみ MongoDB に保存する。

- **Room**: ロビー単位。`room_code`(一意), `host_player_id`, `status`(WAITING / IN_GAME / CLOSED), `members[]`, `config`(次の Match に使う `MatchConfig`), `created_at`, `last_active_at`
- **Player**: `player_id`, `token`(検証用。CPU は `null`), `display_name`(CPU は `CPU-1` 等の自動採番), `connection_state`(CONNECTED / DISCONNECTED。CPU は常に CONNECTED), `joined_at`, `is_cpu`(bool), `cpu_strategy`(`CpuStrategy` / 人間は `null`)
- **Match**: 1ゲーム。`match_id`, `rule_type`(NORMAL / MINORITY / BOSS / TOURNAMENT), `state`(§6), `config`(`MatchConfig`), `alive_player_ids[]`, `scores{player_id:int}`, `current_round_no`, `boss_player_id`(BOSS用), `winner_ids[]`, `started_at`, `ended_at`
  - **特殊ルール用フィールド**（`models.py` / Step R0 実装済み）:
    - `switched_to_normal_finish: bool` — MINORITY が閾値到達後 NORMAL 判定へ移行済みか
    - `tournament_bracket_round: int` — 現在のブラケット段（0 始まり）
    - `tournament_active_pairs: TournamentPair[]` — 当該段のアクティブペア一覧
    - `tournament_segment_rounds: Record<segment_id, Round>` — TOURNAMENT の区画別提出・締切（NORMAL / MINORITY / BOSS は `current_round` 1本）
  - **`boss_player_id`**: `start_match` 時に `init_match_for_rule` が BOSS なら `config.boss_player_id` をコピー（`ws.py` は R1 で `can_start` 再検証を追加）
- **Round**: Match 内の1回のじゃんけん（あいこ再戦で複数発生）。`round_no`, `deadline_at`(サーバー時刻が権威), `submissions{player_id: Hand}`, `result`, `judged_at`
  - **`round_no` の採番規則**: Match 開始時を `1` とし、以降は**あいこ再戦・脱落再戦を問わず新しいラウンドを開始するたびに +1 する単調増加**の整数（マッチをまたいでリセット）。`max_draw_rounds` のカウントは `round_no` とは別管理で「あいこ（同メンバー再戦）」のみを数える（脱落でメンバーが変わる再戦は数えない。§8）。`SUBMIT_HAND` / ラウンド系メッセージの `round_no` はこの値を用い、サーバーは**現在ラウンドと一致しない `round_no` の `SUBMIT_HAND` を `INVALID_STATE` で破棄**する（再接続時の遅延提出・stale 提出の混入を防ぐ）。TOURNAMENT で並行ペアがある場合の採番は §7.1 を参照（`(round_no, segment_id)` で一意）。
- **Hand（列挙）**: `ROCK` / `SCISSORS` / `PAPER`
- **永続化方針（MVP）**: 途中経過は保存せず、**Match 終了時の確定結果＋最終スコアのみ**を `match_history` コレクションに保存する。MVP では**ルーム単位のマッチ履歴のみ**を対象とし（`room_code` で参照）、`display_name` 横断のグローバルなスコアボード集計は後フェーズ（アカウント連携時）に設計する。
  - `match_history` ドキュメント例: `{ _id, room_code, match_id, rule_type, players: [{ player_id, display_name, is_cpu }], winner_ids, scores, started_at, ended_at }`
  - インデックス: `room_code` + `ended_at`（降順）でルーム内の履歴を新しい順に取得する。`match_id` にユニークインデックス（二重書き込み防止）。`player_id` は当該ルームの一時 ID であり、ルームをまたいだ同一人物の追跡は MVP では行わない。
  - **読み取り（Phase 5）**: `GET /rooms/{code}/matches`（§3.1）が MongoDB から一覧を返す。**インメモリのルーム状態とは独立**。ラウンド単位のリプレイ・グローバルスコアボード集計は対象外。

### 5.1 特殊ルールのランタイム統合（実装指針）

判定アルゴリズム（`game/rules/*`・`game/draw_resolution.py`）は Phase 3 Step 1–4 で完了。**オンライン配線**は `core/round_runner.py` と `routers/ws.py` が NORMAL のみ。進捗・タスク分解は `TODO.md`「特殊ルール：ランタイム統合」（Step R0–R6）を正とする。

| 層 | NORMAL（現状） | 統合後の責務 |
|---|---|---|
| `ws.py` `START_GAME` | `min_players_for` | `can_start()` + ルール別 match 初期化 |
| `ws.py` `SUBMIT_HAND` | `segment_id` 無視 | runner へ `segment_id` 中継（TOURNAMENT 必須） |
| `RoundRunner` | `judge_normal_round` のみ | `rule_type`（＋ MINORITY の移行フラグ）で `judge_*` / `resolve_after_*` をディスパッチ |
| タイマー | `(room, null)` 1本 | TOURNAMENT はアクティブペアごとに `(room, segment_id)` 並行 |

**実装順（推奨）**: MINORITY（単一区画・NORMAL と同型）→ BOSS（scores・ボス手）→ TOURNAMENT（区画別ラウンド・ステージバリア）。

## 6. ゲーム状態遷移 (FSM)
- **Room.status**: `WAITING ⇄ IN_GAME`、最終的に `CLOSED`
- **Match.state**: `COLLECTING`(受付中・タイマー稼働) → `JUDGING`(入力ロック) → `ROUND_RESULT` →（継続なら `COLLECTING` へ戻る ／ 決着なら `MATCH_END`）

各状態で許可する操作:

| 状態 | 許可される操作 |
|---|---|
| WAITING(ロビー) | `JOIN` / `LEAVE` / `UPDATE_SETTINGS`(ホスト) / `ADD_CPU`・`REMOVE_CPU`(ホスト, `ALLOW_CPU` 時) / `START_GAME`(ホスト) |
| COLLECTING | `SUBMIT_HAND`(生存者のみ・締切前は上書き可) / `LEAVE` |
| JUDGING | 入力不可（ロック。§4 の `asyncio.Lock` と連動） |
| ROUND_RESULT | 表示のみ。**進行モード**に応じて自動 or ホストの `NEXT_ROUND` で次へ |
| MATCH_END | 結果表示。ホストの `RETURN_TO_LOBBY` でロビーへ戻る（`LEAVE` も可） |

- **`MATCH_END` の遷移点**: マッチ確定後も **`Room.status` は `IN_GAME` のまま**で `Match.state = MATCH_END` の結果画面を全員に表示し続ける（状態駆動 UI が結果を描画できるようにするため）。**ホストの `RETURN_TO_LOBBY`** を受けて初めて `Room.status = WAITING` に遷移し、`LOBBY_UPDATE` をブロードキャストする。この遷移の時点で**観戦者を通常プレイヤーへ合流**させ（`is_spectator = false`）、ホストは次の設定変更・`START_GAME` が可能になる。**また、この合流タイミングで `DISCONNECTED` のまま復帰しなかったプレイヤー（ゴースト）をルームから除去**し（`PLAYER_LEFT` をブロードキャスト）、定員枠を解放する。
- **途中参加**: Match 進行中（IN_GAME）の新規参加者は**観戦として入室し、次の Match からプレイ参加**する（`PlayerView.is_spectator = true`）。
- **観戦者への配信範囲**: 観戦者にもロビー情報に加え、進行中の `ROUND_START` / `SUBMISSION_UPDATE` / `ROUND_RESULT` / `MATCH_END` を**プレイヤーと同様にブロードキャスト**する（手は他者と同様に秘匿。`SUBMISSION_UPDATE` の `expected_count` は alive 集合基準で観戦者を含めない）。観戦者には**手の提出 UI を出さず**、サーバーも観戦者からの `SUBMIT_HAND` は `NOT_ALIVE` で拒否する。`MATCH_END → ロビー`のタイミングで通常プレイヤーへ合流する。
- **再提出**: 締切前 or 生存者全員の提出が揃うまでは**上書き可**。締切到達 or 全員提出で確定し `JUDGING` へ遷移する。
- **マッチ中の `LEAVE`**: COLLECTING 中の `LEAVE` は**切断と同等**に扱い（§7）、その Match の終了まで alive を維持する（即座に alive から外して勝者を確定させない）。ロビー（WAITING）/`MATCH_END` での `LEAVE` は即時退出。
- **CPU の自動提出**: CPU は alive な間、各 `ROUND_START` 時にサーバーが手を生成し（`cpu_strategy`、MVP は `RANDOM`）、自然さのため**短いランダム遅延（例 0.3〜1.5 秒）**で `SUBMIT_HAND` 相当の登録を行う。これにより CPU は「全員提出」（§7）にカウントされ**ソロでも進行が止まらない**。CPU は未提出によるタイムアウト・切断・`LEAVE` を起こさない。CPU の追加/削除は WAITING のみ可（IN_GAME 中は `INVALID_STATE`）。
  - **遅延のクランプ**: 提出遅延は必ず締切前に収める。実装では `delay = min(rand(0.3, 1.5), max(0, round_time_limit_sec - ε))`（`ε = 0.25` 秒）のように**締切（`deadline_at`）の手前にクランプ**し、将来 `round_time_limit_sec` を下限（5秒）より短く設定し直しても CPU が締切を超えて未提出扱いになる事故を防ぐ。遅延の下限/上限（`0.3` / `1.5` 秒）と `ε` は `core/constants.py` の定数（`CPU_SUBMIT_DELAY_MIN_SEC` / `CPU_SUBMIT_DELAY_MAX_SEC` / `CPU_SUBMIT_DELAY_EPSILON_SEC`）とする。
- **次ラウンド進行モード**: `ROUND_RESULT` から次へ進む方法はホストが **自動 / 手動 を切り替え可能**（`MatchConfig.round_advance_mode`、§9）。**自動時はサーバーが `result_display_sec`（既定3秒、§9）だけ結果を表示してから次の `ROUND_START` を送る**（全員の表示タイミングを揃える）。手動時はホストの `NEXT_ROUND` を待つ。**MANUAL 進行中にホストが切断した場合は進行が停止するため、§10 のホスト自動移譲を優先的にトリガー**して新ホストに `NEXT_ROUND` 権を引き継ぐ（移譲先の人間が居ない場合は §10 に従いスイープへ委ねる）。

## 7. タイムアウト・切断者の扱い
- **制限時間**: ラウンド締切は**サーバー側タイマーが権威**（クライアント時刻に依存しない）。秒数はホストが設定する（`MatchConfig.round_time_limit_sec`、§9）。
- **「全員揃った」の定義**: そのラウンド開始時点の **alive プレイヤー集合**を基準とする。締切前に alive 全員が提出したら即 `JUDGING`。
- **未提出時**: 締切までに未提出のプレイヤーは**そのラウンド敗北（脱落系ルールでは脱落）**として扱う。
- **提出者0／生存者0の保護**: そのラウンドの**提出者が1人もいない**、または判定の結果**生存者が0人**になる場合は、その判定を**無効化し、同じ alive メンバーで再ラウンド**する（あいこと同様に扱い、`max_draw_rounds`（§9）をカウントする）。上限到達時はそのマッチを**引き分け終了**とする（`MATCH_END.reason = DRAW_MAX_ROUNDS`）。これにより「全員が一斉に未提出」でも進行が破綻しない。
- **切断者**: 切断しても即脱落とはせず、`DISCONNECTED` 表示のまま **その Match の終了まで alive を維持**する。同一トークンの再接続で復帰し、`STATE_SYNC` で状態を復元する。
  - ⚠️ **alive 維持の意味（誤解防止）**: これは「切断した瞬間に alive 集合から外して生存者数を即変動させ、勝者が瞬間確定する」ことを防ぐための措置であり、**切断者を毎ラウンド保護するものではない**。切断者は手を提出できないため、判定では「未提出＝そのラウンド敗北/脱落」として扱われる（ELIMINATION では結局そのラウンドで脱落する）。再接続して締切前に提出すれば通常どおり参加できる。
  - ⚠️ **早期確定への影響**: alive 集合に提出不可能な `DISCONNECTED` が1人でも含まれる間は「alive 全員提出」が成立しないため、そのラウンドは**必ず締切まで待ってから判定**される（早期確定は発火しない）。これは意図した挙動。
- **意図的退出（`LEAVE`）**: マッチ進行中（COLLECTING）の `LEAVE` は**切断と同等に扱い**、その Match の終了まで alive を維持する（未提出はそのラウンド敗北/脱落として処理）。これにより「2人中1人が抜けて勝者が瞬間確定する」ような挙動を防ぐ。ロビー（WAITING）/`MATCH_END` での `LEAVE` は即時にルームから退出する。

### 7.1 ラウンドタイマーの実装方針
締切＝権威を二重判定なしで実現するため、次の方針で実装する。

- **タイマー本体**: `ROUND_START` 時にラウンドごとの `asyncio.Task` を1本起動し、`round_time_limit_sec` 後に「締切判定」を行う。`deadline_at` はこのタスクの発火予定時刻として算出し、`server_now` と共にクライアントへ送る（クライアントは差分から残り時間を表示し、端末時計のズレに依存しない）。
- **早期確定**: `SUBMIT_HAND` 受信で alive 全員の提出が揃ったら、走っている締切タスクを `task.cancel()` して即 `JUDGING` へ進む。
- **直列化（二重判定防止・状態レース防止）**: 「全員提出」経路と「締切到達」経路は**ルーム単位の `asyncio.Lock`** 内で実行し、ロック取得後に「このラウンドが未判定か」を確認してから1回だけ判定する（後着の経路は no-op）。判定確定時にラウンド状態を `JUDGING` にし、以降の `SUBMIT_HAND` は `INVALID_STATE` で弾く。
  - **ロックのスコープは判定に限定しない**: §4「並行性」のとおり、`JOIN` / `LEAVE` / `ADD_CPU` / `REMOVE_CPU` / `UPDATE_SETTINGS` / `START_GAME` などルーム状態を書き換える操作はすべて同じルーム単位ロック配下で直列化する。これにより「`START_GAME` と `JOIN` の競合」「`ADD_CPU` 連打と定員チェックの競合」などのレースを防ぐ。ロック保持区間は状態更新＋（必要なら）ブロードキャスト準備までの短時間に限り、I/O（実際の WS 送信）は極力ロック外で行う。
  - ⚠️ この `asyncio.Lock` は**プロセス内専用**。将来 `GameStateStore` を Redis 実装に差し替えて複数ワーカー化する場合は、`asyncio.Lock` では直列化できないため**分散ロック（Redis `SETNX`/Redlock 等）**へ置き換える必要がある（MVP は単一ワーカー前提のため現状の `asyncio.Lock` で可）。
- **クリーンアップ**: 判定確定・`NEXT_ROUND`・Match 終了・ルーム破棄の各タイミングで、未完了のタイマータスクを確実に `cancel()` して破棄する。
- **区画（segment）単位への抽象化**: NORMAL / MINORITY / BOSS は1ルームに同時1ラウンド（`segment_id=null`）だが、**TOURNAMENT は `segment_id` ごとに並行ラウンドが走り、ペアごとに独立した締切・あいこ再戦・`round_no` が必要**になる。そのため MVP の段階から**タイマータスクと「未判定か」の確認単位を「ルーム」ではなく「`(room, segment_id)`」をキーとする抽象**として設計する（NORMAL では `segment_id=null` の単一区画として1本動く）。
  - **ロックとの関係**: ルーム状態の書き込み直列化は §4 / 本節の**ルーム単位ロックを維持**する（区画ごとの判定もロック取得後に対象区画の未判定チェックを行う）。これにより Phase 3 で TOURNAMENT を追加する際、`v:1` のメッセージ形式・タイマー実装を破壊的に変えずに並行ペアへ拡張できる。
- **TOURNAMENT の `Match.state`（ステージ集約）**: ペアごとに `COLLECTING` / `ROUND_RESULT` が異なる時刻に存在しうるが、§6 の単一 FSM と矛盾しないよう **マッチ全体の `Match.state` はステージ単位で集約**する。区画ごとの提出・締切・判定済みは `tournament_segment_rounds`（§5）で保持する。
  - ステージ中: いずれかの区画が未完了ならマッチは `COLLECTING`（または区画判定中の短い `JUDGING` をマッチ全体に反映してよい。実装は `RoundRunner` で一貫させる）
  - 全アクティブ区画が完了（bye 含む勝者確定）したら `ROUND_RESULT` → 自動/手動で次ステージまたは `MATCH_END`
  - 同一ステージの全ペアは**同じ `round_no`** を共有。ペア内あいこ再戦時のみ `round_no` を +1（`(round_no, segment_id)` で区画一意）
  - `ROUND_START.alive_player_ids` は TOURNAMENT では**当該ペアの2人**（観戦者・他ペアの alive は含めない）。`SUBMISSION_UPDATE.expected_count` はペア内では `2`
  - ステージ完了後: `collect_round_winners` → 優勝者1人なら `MATCH_END`、そうでなければ `next_bracket_round` で次段ペアを開始（bye は `ROUND_START` 不要で即勝者扱い）
- **`MatchView`（TOURNAMENT）**: 再接続クライアント向けに、viewer の所属ペアの `segment_id` とその区画の `deadline_at` / `my_submitted` を返す（`_match_view` 拡張。`TODO.md` R4）

## 8. 特殊ルール仕様（あいこ・再戦）
判定は `game/engine.py`（通常）と `game/rules/*`（特殊）に分離する。**あいこ（決着がつかず同メンバーで再戦するラウンド）の回数**の上限は `MatchConfig.max_draw_rounds`（§9）で制御し、上限到達時はその Match を**引き分け終了**（脱落・勝者確定なし）とする。脱落が進むラウンド（メンバーが変わる再戦）はこのカウントに**含めない**。

- **NORMAL（通常・MVP）**: 1ラウンドの判定は、出た手の種類が「1種類のみ(全員同じ)」または「3種類すべて」なら**あいこ → 再ラウンド**、「2種類」なら勝ち手側が勝者・負け手側が敗者。**マッチ終了方式はホスト設定 `normal_end_mode`（§9）で切り替える**:
  - `ELIMINATION`（脱落式）: 負け手側を脱落させ、勝ち残りで再戦を繰り返し**生存者が1人になったら勝者確定**。あいこは同メンバーで再戦（`max_draw_rounds` をカウント）。`max_draw_rounds` 到達時は引き分け終了。生存者が0人になる場合は §7 の保護に従い再戦扱い。
  - `SINGLE_ROUND`（1ラウンド確定式）: 最初に勝敗がついた1ラウンドで**勝ち手側全員を勝者**としてマッチ終了（脱落の繰り返しなし）。あいこは再ラウンドし、`max_draw_rounds` 到達で引き分け終了。
- **MINORITY（少数派）**: 手ごとの人数を集計し、**最少人数の手（1つ）を出した人のみ生存**、他は脱落。全員同じ手 / 最少人数の手が複数タイ → あいこ → 同メンバーで再戦。**生存者が閾値以下になったら NORMAL で決着**する（閾値・移行タイミングはホスト設定、§9）。
- **BOSS（代表）**: ボスは**非参加者（勝敗・勝者カウントの対象外）**として毎ラウンド手を出す。ボスに勝った参加者が生存（+スコア）、あいこ・負けは脱落。ボスは**ホスト指名**で選出する。`ROUND_RESULT` の `hands` には**ボスの手も含めて全員に見せる**が、`winner_ids` / `scores` / `alive_player_ids` からは**ボスを除外**する。ボスの識別子は `MatchView.boss_player_id` で配信する。
  - **`boss_player_id` の参照整合**: ホストが BOSS を指名した後、その指名プレイヤーがロビーで退出/除去されると `boss_player_id` がダングリングする。`START_GAME` の開始条件再検証（§4.2）で「`boss_player_id` が集合 `S`（§4.2: 非観戦かつ CONNECTED または CPU）に存在すること」を必須チェックし、不在なら `START_CONDITION_UNMET` で開始を拒否する。指名プレイヤーが退出した時点で `boss_player_id` を `null` にリセットして `SETTINGS_UPDATE` で周知してもよい。
- **TOURNAMENT（トーナメント）**: 参加者からブラケットを自動生成（奇数は **bye**）。各ペアを独立判定し、ペア内あいこはそのペアのみ再戦。勝者が上位へ進み、優勝者1人で終了。

## 9. ホスト設定 (MatchConfig)
ホストはロビーで次の Match 設定を変更できる（`UPDATE_SETTINGS` → `SETTINGS_UPDATE` でロビーに反映、`START_GAME` で確定）。

**設定値の正本**: 各項目の既定値・許容範囲は**本節を正本**とし、サーバー（Pydantic v2 の `MatchConfig`）で範囲・型を検証する（範囲外は `INVALID_PAYLOAD`）。`SCREENS.md` §4.2 はこの値を UI 表現（コントロール種別・刻み）として参照するものであり、数値の二重管理を避けるため本節と乖離させない。

| 項目 | 型 / 選択肢 | 範囲 | 既定 | 有効条件 |
|---|---|---|---|---|
| `rule_type` | NORMAL / MINORITY / BOSS / TOURNAMENT | — | NORMAL | 常時。**オンライン対戦は NORMAL のみ**（特殊ルールはアルゴリズム実装済み・`RoundRunner` 統合後に有効化。`TODO.md` R0–R6） |
| `normal_end_mode` | ELIMINATION / SINGLE_ROUND | — | ELIMINATION | `rule_type=NORMAL`（§8） |
| `round_time_limit_sec` | int（秒） | 5〜60（5刻み） | 10 | 常時 |
| `round_advance_mode` | AUTO / MANUAL | — | AUTO | 常時（`ROUND_RESULT` からの進行） |
| `result_display_sec` | int（秒） | 1〜10（1刻み） | 3 | `round_advance_mode=AUTO`。AUTO 進行時に `ROUND_RESULT` 表示後この秒数だけ待ってから次 `ROUND_START` |
| `max_draw_rounds` | int | 1〜20 | 5 | 常時。1 Match 内の**あいこ（決着がつかず同メンバーで再戦するラウンド）回数**の上限。到達時は引き分け終了（脱落でメンバーが変わる再戦は数えない） |
| `minority_finish_threshold` | int（人数） | 2〜(参加者数−1) | 2 | `rule_type=MINORITY`。この生存人数以下で NORMAL 決着へ移行 |
| `minority_finish_timing` | 即時 / 次マッチから | — | 即時 | `rule_type=MINORITY` |
| `boss_player_id` | player_id | 参加者一覧 | 未選択(null) | `rule_type=BOSS`（ホスト指名） |

> **器とアルゴリズム**: `Match` / `MatchConfig` / `scores` / ルール別設定項目は用意済み。判定は `game/rules/*` + `draw_resolution.py` まで完了。**ランタイム統合**（`RoundRunner` / `ws.py` / フロント UI）は `TODO.md`「特殊ルール：ランタイム統合」を参照。

## 10. バックグラウンドタスク・ライフサイクル
ゲーム進行とは別に、`lifespan` で起動する常駐タスクで以下を扱う（単一ワーカー前提。複数ワーカー化時は Redis 実装側へ移す）。

- **ルーム破棄スイープ**: 一定間隔（**60秒** = `ROOM_SWEEP_INTERVAL_SEC`・`core/constants.py` 定数）で全ルームを走査し、`last_active_at` から **30分以上無操作**（`ROOM_IDLE_TTL_SEC`・既定 `1800`・`.env` 調整可）のルームを `CLOSED` にして接続を閉じる（接続中クライアントには `ROOM_CLOSED` を通知）。`last_active_at` は JOIN/操作/提出などで更新する。
- **ホスト自動移譲**: ホストが切断したまま復帰しない場合、**最古参の接続中（CONNECTED）の人間プレイヤー**へホストを移し `HOST_CHANGED` をブロードキャストする（**CPU は候補から除外**）。判定は切断検知（ハートビート欠落/切断イベント）を契機に、猶予時間（**30秒** = `HOST_TRANSFER_GRACE_SEC`・既定 `30`・`.env` 調整可）経過後に行う。
  - **移譲後に元ホストが復帰した場合**: 同一トークンで再接続しても**ホスト権は取り戻さない**（移譲後の新ホストを維持し、元ホストは通常プレイヤー/生存者として復帰する）。これにより `HOST_CHANGED` の冪等性が保たれ、復帰のたびにホストが揺れる事態を防ぐ。
  - **ホストの明示的 `LEAVE`（ロビー）**: `WAITING` でホストが `LEAVE` した場合は即時退出（§6/§7）と同時に、上記と同じ規則で**最古参の接続中の人間へ即座に移譲**して `HOST_CHANGED` をブロードキャストする（猶予を待たない）。
  - **移譲先の人間が居ない場合**: 例えば人間が全員退出し CPU のみ残存したケースでは移譲できない。この場合は**人間が0人になった時点でルームを即 `CLOSED`**（接続中の CPU 以外は居ないため `ROOM_CLOSED` 通知の対象は無し）にしてリソースを解放する（30分スイープを待たない）。マッチ進行中（IN_GAME）に一時的に全員 `DISCONNECTED`（人間は居るが全員切断）になった場合は §7 のとおり alive を維持し、ルーム破棄スイープに委ねる。
  - **進行停止の回避**: `round_advance_mode=MANUAL` の `ROUND_RESULT` や `MATCH_END` ではホスト操作（`NEXT_ROUND` / `RETURN_TO_LOBBY`）待ちで進行が止まるため、ホスト切断検知時は移譲を**優先的にトリガー**する。移譲先の人間が居ないまま `MATCH_END` で停止した場合は、ルーム破棄スイープ（30分無操作）に委ねる。
- **ゴースト（長期 DISCONNECTED）の整理**: `MATCH_END → ロビー` 合流時（§6）に未復帰の DISCONNECTED を除去するのに加え、**WAITING 中に一定時間（120秒 = `GHOST_TTL_SEC`・既定 `120`・`.env` 調整可）復帰しない DISCONNECTED もスイープで除去**して定員枠を解放する（`PLAYER_LEFT` を通知）。マッチ進行中（IN_GAME）の DISCONNECTED は §7 のとおり alive を維持し除去しない。
- **アイドル切断検知**: ハートビート（`PING`/`PONG`）の欠落で `connection_state` を `DISCONNECTED` に落とす。再接続（同一トークンの `JOIN`）で `CONNECTED` に戻す。**CPU は接続を持たないため検知対象外**（常に CONNECTED 扱い）。
- いずれの常駐タスクも `lifespan` 終了時に確実に `cancel()` してから抜ける。

## 11. 開発環境・品質ツール・運用前提
- **品質ツール**:
  - backend: **ruff**（lint + format）、**mypy**（型チェック）、**pytest**。テストは3層で行う: ①判定エンジン/各 `rules` を**純粋関数として網羅**、②FSM 遷移（COLLECTING→JUDGING→…）を状態ストア単体で検証、③**WebSocket 結合テスト**（`pytest-asyncio` + Starlette テストクライアント）で締切到達・早期確定・再接続復元・`SESSION_REPLACED`・二重判定防止の主要シナリオを検証。
  - frontend: **ESLint + Prettier**、**TypeScript strict** モード。
  - **CI: GitHub Actions** で lint・型チェック・テストを自動実行する。
- **開発/デモ用 CPU**: `.env` の `ALLOW_CPU`（既定 `true`）で有効化する。ホストはロビーで `ADD_CPU`/`REMOVE_CPU`（§4）により CPU を増減でき、一人でも全ゲームループ（提出→判定→結果→次ラウンド/終了）を確認できる。**本番は `ALLOW_CPU=false` を推奨**し、`.env.example` にも明記する。
- **ローカル MongoDB**: 次の2方式を README に併記し、`.env`（`DB_URL`, `DB_NAME`）で切り替える。
  - `docker-compose` でローカル Mongo を起動する方式（`.env.example` を同梱）。
  - MongoDB Atlas の接続文字列を使う方式。
- **運用前提（MVP）**:
  - ゲーム進行状態の正本はインメモリのため **uvicorn は単一ワーカー**で起動する（`--workers` は 1）。
  - **プロセス再起動・クラッシュで進行中のゲーム状態は失われる**（永続化するのは `match_history` の確定結果のみ）。これは MVP として許容する。
  - **CORS**: 許可オリジンは `.env` で設定可能にし、開発はローカル（Vite dev server）を許可する。
  - ルーム作成エンドポイントには簡易なレート制限を設け、スパム作成を抑止する（後続で強化）。
  - **WS 濫用対策（MVP は軽量）**: 1 メッセージのサイズ上限（**8KB＝8192 byte 超は破棄** = `WS_MAX_MESSAGE_BYTES`・`core/constants.py` 定数）を設け、不正/巨大 payload で接続を保護する。同一プレイヤーの**短時間の連打は無視**（状態を変えずカウントもしない）にとどめ、本格的なトークンバケット型レート制限は後フェーズで導入する。
  - **トランスポート暗号化**: トークンを WS の `JOIN` で平文送信するため、**本番は `wss`/HTTPS を必須**とする（リバースプロキシ等で TLS 終端）。ローカル開発は `ws`/HTTP を許容する。
