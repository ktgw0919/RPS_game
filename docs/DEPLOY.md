# 公開デモ・本番運用手順

自宅 PC（Windows）でサービスを常時稼働し、Cloudflare Tunnel 経由で HTTPS / WSS 公開する手順。
プロトコル変更は行わず、リバースプロキシと TLS 終端で `ARCHITECTURE.md` §11 のトランスポート要件を満たす。

開発用 `npm run dev`（Vite :5173）は**外部公開に使わない**。本番ビルド + Caddy で同一オリジンにまとめる。

## 構成

```
クライアント（ブラウザ）
  → https://rps.<DOMAIN>     （Cloudflare Tunnel・TLS 終端）
  → cloudflared（自宅 PC）
  → Caddy :8080              （静的ファイル + API/WS プロキシ）
       ├─ /                  → frontend/dist
       └─ /rooms,/config,/health,/ws → uvicorn :8000
  → MongoDB（docker compose または Atlas）
```

フロントは `window.location.host` へ相対パスで REST / WebSocket するため、**公開 URL と API/WS は同一ホスト**にする（Caddy の役割）。

## 前提

| ツール | 用途 |
|--------|------|
| Docker Desktop | ローカル MongoDB（`docker compose`） |
| uv / Python 3.12+ | バックエンド |
| Node.js | フロントビルド |
| [Caddy](https://caddyserver.com/) | リバースプロキシ（`winget install CaddyServer.Caddy`） |
| [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) | Cloudflare Tunnel（`winget install Cloudflare.cloudflared`） |
| Cloudflare アカウント + ドメイン | 名前付きトンネル（URL 固定） |

## 1. MongoDB

リポジトリルートで:

```powershell
docker compose up -d
docker compose ps   # rps-mongo が Up
```

`backend/.env`（`Copy-Item .env.example .env` 後）:

```env
DB_URL=mongodb://localhost:27017
DB_NAME=rps
ALLOW_CPU=true   # デモは true。本番は false（下記チェックリスト）
```

## 2. バックエンド

```powershell
cd backend
uv sync --all-extras
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- **`--reload` は付けない**（常時稼働向け）
- **`--host 127.0.0.1`**（Caddy 以外から 8000 番に直接到達させない）
- 単一ワーカー（`--workers` は 1）。ゲーム状態はインメモリ正本

確認:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## 3. フロントエンド（本番ビルド）

```powershell
cd frontend
npm install
npm run build
```

`frontend/dist` が生成される。UI 更新時は `npm run build` のみでよい（Caddy 再起動は不要）。

## 4. Caddy

### 設定ファイル

テンプレートをコピーし、`<REPO_ROOT>` を実パスに置換する:

```powershell
cd <REPO_ROOT>
Copy-Item deploy\Caddyfile.example Caddyfile
# Caddyfile 内の <REPO_ROOT> を編集
```

`Caddyfile` はマシン固有のため **Git にコミットしない**（`.gitignore` 対象）。

起動:

```powershell
caddy run --config Caddyfile
```

確認:

```powershell
Invoke-RestMethod http://localhost:8080/health
# ブラウザで http://localhost:8080 → ルーム作成まで
```

## 5. Cloudflare 名前付きトンネル（URL 固定）

Quick Tunnel（`cloudflared tunnel --url ...`）は手軽だが **再起動で URL が変わる**ことがある。常時デモは名前付きトンネルを使う。

以下の `<DOMAIN>` は取得済みドメイン（例: `ktgw0919.com`）、公開 URL は `https://rps.<DOMAIN>` とする。

### 5-1. ログイン

```powershell
cloudflared tunnel login
```

ブラウザで `<DOMAIN>` を選択して Authorize。`%USERPROFILE%\.cloudflared\cert.pem` が作成される（**コミット禁止**）。

### 5-2. トンネル作成

```powershell
cloudflared tunnel create rps-demo
```

表示される **Tunnel ID**（UUID）を控える。認証 JSON が `%USERPROFILE%\.cloudflared\<TUNNEL_ID>.json` に作成される（**コミット禁止**）。

### 5-3. config.yml

テンプレートをコピーし、プレースホルダを置換:

```powershell
Copy-Item deploy\cloudflared.config.yml.example $env:USERPROFILE\.cloudflared\config.yml
# <TUNNEL_ID> と <DOMAIN> を編集
```

検証:

```powershell
cloudflared tunnel ingress validate
```

### 5-4. DNS（サブドメイン）

```powershell
cloudflared tunnel route dns rps-demo rps.<DOMAIN>
```

Cloudflare ダッシュボードの DNS に `rps` の CNAME が追加される。

### 5-5. 起動

```powershell
cloudflared tunnel run rps-demo
```

確認:

```powershell
Invoke-RestMethod https://rps.<DOMAIN>/health
```

## 起動順・終了順

| 起動順 | 終了順（逆） |
|--------|--------------|
| 1. `docker compose up -d` | 4. cloudflared を停止 |
| 2. uvicorn | 3. Caddy を停止 |
| 3. Caddy | 2. uvicorn を停止 |
| 4. `cloudflared tunnel run rps-demo` | 1. `docker compose down`（任意） |

## 常時稼働の注意

- PC の**スリープを無効化**
- cloudflared / Caddy / uvicorn のターミナルを閉じない（またはサービス化・起動スクリプトを利用）
- **プロセス再起動で進行中ゲームは消失**（確定済み `match_history` のみ MongoDB に残る）
- Windows Update の自動再起動に注意

### 任意: cloudflared を Windows サービス化

管理者 PowerShell:

```powershell
cloudflared service install
sc start cloudflared
```

`%USERPROFILE%\.cloudflared\config.yml` を参照する。uvicorn / Caddy / MongoDB の自動起動は別途設定する。

### 任意: 起動スクリプト

`deploy/start-demo.ps1.example` を `deploy/start-demo.ps1` にコピーし、`<REPO_ROOT>` を編集して利用する。`deploy/start-demo.ps1` は Git にコミットしない。

## 本番・公開デモ向け設定チェックリスト

`backend/.env` を環境に合わせて確認する。

| 項目 | デモ（研究室） | 本番・長期公開 |
|------|----------------|----------------|
| `ALLOW_CPU` | `true` 可（ソロ検証） | **`false` 推奨** |
| `DB_URL` | `mongodb://localhost:27017` | Atlas 等。パスワード付き URL は **`.env` のみ** |
| `CORS_ORIGINS` | Caddy 同一オリジンなら変更不要 | フロントと API を分離する構成時のみ公開オリジンを列挙 |
| uvicorn | `--host 127.0.0.1`、単一ワーカー、`--reload` なし | 同左 |
| TLS | Cloudflare Tunnel（HTTPS / WSS） | 同左 |
| `ROOM_IDLE_TTL_SEC` | 既定 1800（30 分） | 負荷に応じて調整可 |
| `ROOM_CREATE_RATE_MAX` | 既定 10 / 10 分 | スパム対策として維持 |

## トラブルシューティング

| 症状 | 確認 |
|------|------|
| 公開 URL が 502 | Caddy（8080）・uvicorn（8000）が起動しているか |
| WS のみ失敗 | uvicorn 直公開ではなく **Caddy 経由（8080）** か |
| `caddy` / `cloudflared` が認識されない | PowerShell を開き直す、または PATH を再読み込み |
| Caddy 起動で 2019 ポート競合 | 既に Caddy が動いている。`http://localhost:8080/health` を確認 |
| 対戦履歴が保存されない | `docker compose ps` で MongoDB が Up か |

## リポジトリに含めるもの / 含めないもの

**コミットしてよい**: 本ドキュメント、`deploy/*.example`、手順・プレースホルダ付き設定テンプレート。

**コミットしない**（秘密・マシン固有）:

| パス | 内容 |
|------|------|
| `backend/.env` | DB 接続文字列・運用フラグ |
| `Caddyfile`（ルート） | ローカル絶対パス |
| `%USERPROFILE%\.cloudflared\*.json` | トンネル認証情報 |
| `%USERPROFILE%\.cloudflared\cert.pem` | `tunnel login` 証明書 |
| `deploy/start-demo.ps1` | ローカルパス入り起動スクリプト |

公開 URL（例: `https://rps.ktgw0919.com`）は DNS 上も公開情報のため、ドキュメントに例示してよい。トンネル **credentials JSON** だけは厳守して除外する。

## 関連ドキュメント

- `ARCHITECTURE.md` §11 — トランスポート暗号化・単一ワーカー前提
- `README.md` — 開発用クイックスタート（`npm run dev`）
- `docs/TODO.md` Phase 7 — デプロイ整備の進捗
