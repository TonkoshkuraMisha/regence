<!-- --- FILE: frontend/README.md --- -->

# regence client

A single-page application: React 19, TypeScript, Vite 6, Tailwind CSS v4. The overall project structure is in
[../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md); here is only what is needed to work on the client.

## Commands

    npm install            # packages strictly per package-lock.json
    npm run dev            # Vite at http://127.0.0.1:3000 (the API is expected at 127.0.0.1:8000)
    npm run lint           # Oxlint
    npm run test           # Vitest, all tests
    npx vitest run src/components/arena --reporter=dot    # tests of one section
    npm run build          # type check (tsc -b) and build - the same as CI does
    npm run test:e2e       # Playwright: needs a running stack; in CI it runs on built images

Before pushing a branch, always run `npm run build`: it catches type errors that neither the linter nor Vitest sees.

## Where things live

| Folder | What is in it |
|---|---|
| `src/App.tsx` | Header, menu, all routes |
| `src/components/Chessboard.tsx`, `src/components/chessboard/` | The main board (game against a human, against a bot, analysis) and its panels; logic is in the `chessboard/hooks/` hooks |
| `src/components/<section>/` | Section pages: `arena`, `puzzles`, `learn`, `tournaments`, `library`, `repertoire`, `social`, `trainers` and others |
| `src/services/` | One file per API section (`arenas.ts`, `puzzles.ts`...), WebSocket (`gameSocket.ts`), sound, sign-in |
| `src/config/` | Appearance, bot and time control data |
| `src/content/` | Learning content: the Great Course, programs, endgame exercises |
| `src/trainers/` | Trainer logic (pure functions, covered by tests) |
| `src/i18n/` | Message catalogs `messages/{en,uk}.ts` and translation functions |
| `e2e/` | Playwright scenarios: a game between two players, puzzles, phone layout and others |
| `public/` | Assets (pieces, boards, sounds, portraits) and the service worker; licences are in `../ATTRIBUTION.md` |

## Rules

* **No player-facing strings in markup.** Text comes from the catalogs: `const {t} = useI18n(); t('arenas.title')`.
  A new key is added to all three catalogs at once with the same parameters; the tests check this.
* **Server errors arrive as codes** (`src/services/apiErrors.ts`): the text by code comes from the `serverErrors` section
  of the catalog, so a new server code requires strings in all three catalogs.
* **The server is the source of truth.** The clock, rating, puzzle solution and game result are computed by the server; the client shows
  what was sent and does not trust its own calculations where the result depends on them.
* **Layout is checked on a phone.** A new page without parameters is added to the `ROUTES` list in
  `e2e/layout.e2e.ts`. Local width measurements are understated: in CI (Linux) text is 9-10% wider.
* **Assets** only with a free licence and an entry in `../ATTRIBUTION.md`.
