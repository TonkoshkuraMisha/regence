# Catalog of tactical techniques and exercise themes

Development working document (in English). This is the **registry of themes** from which puzzles, lessons, trainers,
the player's "weak spots map" and the selection of exercises are built. The catalog is extensible: new themes and puzzles are added as
development proceeds, without breaking what is already done (the procedure is at the end of the document).

## How a theme is structured

Each theme has:

* a **code** (`snake_case`, English) - an immutable key in the database, API and message catalogs;
* a **name and explanation** in three languages - in the catalogs (`themes.<code>.name`, `.short`, `.explain`), not in code;
* a **section** (A-L below) and a **parent** (for example, "knight fork" → "fork");
* a **tagging source**: the motif detector (task 11.1) - `D`; a tag of the open lichess puzzle database - `L` (the correspondence of
  tags is checked at import, task 13.1); manual tagging only - `M`;
* a **goal** (task 27.8): `mate`, `material`, `promotion`, `invasion`, `draw`, `tempo` - the "technique × goal" classification.
  A theme has a goal set when the technique serves a single goal (mates, "save the game", passed pawns); for the others the puzzle sets it:
  the puzzle's goal is derived from its themes (mate > draw > promotion > material), and training by technique accepts `goal`;
* **steps**: 1 - introduction (the technique in pure form, 1 move), 2 - consolidation (2-3 moves, one obstacle),
  3 - combined with another technique, 4 - master (long calculation, a quiet move, the opponent's defense);
* a **minimum of puzzles** for each step to launch the theme (by default 25 / 25 / 20 / 15; a theme without the minimum
  does not appear in the "by theme" selection, but its puzzles take part in mixed selections).

## A. Double attack

| Code | Technique | Tagging |
|---|---|---|
| `fork` | Fork - one piece attacks two targets | D, L |
| `fork_knight` | Knight fork (including the "family" fork - king, queen, rook) | D |
| `fork_pawn` | Pawn fork | D |
| `fork_bishop` | Bishop fork | D |
| `fork_rook` | Rook fork | D |
| `fork_queen` | Queen fork (including a mate threat + a piece) | D |
| `fork_king` | King fork | D |
| `double_attack` | A double threat by different means (a move creates two threats, not necessarily with one piece) | D, M |
| `double_check` | Double check | D, L |

## B. Line strikes

| Code | Technique | Tagging |
|---|---|---|
| `pin` | Pin: absolute (against the king) and relative | D, L |
| `pin_exploit` | Exploiting a pin - attacking the pinned piece | D |
| `skewer` | Skewer (a line strike through a piece) | D, L |
| `x_ray` | X-ray - acting through a piece | D, L |
| `discovered_attack` | Discovered attack | D, L |
| `discovered_check` | Discovered check | D |
| `windmill` | "Windmill" - a series of discovered checks | M |
| `battery` | Battery: queen + rook / queen + bishop, doubling rooks | D |

## C. Removing the defense

| Code | Technique | Tagging |
|---|---|---|
| `remove_defender` | Destroying the defender | D, L |
| `deflection` | Deflection - the defender is led away from its post | D, L |
| `decoy` | Decoy - the opponent's piece is forced onto a fatal square | D, L |
| `overload` | Overload - one piece defends two things | D |
| `undermining` | Undermining - a strike at the base of the defense (often with a pawn) | M |
| `interference` | Interference with the line of defense | D, L |
| `clearance` | Clearing a square or a line (by a sacrifice or a tempo) | L, M |
| `intermezzo` | Intermediate move | L |
| `quiet_move` | A quiet move in a combination | L |
| `desperado` | Desperado piece - sells itself as dearly as possible | M |
| `hanging_piece` | Hanging piece - capture it or defend it | D, L |

## D. Trapping, restriction, special positions

| Code | Technique | Tagging |
|---|---|---|
| `trapped_piece` | Trapping a piece | D, L |
| `domination` | Domination - the piece has nowhere to go | M |
| `zugzwang` | Zugzwang | L |
| `perpetual_check` | Perpetual check (a rescue) | M |
| `stalemate_trick` | A stalemate rescue combination | M |
| `fortress` | Fortress | M |
| `en_passant` | En passant capture in tactics | L |
| `castling_tactic` | Tactics with castling (long castling with check, a ban on castling) | L, M |
| `perpetual_attack` | Perpetual attack on a piece (a rescue, the goal is a draw) | M |

## E. Pawns

| Code | Technique | Tagging |
|---|---|---|
| `promotion` | Promotion | L |
| `underpromotion` | Underpromotion (to a knight - with check/fork, to a rook/bishop - avoiding stalemate) | L |
| `pawn_breakthrough` | Pawn breakthrough | M |
| `pawn_race` | Pawn race | M |
| `advanced_pawn` | A far-advanced pawn as an attacking force | L |
| `passed_pawn_support` | Supporting/stopping a passed pawn | M |

## F. Mating patterns

| Code | Pattern | Tagging |
|---|---|---|
| `mate_in_1` … `mate_in_5` | Mate in N moves (general calculation training; `mate_in_5` - 5 or more, like the database tag `mateIn5`) | L, D |
| `back_rank_mate` | Back-rank mate | D, L |
| `smothered_mate` | Smothered mate | L |
| `anastasia_mate` | Anastasia's mate (knight + rook on the edge) | L |
| `arabian_mate` | Arabian mate (rook + knight in the corner) | L |
| `boden_mate` | Boden's mate (two bishops crossing) | L |
| `double_bishop_mate` | Double bishop mate in an attack | L |
| `dovetail_mate` | Dovetail mate | L |
| `epaulette_mate` | Epaulette mate | M |
| `hook_mate` | Hook mate (rook + knight + pawn) | L |
| `opera_mate` | Opera mate (rook + bishop on the edge) | M |
| `legal_mate` | Légal's mate | M |
| `greco_mate` | Greco's mate | M |
| `damiano_mate` | Damiano's mate | M |
| `lolli_mate` | Lolli's mate | M |
| `pillsbury_mate` | Pillsbury's mate | M |
| `morphy_mate` | Morphy's mate (bishop + rook) | M |
| `blackburne_mate` | Blackburne's mate | M |
| `corridor_mate` | Corridor mate | M |
| `queen_kiss_mate` | "Queen's kiss" - a mate by the queen right next to the king with support | M |
| `vukovic_mate` | Vuković's mate (rook + knight) | L |

## G. Attack on the king

| Code | Technique | Tagging |
|---|---|---|
| `greek_gift` | Bishop sacrifice on h7/h2 | M |
| `double_bishop_sacrifice` | Sacrifice of two bishops on h7 and g7 | M |
| `f7_f2_attack` | Attack on f7/f2 (including early) | L |
| `exposed_king` | Attack on an exposed/uncastled king | L |
| `kingside_attack` / `queenside_attack` | Attack on the castled position | L |
| `rook_lift` | Bringing a rook in along the rank | M |
| `pawn_storm` | Pawn storm with opposite-side castling | M |
| `sacrifice` | Sacrifice in general (material for an attack) | L |

## H. Opening traps and mistakes

| Code | Technique | Tagging |
|---|---|---|
| `opening_trap` | A trap in the opening (general theme) | M |
| `early_queen` | Punishing an early queen development | M |
| `trap_noahs_ark` | "Noah's Ark" - trapping a bishop with pawns | M |
| `trap_fishing_pole` | "Fishing pole" | M |
| `trap_elephant` | "Elephant trap" | M |
| `trap_lasker` | Lasker's trap | M |
| `trap_scholars_mate` | Scholar's mate and the defense against it | M |
| `development_lag` | Punishing a lag in development | D, M |

## I. Defense (puzzles "for the defender")

| Code | Technique | Tagging |
|---|---|---|
| `find_the_threat` | Find the opponent's threat (what does he want?) | D |
| `defensive_move` | The only defense | L |
| `counterattack` | Defense by counterattack | M |
| `save_by_perpetual` | Rescue by perpetual check | M |
| `save_by_stalemate` | Rescue by stalemate | M |
| `blunder_check` | "Don't blunder": of three natural moves only one does not lose | D |

## J. Endgame technique

| Code | Technique | Tagging |
|---|---|---|
| `opposition` | Opposition (direct, distant, diagonal) | M |
| `triangulation` | Triangulation | M |
| `square_rule` | The rule of the square | M |
| `key_squares` | Key squares | M |
| `outflanking` / `shouldering` | Outflanking, shouldering | M |
| `lucena` | Lucena position | M |
| `philidor_position` | Philidor position | M |
| `rook_behind_passer` | Rook behind the passed pawn | M |
| `wrong_bishop` | The "wrong" bishop | M |
| `opposite_bishops` | Opposite-colored bishops (defense) | M |
| `rook_vs_minor` | Rook against bishop or knight (defense) | M |
| `basic_mates` | Mate with the queen, rook, two bishops, bishop and knight | M |

## K. Calculation and combining techniques

| Code | Technique | Tagging |
|---|---|---|
| `combination` | A combination of two or more techniques (a puzzle has several themes) | L, D |
| `long_calculation` | A long forcing variation (5+ moves) | L |
| `equality` | A "save yourself" puzzle: the best move leads to equality | L |
| `candidate_moves` | Find all strong candidate moves | M |
| `tempo_gain` | Gaining a tempo: a useful move with a threat | M |
| `unstoppable_threat` | Unstoppable threat (a quiet move with no defense) | M |
| `critical_position` | Critical position: the moment where the game is decided | M |

## L. Positional themes ("choose a plan" exercises)

| Code | Theme | Tagging |
|---|---|---|
| `outpost` | An outpost for a knight | M |
| `open_file` | Seizing an open file | D |
| `seventh_rank` | Rook on the 7th rank | D |
| `bad_bishop` | Bad bishop, exchanging "good for bad" | M |
| `weak_squares` | Weak squares, "holes" | M |
| `isolated_pawn` | Playing against / with an isolated pawn | M |
| `minority_attack` | Minority attack | M |
| `piece_improvement` | Improving the worst piece | M |
| `prophylaxis` | Prophylaxis | M |
| `exchange_choice` | Which exchange is correct | M |
| `blockade` | Blockade of a passed or isolated pawn | M |
| `overprotection` | Overprotection of a key point | M |
| `centralization` | Centralization of pieces | M |
| `pawn_chain` | Pawn chain and attack on its base | M |
| `restriction` | Restricting the opponent's pieces and pawn breaks | M |
| `bishop_pair` | Advantage of the two bishops | M |

## How to add

1. **A new theme**: an entry in the registry `src/services/themes.py` (code, section, parent, tagging sources, lichess
   tags, detector codes) + the keys `themes.<code>.name / .short / .explain` in all three catalogs
   (`frontend/src/i18n/messages/*.ts`; the explanation is 2-4 sentences, as a coach to a student) + a row in this document.
   `tests/test_themes.py` checks the codes, sections, parents, texts in three languages and that the theme is present here.
   The client receives the registry through `GET /api/v1/themes`; a theme without texts is simply not shown by an old client.
2. **New puzzles**: import from the open database by tag (`L`), automatic tagging by the detector (`D`) or a file
   of manual puzzles in the repository (`M`: FEN, solution, themes, step, source). A check script (in CI): the moves are legal,
   the solution is unique (the engine offline: the best move leads the second by >= 200 cp or is the only one leading to mate),
   the stated theme is confirmed by the detector where it can see it.
3. A theme enters the "by theme" selection when the minimum of puzzles per step is reached; until then, only in mixed selections.
