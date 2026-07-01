# Realtime Rock-Paper-Scissors

[![CI](https://github.com/ktgw0919/RPS_game/actions/workflows/ci.yml/badge.svg)](https://github.com/ktgw0919/RPS_game/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

複数人がブラウザから参加できるリアルタイムじゃんけんゲーム。
React + FastAPI + WebSocket + MongoDB のフルスタック学習プロジェクト。

```powershell
git clone https://github.com/ktgw0919/RPS_game.git
cd RPS_game
```
設計の正本は [`docs/`](docs/) を参照（実装より `docs/` を優先）:

- [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) — 製品要件・制約
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — 技術設計（WS / FSM / ドメイン）
- [`docs/SCREENS.md`](docs/SCREENS.md) — 画面遷移
- [`docs/TODO.md`](docs/TODO.md) — 実装フェーズ（Phase 1–5）
- [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) — Git 運用方針（ブランチ・コミット・PR・進捗ドキュメント同期 §9・**Agent 自動 Git** §10）

## 構成

```
backend/    FastAPI + WebSocket + MongoDB（uv 管理）
frontend/   React + Vite + TypeScript（strict）+ Tailwind CSS
docs/       設計ドキュメント（正本）
docker-compose.yml   ローカル MongoDB
```

## クイックスタート

### 1. MongoDB（いずれか）

- **ローカル（docker-compose）**: `docker compose up -d`
- **MongoDB Atlas**: 接続文字列を `backend/.env` の `DB_URL` に設定

### 2. Backend

```powershell
cd backend
uv sync --all-extras
Copy-Item .env.example .env   # DB_URL / DB_NAME を設定
uv run uvicorn app.main:app --reload --port 8000   # 単一ワーカー（MVP 前提）
```

ヘルスチェック: `GET http://localhost:8000/health`

### 3. Frontend

```powershell
cd frontend
npm install
npm run dev   # http://localhost:5173 （/rooms・/ws を backend にプロキシ）
```

## 実装状況

- [x] **Phase 1**: 環境構築・シンプル REST API（ルーム作成/参加、トークン発行、レート制限、品質ツール・CI）
- [x] **Phase 2**: WebSocket・ゲームループ（MVP）。Redis 実装（Step 3）は任意のため未着手
- [ ] **Phase 3**: 特殊ルール（MINORITY / BOSS / TOURNAMENT）
- [x] **Phase 4**: フロントエンド統合（WS・全画面・CPU UI・再接続/締切/ホスト移譲）
- [x] **Phase 5**: 対戦履歴の読み取り（`GET /rooms/{code}/matches`）とロビー履歴 UI（SWR / `MatchHistoryPanel`）

**MVP 残タスク**（[`docs/TODO.md`](docs/TODO.md) 末尾）: フロント E2E テスト（任意）のみ。

詳細は [`docs/TODO.md`](docs/TODO.md)。

## 品質チェック

```powershell
# backend
cd backend; uv run ruff check .; uv run ruff format --check .; uv run mypy app; uv run pytest
# frontend
cd frontend; npm run lint; npm run format:check; npm run build
```

CI（GitHub Actions, [`.github/workflows/ci.yml`](.github/workflows/ci.yml)）で
backend（ruff / mypy / pytest）と frontend（eslint / prettier / build）を自動実行する。

## MVP の運用前提

- ゲーム進行状態の正本は**単一プロセスのインメモリ**（`uvicorn` は単一ワーカーで起動）。
  プロセス再起動で進行中の状態は失われる（永続化は `match_history` の確定結果のみ）。
- 認証は行わず `playerId` / `playerToken` で識別。本番は `wss`/HTTPS 必須。
- 開発/デモ用 CPU は `ALLOW_CPU`（`.env`）で切替（本番は無効化推奨）。

## License

[MIT](LICENSE) — 自由に利用・改変・再配布できます（著作権表示とライセンス文の保持が条件）。
