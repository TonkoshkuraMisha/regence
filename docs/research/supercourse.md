# The Big Course: a single study program (design, 15.11.2026)

Development working document. All the study programs from the owner's library (overview:
`docs/research/books-library-review.md`) are merged into one program and built into what the platform already has.
The course is a **skeleton**: levels, branches, modules and empty cells. The cells are filled gradually - with puzzles, positions,
questions, games from the library (27.1), lessons in the 14.1 format. The texts are our own, in three languages; from the books we took
only the topics, the order and the kinds of exercises.

The working title is "The Big Course", at `/learn/course`. It does not replace the existing sections but links them into
one path: a course module can simply lead to the basics, to the mates course, to the endgame trainer, to the vision trainer, to a
path through a puzzle theme or to the repertoire.

## Structure

* **Level** - 6 steps by rating class (the rating guide is approximate and is shown alongside):

  | Level | For whom | Guide |
  |---|---|---|
  | 0. Basics | just learned the rules | — |
  | 1. Beginner | no class → Class IV | up to ~1000 |
  | 2. Class IV–III | | ~1000–1400 |
  | 3. Class III–II | | ~1400–1700 |
  | 4. Class II–I | | ~1700–2000 |
  | 5. Class I – Candidate Master (CM) | | ~2000–2200 |

* **Branch** - a direction within a level: **T** tactics, **M** mate and attack on the king, **E** endgame,
  **S** strategy and pawn structures, **O** opening, **C** calculation, vision and thinking, **G** games and history.
* **Module** - a branch topic at a level (for example, "T2.4 Deflection"). The module code is immutable: `<branch><level>.<number>`.
* **Step (cell)** - the unit of filling. Kinds:
  * `lesson` - a lesson in the 14.1 format (an explanation on our own positions);
  * `demo` - a demonstration of the solution (`/puzzles/demo`);
  * `puzzles` - N puzzles by theme × goal × step (13.4), including from your own games (13.5);
  * `drill` - a 13.7 generator exercise (kind × piece × level);
  * `trainer` - a 16.5/19.x trainer with a level;
  * `endgame` - a position of the 14.4 endgame trainer;
  * `game` - a game from the library (27.1) with "what would you play?" stops (as in 14.7);
  * `guess` - "Guess the master's move" on a game (14.3);
  * `question` - a multiple-choice question (plan, evaluation, structure, "which move is stronger");
  * `play` - a game against an opponent from a given position or a trainer game (19.8);
  * `test` - a timed check of the module.
* A cell has a status: `empty` (only a place in the skeleton), `draft`, `ready`. Empty cells are not shown to the player;
  a module is visible when it has at least a lesson and puzzles.
* **Level exam** - the "class test" (22.0): a fixed set of positions across all branches, timed, the result is
  a profile by branch (skill map 22.1) and the decision "level passed".
* **Programs by year** (22.3) are routes through the course: which modules to take and in what order, week by week.

## What already exists and where it fits

| Existing section | Place in the course |
|---|---|
| Basics `/learn/basics` (14.5, 8 sections, 52 levels) | Level 0, branches T/G entirely |
| Mates course `/learn/mates` (14.6, 20 patterns) | M1–M3: simple patterns at 1–2, the rest at 3 |
| Endgame trainer `/learn/endgames` (14.4, 25 positions) | E0–E3 by difficulty: mates - 0–1, pawns and the square - 1–2, Lucena/Philidor - 3 |
| Courses "Tactics", "Attack on the king", "Endgame: converting" (14.2) | T1–T2, M2, E2 |
| Master games with explanations `/learn/classics` (14.7, 30 games) | Branch G, levels 2–5 |
| Puzzle themes A–L (13.0–13.4), puzzles from your own games (13.5), defense (13.6) | `puzzles` steps in all T, M, E, S modules |
| Generator exercises (13.7) | T0–T1 |
| Vision, memory, counting, blindfold trainers (16.5, 19.1–19.7) | Branch C, all levels |
| Trainer games (19.8) | Levels 0–1: pawn battle, king and pawns, capture the flag |
| Repertoire and starter sets (20.1–20.3) | Branch O, levels 2–5 |
| "Guess the master's move" (14.3) | Branch G, levels 2–5 |

