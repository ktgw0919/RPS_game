# RPS Frontend

React 18 + Vite + TypeScript (strict) + Tailwind CSS. SPA for the realtime
Rock-Paper-Scissors game. See `../docs/ARCHITECTURE.md` and `../docs/SCREENS.md`.

## Requirements

- Node.js 20+

## Setup

```powershell
# from frontend/
npm install
```

## Run

```powershell
npm run dev        # Vite dev server on http://localhost:5173
```

The dev server proxies `/rooms`, `/health`, and `/ws` to the backend on
`http://localhost:8000` (see `vite.config.ts`).

## Quality

```powershell
npm run lint          # ESLint
npm run format:check  # Prettier
npm run build         # tsc -b (strict) + vite build
```

## Layout (ARCHITECTURE.md §2)

```
src/
  main.tsx          # entry
  App.tsx           # root component (Phase 1 placeholder home)
  index.css         # Tailwind v4 entry (@import "tailwindcss")
  components/        # Layout, screens (Lobby/GameBoard/... in Phase 4)
  hooks/             # useWebSocket.ts (Phase 4)
  types/             # WS message + domain types (Phase 4)
  lib/constants.ts   # protocol constants mirrored from the backend
```
