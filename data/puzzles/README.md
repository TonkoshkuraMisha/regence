# Puzzles

`lichess_subset.csv.gz` - a selection from the open lichess puzzle database (https://database.lichess.org/#puzzles),
licence **CC0** (public domain). Selection: `scripts/dev/build_puzzle_subset.py` - stable rating
(deviation <= 80), popularity >= 85, at least 300 plays; rating 600-2600 evenly across buckets of 100 points
and a quota for each tag that the theme registry maps to its own theme.

Columns: `PuzzleId, FEN, Moves, Rating, RatingDeviation, Popularity, NbPlays, Themes` - as in the source database:
FEN is the position before the opponent's move, the first move in `Moves` is the opponent's move, then the solution and replies alternate.

`lichess_themes_extra.csv.gz` - a supplement from the same database (CC0) for themes without lichess tags (task 27.8): themes are counted
by the recognisers in `src/services/theme_detectors.py` and the mate classifier, the quota is the shortfall of a theme to the tier minimum in
the main selection. Build: `uv run --with zstandard python -m scripts.dev.build_theme_extra <database.csv.zst>`.
The same file also holds "save the game" puzzles (27.11): the solver is at least 3 points down and saves the game with
a perpetual check or a stalemate, and Stockfish confirms the first move is the only one that keeps the balance.
They are appended (the file's other rows are kept) by
`uv run --with zstandard python -m scripts.dev.build_save_puzzles <database.csv.zst>`; run it after `build_theme_extra`,
which rewrites the file.

`endgame_generated.csv.gz` - our own puzzles on endgame technique (opposition, key squares, outflanking, the rule of the square,
the "wrong" bishop) and on the stalemate defence of a queen against a bishop or rook pawn on the seventh (task 27.9, theme
`save_by_stalemate` for "Save the game"): the open database has almost none. The positions are built by `scripts/dev/build_endgame_puzzles.py` and verified against
endgame tablebases: a puzzle is taken only if exactly one move is correct. Same format; the theme is the tag
`regence:<registry code>`, the source in the database is `regence` (until 19.11.2026 - `michess`; old records were renamed by a migration). Build (needs network, about an hour):
`uv run python -m scripts.dev.build_endgame_puzzles`.

Loading into the server database: `python -m scripts.import_puzzles` (after migrations; re-running is safe).