## Program

Below are the modules by level. In parentheses are the existing sections the module uses. The topics are merged from all the courses
of the library; repetitions are combined.

### Level 0. Basics
* T0/G0. The board and pieces, moves, capture (basics 14.5).
* T0.1. Check and defense against check: moving away, blocking, capturing.
* M0.1. Mate and stalemate: telling them apart; mate in 1 move ("mate in 1" generator).
* E0.1. The simplest mates: with the queen, with the rook (endgame 14.4); the king helps.
* T0.2. The value of pieces and a favorable exchange; capturing an unprotected piece (generator).
* O0.1. How to begin a game: center, development, castling, not moving the queen early.
* G0.1. Trainer games: pawn battle, king and pawns, capture the flag (19.8).
* Level 0 exam.

### Level 1. Beginner
* T1.1. Double attack (forks by all pieces). T1.2. Pin (absolute and relative). T1.3. Discovered attack and
  discovered check. T1.4. Skewer. T1.5. Defense against threats: "what is threatened?" (13.6).
* M1.1. Mate in 1–2 moves: mixed sets. M1.2. Back-rank mate, smothered mate (mates course).
  M1.3. Attack on f7/f2.
* E1.1. King and pawn against king: the rule of the square, key squares, opposition (14.4).
  E1.2. Queen against pawn. E1.3. Converting an extra piece: exchanges, active king.
* O1.1. Opening principles by example. O1.2. Traps and early mistakes (section H). O1.3. First moves for White and for
  Black (starter sets 20.1 for beginners).
* C1.1. Coordinates, seeing the board (19.2, 16.5). C1.2. Checks, captures, threats (19.7). C1.3. How many moves to a square.
* G1.1. Miniatures: short games with punishment for a mistake (27.9).
* Level 1 exam ("Class IV test").

### Level 2. Class IV–III
* T2.1. Double check and windmill. T2.2. Intermezzo and intermediate check. T2.3. X-ray and ambush.
  T2.4. Deflection. T2.5. Decoy. T2.6. Destroying the defender, overload. T2.7. Counterblow and unstoppable threat.
  T2.8. Gaining a tempo, invasion. T2.9. Trapping a piece, domination. T2.10. Passed pawn: breakthrough, promotion,
  underpromotion.
* M2.1. Mating patterns: Anastasia, Arabian, Boden, two-bishop mate, epaulette and others (mates course). M2.2. Mate in 3.
  M2.3. Attack on an uncastled king.
* E2.1. Pawn endings: triangulation, outflanking, shouldering, breakthrough. E2.2. Rook endings: Lucena, Philidor,
  rook behind the passed pawn. E2.3. The "wrong" bishop, rook's pawn. E2.4. "Must-know positions" I (27.9).
* S2.1. Open file, seventh rank. S2.2. Outpost. S2.3. Good and bad bishop. S2.4. Weak squares and
  pawns: isolated, doubled, backward. S2.5. Center: open, closed, mobile.
* O2.1. Open games: Italian, Spanish, Scotch (repertoire). O2.2. Your first repertoire (20.1–20.2).
* C2.1. Calculating 2–3 moves blindfold (19.6). C2.2. Who wins the exchange (19.7). C2.3. Candidate moves (27.9).
* G2.1. Master games with stops (14.7). G2.2. "Guess the master's move" (14.3). G2.3. Beautiful games (library).
* Level 2 exam ("Class III test").

### Level 3. Class III–II
* T3.1. Opening lines (for mate, invasion, double attack). T3.2. Conquering a square. T3.3. Clearing a square and a line.
  T3.4. Interference. T3.5. Blockade. T3.6. Quiet move. T3.7. Combining techniques: two- and three-move combinations.
* T3.8. **Save the game**: stalemate, perpetual check, perpetual attack, perpetual threat, "rampant" piece, fortress, blockade,
  positional draw (27.9).
* M3.1. Sacrifices on h7/h2 ("Greek gift"), double bishop sacrifice. M3.2. Pawn attack, bringing in the rook.
  M3.3. Attack with opposite-side castling. M3.4. Sacrifice for the initiative.
