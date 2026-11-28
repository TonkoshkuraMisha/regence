# Third-party works in the project: authors and licences

Project rule: an asset (piece set, portrait, sound, texture, font, database) is added only together with an
entry in this file — source, author, licence. If there is no clear licence that allows use in any project, the
asset is not added. `tests/test_assets_licensing.py` checks that this file matches the repository contents; the
same list is shown to users on the `/about` page.

## Chess engine

| What | Author | Licence | How it is used |
|---|---|---|---|
| [Stockfish](https://github.com/official-stockfish/Stockfish) | The Stockfish developers | GPL-3.0 | A separate program, launched through `EnginePool`; unmodified. In the Docker image it is installed with the Debian package `stockfish`; locally — `scripts/setup_stockfish.py` (the `bin/` folder is not in git). |

## Piece sets — `frontend/public/assets/pieces/`

Downloaded by `scripts/setup_piece_sets.py` from the repository [lichess-org/lila](https://github.com/lichess-org/lila);
authors and licences are as in its [COPYING.md](https://github.com/lichess-org/lila/blob/master/COPYING.md).

| Folder | Author | Licence |
|---|---|---|
| `merida` | Armando Hernandez Marroquin | GPL-2.0-or-later |
| `cburnett` | Colin M.L. Burnett | GPL-2.0-or-later |
| `chessnut` | Alexis Luengas | Apache-2.0 |
| `fantasy` | Maurizio Monge | MIT |
| `rhosgfx` | RhosGFX | CC0-1.0 |
| `mpchess` | Maxime Chupin | GPL-3.0-or-later |
| `celtic` | Maurizio Monge | MIT |
| `spatial` | Maurizio Monge | MIT |
| `papercut` | Nikolay Anzarov | CC-BY-4.0 |
| `totoy` | Kosal Sen | CC-BY-4.0 |
| `pirouetti` | pirouetti | AGPL-3.0-or-later |
| `pixel` | therealqtpi | AGPL-3.0-or-later |
| `firi` | James Faure | CC-BY-4.0 |
| `shapes` | flugsio | CC-BY-SA-4.0 |
| `letter` | usolando | AGPL-3.0-or-later |
| `outline` | regence, derived from `merida` (an outline added) | GPL-2.0-or-later |
| `lewis` | regence, own drawing inspired by the 12th-century Lewis chessmen (public domain); `scripts/build_lewis_pieces.py` | CC0-1.0 |

Player avatars (task 18.4) are pieces of the `lewis` set on a coloured background (`frontend/src/components/PlayerAvatar.tsx`);
the external avatar service (DiceBear) is no longer used.

App icons (task 24.2, `frontend/public/icons/`: `icon.svg`, PNG 192/512, maskable, `apple-touch-icon.png`) — the
knight of the `rhosgfx` set (CC0-1.0) on regence's own background and frame; built by `scripts/dev/build_pwa_icons.mjs`.

Removed as non-free: `alpha` (Eric Bentzen, "free for personal non commercial use"), `maestro` (sadsnake1,
CC BY-NC-SA 4.0), and a set of unknown origin that lay in the folder root and in `classic/`.

## Chess player portraits — `frontend/public/assets/champions/`

Downloaded by `scripts/download_champions.py` from Wikimedia Commons (a reduced copy 500 pixels wide) and only
under a free licence; manifest — `frontend/src/config/portraitCredits.json`. Works under CC BY-SA are distributed
on the same terms. The copies of seven portraits in `frontend/src/assets/champions/` are the same files.

| File | Source file on Wikimedia Commons | Author | Licence |
|---|---|---|---|
| `philidor.jpg` | [Francois-Andre Danican Philidor.jpg](https://commons.wikimedia.org/wiki/File:Francois-Andre_Danican_Philidor.jpg) | Augustin de Saint-Aubin | Public domain |
| `labourdonnais.jpg` | [Louisdelabourdonnais.jpg](https://commons.wikimedia.org/wiki/File:Louisdelabourdonnais.jpg) | The original uploader was Jaapvanderkooij at Dutch Wikipedia. | Public domain |
| `staunton.jpg` | [Howard-Staunton-ILN.jpeg](https://commons.wikimedia.org/wiki/File:Howard-Staunton-ILN.jpeg) | R. & E. Taylor (Firm) / After Thomas Dewell Scott | Public domain |
| `anderssen.jpg` | [Anderssen, Adolf "-5" - DPLA - 9ca464339f18b3d8be87fccc68c3ee73 (cropped).jpg](https://commons.wikimedia.org/wiki/File:Anderssen,_Adolf_%22-5%22_-_DPLA_-_9ca464339f18b3d8be87fccc68c3ee73_(cropped).jpg) | Unknown author | Public domain |
| `morphy.jpg` | [PaulmorphyHair.jpg](https://commons.wikimedia.org/wiki/File:PaulmorphyHair.jpg) | Unknown author | Public domain |
| `paulsen.jpg` | [LouisPaulsen.jpg](https://commons.wikimedia.org/wiki/File:LouisPaulsen.jpg) | The original uploader was Miastko at German Wikipedia. | Public domain |
| `zukertort.jpg` | [Zukertort, Johannes Hermann "-1" - DPLA - 178f6bd2074f2347becb2e4ebeabd45b (cropped).jpg](https://commons.wikimedia.org/wiki/File:Zukertort,_Johannes_Hermann_%22-1%22_-_DPLA_-_178f6bd2074f2347becb2e4ebeabd45b_(cropped).jpg) | Unknown author | Public domain |
| `Steinitz.jpg` | [Steinitz, William-4 - DPLA - 9eeab9ac335135c24b69ab7e36fc5354 (cropped).jpg](https://commons.wikimedia.org/wiki/File:Steinitz,_William-4_-_DPLA_-_9eeab9ac335135c24b69ab7e36fc5354_(cropped).jpg) | Schumann, Fritz | Public domain |
| `Lasker.jpg` | [Bundesarchiv Bild 102-00457, Emanuel Lasker.jpg](https://commons.wikimedia.org/wiki/File:Bundesarchiv_Bild_102-00457,_Emanuel_Lasker.jpg) | Unknown author | CC BY-SA 3.0 de |
| `Rubinstein.jpg` | [Akiba-Rubinstein.png](https://commons.wikimedia.org/wiki/File:Akiba-Rubinstein.png) | Unknown author | Public domain |
| `Capablanca.jpg` | [José Raúl Capablanca 1931.jpg](https://commons.wikimedia.org/wiki/File:Jos%C3%A9_Ra%C3%BAl_Capablanca_1931.jpg) | Unknown author (Keystone-France) | Public domain |
| `Alekhine.jpg` | [Alexandre Alekhine Color.jpg](https://commons.wikimedia.org/wiki/File:Alexandre_Alekhine_Color.jpg) | Alexandre_Alekhine_01.jpg: George Grantham Bain Collection (Library of Congress) derivative work: JesusAngelRey (talk) | Public domain |
| `Euwe.jpg` | [Max Euwe (1945).jpg](https://commons.wikimedia.org/wiki/File:Max_Euwe_(1945).jpg) | Theo van Haren Noman / Anefo | CC BY-SA 3.0 nl |
| `Keres.jpg` | [Hoogoven Schaaktoernooi Keres, Bestanddeelnr 922-0145.jpg](https://commons.wikimedia.org/wiki/File:Hoogoven_Schaaktoernooi_Keres,_Bestanddeelnr_922-0145.jpg) | Eric Koch for Anefo | CC0 |
| `Botvinnik.jpg` | [Mikhail Botvinnik 1962.jpg](https://commons.wikimedia.org/wiki/File:Mikhail_Botvinnik_1962.jpg) | Harry Pot for Anefo | CC BY-SA 3.0 nl |
| `Geller.jpg` | [Efim Geller 1977b.jpg](https://commons.wikimedia.org/wiki/File:Efim_Geller_1977b.jpg) | Suyk, Koen / Anefo | CC0 |
| `Korchnoi.jpg` | [Max Euwe Schaakvierkamp in Amsterdam Kortsjnoj (close), Bestanddeelnr 933-9735 (cropped).jpg](https://commons.wikimedia.org/wiki/File:Max_Euwe_Schaakvierkamp_in_Amsterdam_Kortsjnoj_(close),_Bestanddeelnr_933-9735_(cropped).jpg) | Bart Molendijk / Anefo | CC0 |
| `Smyslov.jpg` | [Interpolisschaaktoernooi Tilburg 1819 Smyslov aan zet, Bestanddeelnr 929-3630.jpg](https://commons.wikimedia.org/wiki/File:Interpolisschaaktoernooi_Tilburg_1819_Smyslov_aan_zet,_Bestanddeelnr_929-3630.jpg) | Koen Suyk / Anefo | CC0 |
| `Tal.jpg` | [Hoogovenschaaktoernooi, de Rus M. Tal, Bestanddeelnr 920-9788.jpg](https://commons.wikimedia.org/wiki/File:Hoogovenschaaktoernooi,_de_Rus_M._Tal,_Bestanddeelnr_920-9788.jpg) | Ron Kroon for Anefo | CC0 |
| `Petrosian.jpg` | [Tigran Petrosian 1962.jpg](https://commons.wikimedia.org/wiki/File:Tigran_Petrosian_1962.jpg) | Harry Pot / Anefo | CC0 |
| `Spassky.jpg` | [Dhr. Boris Spassky, Bestanddeelnr 932-7320.jpg](https://commons.wikimedia.org/wiki/File:Dhr._Boris_Spassky,_Bestanddeelnr_932-7320.jpg) | Rob Bogaerts for Anefo | CC0 |
| `Fischer.jpg` | [Bobby Fischer 1972.jpg](https://commons.wikimedia.org/wiki/File:Bobby_Fischer_1972.jpg) | Bert Verhoeff for Anefo | CC0 |
| `Karpov.jpg` | [Anatoly Karpov 2017 april.jpg](https://commons.wikimedia.org/wiki/File:Anatoly_Karpov_2017_april.jpg) | Veni Markovski | CC BY-SA 4.0 |
| `Kasparov.jpg` | [Garry Kasparov European Union 2023 (cropped).jpg](https://commons.wikimedia.org/wiki/File:Garry_Kasparov_European_Union_2023_(cropped).jpg) | Lukasz Kobus | CC BY 4.0 |
| `Kramnik.jpg` | [Candidates Tournament 2018, Vladimir Kramnik.jpg](https://commons.wikimedia.org/wiki/File:Candidates_Tournament_2018,_Vladimir_Kramnik.jpg) | Vladimir Barskij | CC BY-SA 3.0 |
| `Anand.jpg` | [Viswanathan Anand (2016).jpeg](https://commons.wikimedia.org/wiki/File:Viswanathan_Anand_(2016).jpeg) | Wolfgang Jekel | CC BY 2.0 |
| `Carlsen.jpg` | [Magnus Carlsen in 2025.jpg](https://commons.wikimedia.org/wiki/File:Magnus_Carlsen_in_2025.jpg) | Miroslav.vajdic | CC BY 4.0 |
| `Ding.jpg` | [DingLiren24a.jpg](https://commons.wikimedia.org/wiki/File:DingLiren24a.jpg) | Stefan64 | CC BY-SA 3.0 |
| `Chigorin.jpg` | [Mikhail Ivanovich Chigorin.jpg](https://commons.wikimedia.org/wiki/File:%D0%9C%D0%B8%D1%85%D0%B0%D0%B8%D0%BB_%D0%98%D0%B2%D0%B0%D0%BD%D0%BE%D0%B2%D0%B8%D1%87_%D0%A7%D0%B8%D0%B3%D0%BE%D1%80%D0%B8%D0%BD.jpg) | Unknown author | Public domain |
| `Tarrasch.jpg` | [Tarrasch, Siegbert-2 - DPLA - 224f35dc323734bf355cc7c94d0ded68 (cropped).jpg](https://commons.wikimedia.org/wiki/File:Tarrasch,_Siegbert-2_-_DPLA_-_224f35dc323734bf355cc7c94d0ded68_(cropped).jpg) | Unknown author | Public domain |
| `Pillsbury.jpg` | [Pillsbury, Harry Nelson, as a Young Man - DPLA - bcd01a18c987fea609e21f290ce181be (cropped).jpg](https://commons.wikimedia.org/wiki/File:Pillsbury,_Harry_Nelson,_as_a_Young_Man_-_DPLA_-_bcd01a18c987fea609e21f290ce181be_(cropped).jpg) | Unknown author | Public domain |
| `Marshall.jpg` | [Frank Marshall (chess player).jpg](https://commons.wikimedia.org/wiki/File:Frank_Marshall_(chess_player).jpg) | Oxford and Dilhoff | Public domain |
| `Nimzowitsch.jpg` | [Aron Nimzowitsch.jpg](https://commons.wikimedia.org/wiki/File:Aron_Nimzowitsch.jpg) | Not mentioned | Public domain |
| `Reti.jpg` | [RichardReti.jpg](https://commons.wikimedia.org/wiki/File:RichardReti.jpg) | Unknown author | Public domain |
| `Tartakower.jpg` | [Ksawery Tartakower.jpg](https://commons.wikimedia.org/wiki/File:Ksawery_Tartakower.jpg) | Unknown author | Public domain |

The same portraits (only public domain and CC0 from the table above: Philidor, Staunton, Zukertort, Marshall, Keres,
Rubinstein, Paulsen, Labourdonnais; Morphy, Capablanca, Alekhine, Steinitz, Tal, Tarrasch, Pillsbury, Anderssen), as
small sepia images, serve as the background of the "Maintenance" page (`frontend/public/maintenance.html`) and the
waiting page (`ops/landing`); built by `scripts/dev/build_error_pages.py`. CC BY-SA and CC BY works are not used on
these pages.

## Sounds and textures

| What | Source | Licence |
|---|---|---|
| Move and alert sounds | Synthesised in the browser (`frontend/src/services/soundEngine.ts`), no recordings | own work |
| `frontend/public/assets/textures/wood-grain.svg` | Project procedural graphics (SVG filter) | own work, CC0-1.0 |
| `frontend/public/assets/textures/wood-fine.svg` | Project procedural graphics (SVG), fine wood fibres (oak, cherry, ebony) — task 18.1 boards | own work, CC0-1.0 |
| `frontend/public/assets/textures/marble.svg` | Project procedural graphics (SVG), marble veining (white and green) — task 18.1 boards | own work, CC0-1.0 |
| `frontend/public/assets/textures/stone.svg` | Project procedural graphics (SVG), stone grain — task 18.1 boards | own work, CC0-1.0 |
| `frontend/public/assets/textures/brushed-metal.svg` | Project procedural graphics (SVG), brushed metal — task 18.1 boards | own work, CC0-1.0 |
| `frontend/public/assets/textures/leather.svg` | Project procedural graphics (SVG), leather texture — task 18.1 boards | own work, CC0-1.0 |
| `frontend/public/assets/textures/paper.svg` | Project procedural graphics (SVG), old paper — task 18.1 boards | own work, CC0-1.0 |
| `frontend/public/assets/textures/chalk.svg` | Project procedural graphics (SVG), chalk dust (school blackboard) — task 18.1 boards | own work, CC0-1.0 |
| `frontend/public/assets/textures/stained-glass.svg` | Project procedural graphics (SVG), stained-glass leading — task 18.1 boards | own work, CC0-1.0 |
| `frontend/public/assets/textures/glass.svg` | Project procedural graphics (SVG), glass glare — task 18.1 boards | own work, CC0-1.0 |
| `frontend/public/assets/textures/hatch.svg` | Project procedural graphics (SVG), newspaper diagram hatching — task 18.1 boards | own work, CC0-1.0 |
| `frontend/public/assets/patterns/celtic.svg` | Embossed page-background tile (SVG), Celtic knot — task 18.1 | own work, CC0-1.0 |
| `frontend/public/assets/patterns/map.svg` | Embossed page-background tile (SVG), antique map — task 18.1 | own work, CC0-1.0 |
| `frontend/public/assets/patterns/manuscript.svg` | Embossed page-background tile (SVG), manuscript — task 18.1 | own work, CC0-1.0 |
| `frontend/public/assets/patterns/circuit.svg` | Embossed page-background tile (SVG), circuit board — task 18.1 | own work, CC0-1.0 |
| `frontend/public/assets/patterns/bauhaus.svg` | Embossed page-background tile (SVG), Bauhaus geometry — task 18.1 | own work, CC0-1.0 |
| `frontend/public/assets/patterns/marble.svg` | Embossed page-background tile (SVG), marble veining — task 18.1 | own work, CC0-1.0 |
| `frontend/public/assets/patterns/leaves.svg` | Embossed page-background tile (SVG), autumn leaves and chestnuts — task 31.1 | own work, CC0-1.0 |
| `frontend/public/assets/patterns/parquet.svg` | Embossed page-background tile (SVG), herringbone parquet — task 31.1 | own work, CC0-1.0 |
| `frontend/public/assets/patterns/notebook.svg` | Embossed page-background tile (SVG), squared notebook — task 31.1 | own work, CC0-1.0 |

Removed: `Move.mp3`, `Capture.mp3`, `GenericNotify.mp3` (lichess sounds that its COPYING.md classes as non-free) and
`wood-grain.png` (origin unknown).

## External services

| What | Author | Terms | Note |
|---|---|---|---|
| Endgame tablebases — open API of [lichess](https://tablebase.lichess.ovh) (`TABLEBASE_URL`) | lichess.org (lila-tablebase server; Syzygy and other tables) | Open service | Development only: a single position (FEN) is sent to the server, with no player data. In production — our own tablebase server (owner decision, DEPLOY). |
| Import of a player's games (task 24.1): open API of [lichess](https://lichess.org/api) (`GAME_IMPORT_LICHESS_URL`, `/api/games/user/{username}`) and Published-Data API of [chess.com](https://www.chess.com/news/view/published-data-api) (`GAME_IMPORT_CHESSCOM_URL`, `/pub/player/{username}/games/…`) | lichess.org; Chess.com | Open APIs without a key; the player makes the request for their own games | Only the username entered by the player is sent to the site; the client identifies itself with the generic name `regence-game-import`, with no login or tokens. One request to a site at a time; a 429 response pauses that site for 60 s. Moves and game headers are stored without comments or third-party evaluations (`imported_games`). |

## Data

| What | Source | Status |
|---|---|---|
| Archive of historical games | PGN collections of pgnmentor.com (`src/db/seed.py`), downloader `scripts/chessgames_downloader.py` | A record of a game's moves is a fact and is not protected by copyright. The terms of the source sites and the rights to the selection as a database have not been checked — see "Open questions". |
| Endgame technique puzzles (`data/puzzles/endgame_generated.csv.gz`) | Own positions built by `scripts/dev/build_endgame_puzzles.py`; the correctness of the only move was verified against the open lichess endgame tablebase API (Syzygy tables) | A position and its tablebase result are facts; the selection and tagging are our own. Only positions (FEN) were sent to the tablebase server. |
| Openings table (`src/services/data/openings.tsv`) | [lichess-org/chess-openings](https://github.com/lichess-org/chess-openings) — ECO codes and names; converted by `scripts/build_openings.py` (position instead of moves) | CC0-1.0 (the repository licence was checked on 15.11.2026). |
| Bot opening books (`src/services/bots/books/*.json`) | Built by `scripts/build_opening_books.py` from the same games | Move statistics, own processing. |
| Studies of the endgame trainer (`frontend/src/content/endgames.json`: `study_*`, task 27.9) | F. Saavedra's position (1895, from the Barbier game) and R. Reti's study (Ostrauer Morgenzeitung, 1921); J. Kling and B. Horwitz's rook defence (shown in the Wikipedia article on J. Kling; their *Chess Studies*, 1851); A. Troitzky (1909); N. Grigoriev (3rd prize, Shakhmat, 1928; 1930; two of 1936). Positions as printed in the Wikipedia articles on the composers and on the endgame study. The composers died in 1922, 1929, 1876, 1885, 1942 and 1938 | A position is a fact; the explanation texts are our own, verification is by endgame tablebases. |
| Library collection "Masters' games" and the masters' opening books 21.5 (`src/services/bots/books/*.json`) | Player files from pgnmentor.com (Chigorin, Tarrasch, Pillsbury, Marshall, Nimzowitsch, Reti, Tartakower, Botvinnik, Tal, Petrosian), loaded by `scripts/import_library.py` | Game moves are facts; the source site's terms — see "Open questions", as for the archive of historical games. |
| Game library (`library_*`, tasks 27.1–27.3) | Collections and databases of the project owner: PGN files he gathered and teaching databases from his library; loaded by `scripts/import_library.py` (and `scripts/cbh_to_pgn.py`), not included in the repository | Only headers and the main line are facts; comments, variations and exercises from published editions are not taken. The "Beautiful games" and opening repertoire collections were compiled by the owner. |

## Software libraries

Full lists — `uv.lock` and `frontend/package.json`. Main ones: FastAPI, SQLAlchemy, Pydantic, Celery,
redis-py (MIT / BSD); React, React Router, Tailwind CSS, Recharts, date-fns (MIT); lucide (ISC); chess.js
(BSD-2-Clause); **python-chess (GPL-3.0)**.

Information on the binary format of teaching databases (move encoding tables) for `src/services/cbh_reader.py` was
taken from the open converter [cbh2pgn](https://github.com/asdfjkl/cbh2pgn) — © 2022 Dominik Klein, MIT licence. The
module code is our own; it is a development tool and is not used in the product.

## Open questions

* **python-chess — GPL-3.0.** As long as the server runs as a network service and its code is not handed to
  anyone, GPL-3.0 creates no obligations. If the server code is distributed (including as a closed product), it must
  be distributed under GPL-3.0.
* **The `LICENSE` file** — a draft proprietary licence was added on 23.11.2026 (`THIRD_PARTY_NOTICES.md` — third-party
  components); the owner's decision (proprietary or AGPL-3.0, private repository) — `docs/owner-decisions/02-legal-and-licenses.md`.
* **PGN sources** (terms checked on 23.11.2026 — `docs/owner-decisions/pgn-sources.md`: pgnmentor.com has no licence,
  chessgames.com is closed). Before a public launch it is worth switching to a collection with explicit permission to
  use it, or checking the terms of pgnmentor.com and chessgames.com.

Closed: the external avatar service (DiceBear) was removed in task 18.4 — avatars now come from our own set, and
the player's name is not sent to a third-party service.
