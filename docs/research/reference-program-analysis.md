# Analysis of a reference chess training program (2007)

Development working document. The project owner provided an installed copy of a classic commercial
chess training program from 2007 (the "grandmaster" edition release, Russian localization) for study. Studied: the user
manual (44 pp.), the ReadMe, the curriculum (`Curriculum.dat`), the lesson format (`*.tut`), 188 opponent personality files,
76 opening books, game databases, endgame tablebases, wallpapers, skins, previews of 56 piece sets, mini-games.

## The boundary: what we take and what we do not (rule 1 of Part II)

* **We take ideas and mechanics** - they are not protected: kinds of exercises, the structure of lessons, opponent character parameters,
  kinds of hints, tournament formats, design principles.
* **We take nothing from the contents**: the name of the program and its engine, the names of modes and mini-games, the names of trainers on
  the study materials, the lesson texts, the comments on games (there are 8,454 in `ClassicGames.pgn`), the collections of puzzles and games,
  the names and biographies of personalities, the voice-over, images, wallpapers, 3D models, icons, its own game database (closed
  format) and the endgame tablebases. Nothing from the program's folder is copied into the repository.
* The moves of historical games are common knowledge; if a game is needed, it is taken from open PGN collections, and
  we write the comments ourselves.

## 1. Modes and overall structure

Three sections of the main menu: **Play** (training with hints and takebacks; rated without hints;
from a given position; tournaments; online; local network), **Learn** (academy courses, openings, database, famous
games) and **Fun** (a children's corner: a simplified interface, animated pieces, weak opponents,
puzzles, mini-games, basics). On first launch a beginner lands in "learning mode" - the rest opens after the
first lesson. When a profile is created, age and experience give the starting rating estimate; for the first 20 rated games the
rating is "provisional" (it changes quickly).

## 2. Opponents (188 personalities)

A personality is 40 numeric parameters. The recognized fields and their ranges across all 188 files:

| Parameter | Range | Median | Ours |
|---|---|---|---|
| Rating | 1–2724 | 1582 | `target_elo` |
| Attack ↔ defense | −100…+100 | 0 | `aggression` |
| Strength, % | 0–100 | 38 | via `target_elo` |
| Randomness | 0–100 | 1 | `randomness` |
| Search depth | 1–14 | 6 | derived from strength |
| **Attitude to draws** | −500…+500 | 0 | **none** |
| Material ↔ position | −100…+100 | 0 | indirectly, via weights |
| Center control (own/opponent's) | 0–200 | 100 | `center_control` |
| Mobility (own/opponent's) | 0–200 | 100 | `mobility` |
| King safety (own/opponent's) | 0–185 | 100 | `king_safety` |
| **Passed pawns (own/opponent's)** | 0–200 | 100 | **none** (inside `pawn_structure`) |
| Pawn weakness (own/opponent's) | 0–200 | 100 | `pawn_structure` |
| Piece values (own/opponent's) | Q 10–150, R 10–90, B/N 10–80, P 5–30 | 90/50/30/30/10 | `piece_values` (own only) |
| Opening book | 76 books | — | the historical bots' books |

Conclusions:

* **There are many weak opponents**: 59 of 188 are below 1200, 50 are 1200–1800, 24 are 1800–2400, 55 are 2400 and up. We have 10
  archetypes (~700–2200): there are too few opponents for beginners.
* "Attitude to draws" (some gladly accept a draw, others never agree) is a noticeable character trait
  that we lack. Separate "own/opponent's" weights differ in only 26 of 188 - the benefit is small.
* Each personality has a biography, and the selection window has a filter by type, age, rating.
* **Opening books as characters**, not only the books of players: a "trapper" (sets opening traps) and a "trap victim"
  (falls into them), early queen development, gambit, drawish, "likes captures", "knights only", "pawns only",
  unconventional, "quickly losing", weak, strong, books of different depth. An opponent who deliberately
  falls into traps is a ready-made exercise for a beginner.
* The actual rating of a character depends on the computing power - for us strength is measured by calibration (task 10.4).

## 3. The mentor and hints during the game

* **Visual trainer** (turned on in training): arrows - all legal moves (blue), captures (red:
  thin - exchange, thick - material gain), defenses (green), pins and reverse pins (red dotted line),
  checks and mates (purple); pieces - isolated and passed pawns shown semi-transparent; squares - safe (green) and
  dangerous (red) for the selected piece, board coverage by both sides; opening moves - circles of different
  fill by popularity. A key switches the hints to the opponent's side - "what will he answer me?".
* **A three-step hint**: the square to go to → which piece → the move itself (for us - task 11.4).
* **"Advice"**: the player sets a thinking time, and the program explains the move aloud.
* **Blunder warning**: a pop-up "Why?" (explanation), "Take back the move", "I disagree"; the sensitivity
  threshold is adjustable.
* **"Find mate"**: the player sets the depth, the program searches for mate and shows the line.
* **Auxiliary board**: during a game you can switch to a copy of the position and play out variations for both sides
  while the opponent thinks.
* **Game summary**: an overall evaluation, the type of game - "domination", "decided by a mistake", "equal" (more than 40% of moves
  equal), "seesaw" (the advantage passed from one side to the other); the opening, rating change, a graph, a **recommended
  next opponent** and a "play him" button.

## 4. Learning

* **Lesson format** - a script synchronized with the board: a position (FEN), pieces appearing, a sliding move, arrows,
  square highlighting, a "ghost" piece (where it could go), pauses, voice-over of every line. A question in a lesson: the correct
  move, a **separate response to each specific wrong move** ("there is a better move" / "this is not what we are looking for") and
  a continuation after the computer's reply ("now play the continuation").
* **Curriculum**: courses for beginners (the board, each piece, a survey of pieces, check and mate, stalemate, castling, en passant,
  promotion, notation, piece values, opening principles, development of each piece, pawn structure,
  passed pawns, pins, forks, discoveries, defense, planning, tournament play) - each lesson has 1-5 control
  "exams"; for intermediate players - "first moves" (what to play as the first, second, third, fourth move for White and for
  Black), five main topics, tactics and position, endgame; for strong players - master games with guessing and
  puzzle problems. A separate children's course with the same content.
* **Generator exercises** (a "type × piece" matrix, levels, time and records): capture an unprotected piece, find
  a fork, find a check, pin a piece, a safe move, avoid mate, mate in 1, mate in 2 - for the queen, rook, bishop, knight
  and a random piece.
* **Technical mates against the computer** with a move limit: with the queen (20), rook (14), two pawns (30), king and
  pawn (30), bishop and knight (20), two bishops (20), queen against knight, rook against knight, queen against rook.
* **Memorizing a position** - three steps: 4-6, 7-12, 13-24 pieces.
* **Diagnostic exam** - 10 tests by section (mate, discovered moves, tactics, mistakes, endgame I and II,
  defense, strategy I-III), the questions are a move on the board or a choice of answer; the result is an "exam rating",
  which does not change the game rating. Separately - an endgame exam of 50 positions.
* **Guess the master's move**: a position from the move into the middlegame, the opening moves are given; the player is offered a **list
  of candidate moves**; points for the exact move, fewer for a close one, a penalty for a bad one; after the game - **additional
  questions**; the result is compared with the masters' level.
* **Courses with a review of the author's own games** - stories from tournaments with a conclusion ("tug-of-war", "more pins",
  "the exchange", "dark squares", "space in front and behind", "the opponent's time"): study material in the form of a story about a
  game. The topics (not the texts) suit our lessons.
* **Openings**: line training (first a demonstration with comments, then a repeat; a hint lowers the "accuracy"),
  an encyclopedia (2,200 lines; when a piece is selected, the squares of its opening moves are marked), an editor of your own opening book.

## 5. Games and database

* **Famous games** (about 830, 1619-2007) with an introduction to each and comments on the moves; keyword
  search.
* **Database** (~800 thousand games): a "who / where / when" search, advanced search, position search, a position tree.
  **Collections by amusing features**: the shortest games, the most checks, the longest series of captures, the most
  peaceful (without captures), the most promotions, "pawn wars" (the most passed pawns), "triumphant draws" -
  stalemate.

## 6. Tournaments and competitions

* **Career**: more than 50 ready-made tournaments of growing difficulty; half are hidden and open for a place in the top three
  of prizewinners. A custom tournament: round-robin or Swiss, rated or not, time control, the rating range of
  opponents in words ("my level", "grandmaster") or in numbers, opponents random or chosen. In a tournament
  you can watch the bots' games against each other or learn only the result.
* **Online** (for our sprint 17): a "ladder" with movement rules (a lower-ranked winner rises by
  half the distance, a higher-ranked one by one position; two games with each opponent with different colors), teams and a
  yearly league with a points table for the result taking rating differences into account, simultaneous exhibition sessions, correspondence
  play, offline messages, friends and an ignore list, a broadcast lesson: the teacher draws arrows in 8 colors, highlights
  squares, places "ghost" pieces, asks multiple-choice questions with a timer, and students vote with a move.

## 7. Time control and game rules

Moves in minutes, seconds per move, all time for the game, Fischer, no limit, an **"hourglass"** (time passes to the
opponent); **separate time** for the sides (a time handicap); a material handicap; **blindfold play** as a game option.
A draw offer only on your own move and no more than once per move; "force to move" a thinking opponent;
adjourn a rated game.

## 8. Design

* **Wallpapers** - tiles with a barely noticeable embossed pattern (hieroglyphs, a Celtic knot, an old map, a manuscript,
  a circuit board, Bauhaus pieces, marble, cracked stone) in two palettes: a deep blue-teal and a light
  parchment. The background does not compete with the board.
* **Piece sets and boards** (56): 2D concepts - "school blackboard" (chalk on green), "newspaper" (a diagram as in a magazine),
  neon, stained glass, "old paper", a strict gray "expert", cartoon, "paints"; materials - glass, metal,
  marble, ceramic, wood of different species; historical replicas - Lewis chessmen (12th c.), Mongolian, Egyptian,
  "sultan", replicas of tournament sets of different eras; mechanical, "modern". Boards - green/cream, blue/white,
  red/cream, purple, turquoise.
* Some sets and skins are **unlocked by wins** in rated games.
* **Sounds** - themed sets matching the piece set; voice announcement of moves; "sliding" pieces (animation of the
  opponent's move) can be turned off.
* Board settings: show moves by highlighting or by an arrow, moving in two clicks instead of dragging, "quick move"
  (a click on a square where only one piece can go), display of captured pieces (by kind / by order / by
  value), a choice of 30 player avatars.

## 9. Chess variants (online)

12 variants: including Marseillais (two moves in a row), progressive (each move one longer), "knight in the
pocket", Kriegspiel (the opponent's pieces are not visible). For us - the "Backlog" (a different engine is needed).

## 10. What follows from this for regence

The comparison with the roadmap and the new tasks are in `ToDo.md` (marked "from the analysis of the reference program"). In short:
much is already planned (the mentor, hints by steps, the ladder, tournaments, puzzles, school, "guess the master's move",
memory and vision trainers, the opening repertoire, design themes); what is new - generator exercises, a game summary
with an opponent recommendation, visual trainer modes, a diagnostic exam, beginner training opponents and book
characters, attitude to draws, a tournament career with unlocking, amusing game collections, a first entry with a level estimate,
the hourglass and time handicap, an auxiliary board, "find mate", board settings, unlockable themes.