* E3.1. Bishop against knight. E3.2. Opposite-colored bishops. E3.3. Queen endings. E3.4. Practical rook endings:
  activity of the rook and king. E3.5. "Must-know positions" II.
* S3.1–S3.7. **Pawn structures I**: Spanish (e4 against d6), French chain, symmetry in the center,
  Exchange French, "saw", Maroczy, isolated pawn - the plan for both sides, 3–5 sample games from the
  library, "Find the plan", "Recognize the structure" (27.9).
* S3.8. Positional elements: blockade, overprotection, centralization, pawn chain and attack on its base (27.8).
* S3.9. Minority attack, advantage of the two bishops.
* O3.1. Closed games: Queen's Gambit, Slav, Indian defenses. O3.2. Sicilian: typical ideas.
  O3.3. Broadening the repertoire, the opponent's deviations (20.3).
* C3.1. Candidate moves and the tree of variations. C3.2. Calculating forcing lines (checks, captures, threats).
  C3.3. Visualizing long lines (19.6).
* G3.1. Champions' games: history from Steinitz (library + historical opponents 21.5).
* Level 3 exam ("Class II test").

### Level 4. Class II–I
* T4.1. Forcing combinations: mate, double attack, line attack with preparation. T4.2. Combinations with promotion.
  T4.3. Defense in difficult positions (13.6, hard level).
* M4.1. Attack on a king in the center. M4.2. Attack with same-side castling. M4.3. Defense: counterattack, exchange of
  attacking pieces.
* E4.1. Endgame strategy: active king, weaknesses, the principle of two weaknesses. E4.2. Transition into a won endgame.
  E4.3. Rook against a minor piece, queen against rook. E4.4. Studies for combinational vision (only early
  composers).
* S4.1–S4.7. **Pawn structures II**: hanging pawns, Carlsbad, stonewall, King's Indian chain,
  wedge in the center, Modern Benoni, hedgehog.
* S4.8. Restricting the opponent's pieces and pawns. S4.9. Improving the worst piece, prophylaxis.
  S4.10. Strategic techniques: exchanging a key piece, transferring a piece, seizing a file, opening the position.
  S4.11. Planning: evaluating the position → goal → plan.
* O4.1. Opening and middlegame: a plan from the opening's pawn structure. O4.2. Advanced starter repertoires
  (a skeleton from the owner's library, 27.10).
* C4.1. Calculation technique: calculate to a quiet position, evaluate. C4.2. "Compare two moves".
* G4.1. World Championship matches: key games (library). G4.2. Working on your own mistakes (13.5 + review).
* Level 4 exam ("Class I test").

### Level 5. Class I – Candidate Master (CM)
* T5.1. Complex combinations, a combination of several ideas. T5.2. Hidden defensive resources.
* M5.1. Attack with a long-term sacrifice of material for the initiative.
* E5.1. Complex rook endings. E5.2. Conversion technique of masters (games from the library).
  E5.3. "Must-know positions" III.
* S5.1. Critical positions: static and dynamic factors, choosing a plan. S5.2. Dynamics and initiative.
  S5.3. Intuition and evaluation of sacrifices. S5.4. Positional sacrifice.
* O5.1. Opening preparation for an opponent. O5.2. New ideas in your own repertoire.
* C5.1. Creative thinking: finding the opponent's idea, prophylaxis. C5.2. Calculation in time trouble (19.7 timed).
* G5.1. Lectures on champions' games (our own texts on library games). G5.2. Self-analysis of played games.
* Level 5 exam ("Candidate Master test").

## How to fill it

* Filling goes cell by cell; each cell has a source of positions (our CC0 puzzle database, a generator, an archive,
  the library, your own position), a text author, a status. For a library game, the cell stores a link to the game and
  the move numbers with stops.
* Checks are as for 14.1 lessons: legality, solvability, uniqueness of the answer where there is only one; texts are in three
  catalogs with identical keys; the moves mentioned in the text are checked against the game (as in 14.7).
* Order of filling: levels 0–2 (beginners are waiting for them), then pawn structures (they already have games), then
  the rest.
