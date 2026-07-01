# 構成雛形メモ（旧 chapter9 由来）

> 旧 `chapter9`（FARM cars サンプル: pip / CRA / Pydantic v1）の構成から、
> 本プロジェクトで踏襲する「責務分割の考え方」だけを抽出したもの。
> 実ソースは削除済みなので、構成の参照はこのファイルを正とする。
> ※ 依存管理・フレームワークは本プロジェクト側（uv / Vite+TypeScript / Pydantic v2 / `lifespan`）が優先。

## Backend
- `main.py`: 機能ごとのルーターを `app.include_router(router, prefix=..., tags=[...])` で登録する。DB 接続クライアントはアプリ起動時に生成して `app` 上に保持する。
  - ※ chapter9 は Motor だが、本プロジェクトは **PyMongo Async（`AsyncMongoClient`）** を `lifespan` で生成・保持する。
  - ※ chapter9 は `@app.on_event("startup"/"shutdown")` だが、本プロジェクトは `lifespan` で管理する。
- `routers/`: 機能単位で `APIRouter()` を分割する。ハンドラ内は DB ハンドル（`request.app.mongodb[...]` 相当）経由でアクセスする。
- 雛形の `utils/`（処理を小さな関数に分割し pipeline で合成する考え方）は踏襲するが、**本プロジェクトでは責務分割を `ARCHITECTURE.md` §2 の `routers/` / `core/` / `game/` の3層に拡張する**（雛形のように何でも `utils/` に置かない）。`utils.py` は時刻整形・ルームコード生成などの**汎用ヘルパ専用**とし、接続管理・状態ストア・判定エンジン等のドメイン/基盤ロジックは `core/` / `game/` に置く。
- `models.py`: Mongo 用ベースモデル（`_id` をエイリアスで扱う）＋ `Field(...)` でのバリデーション付きスキーマを定義する。
  - ※ 本プロジェクトは Pydantic v2 の `model_config` / `field_validator` で記述する（v1 の `class Config` / `validator` は使わない）。
- シードスクリプト: 設定を `python-decouple` で読み込み、CSV/JSON を読んで DB に投入する単発スクリプトを用意する。

## Frontend
- `Layout`: Header / 本文（`children`）/ Footer を縦積みするレイアウトコンポーネントを用意し、各画面は `components/` 配下に分割する。
  - ※ 本プロジェクトは Vite + TypeScript。Create React App の作法は踏襲しない。

## 本プロジェクトでの追加要素（chapter9 に無いもの）
- chapter9 は REST のみで WebSocket を含まない。リアルタイム層（`routers/ws.py`・`core/connection_manager.py`・`game/` 判定エンジン）は本プロジェクトで新規に設計・追加する（詳細は `ARCHITECTURE.md` §4〜§8）。
