# Third-party notices

Full lists: `uv.lock` (server) and `frontend/package-lock.json` (client); sources, data and images —
`ATTRIBUTION.md`. Checked 23.11.2026 with `importlib.metadata` and `package-lock.json`.

## Components under copyleft or weak-copyleft licences

| Component | Licence | Where used | What it means for us |
|---|---|---|---|
| `chess` / `python-chess` | GPL-3.0-or-later | server (move rules, PGN, tablebases) | GPL obliges to offer the source only when the program is **distributed**. The server runs on our own host and is not given to anyone. If server code, a Docker image or an archive is ever handed to others, GPL-3.0 applies to that distribution. |
| Stockfish | GPL-3.0 | server, separate process | Same. If a binary or image containing it is distributed, include the GPL text and the source (or a written offer): https://github.com/official-stockfish/Stockfish |
| `certifi`, `pathspec` | MPL-2.0 | server dependencies | Permits closed use; only changes to the MPL files themselves must be shared. |

The browser bundle has **no** GPL, LGPL or MPL dependencies (all runtime packages are MIT, ISC, BSD or Apache-2.0),
so nothing under GPL is sent to players' browsers. Re-check with `npm ls --omit=dev` and the lock file whenever a
client dependency is added.

## Permissive components

Everything else is MIT, BSD, ISC, Apache-2.0, PSF or similar: FastAPI, SQLAlchemy, Pydantic, Celery, redis-py,
React, React Router, Tailwind CSS, Recharts, date-fns, lucide (ISC), chess.js (BSD-2-Clause), and others. Their licence
texts are shipped with the packages. Keep their copyright notices when redistributing.

## Data and design assets

See `ATTRIBUTION.md`: lichess opening names (CC0), endgame tables (facts), champion portraits (public domain / CC0),
fonts and piece sets with their licences.
