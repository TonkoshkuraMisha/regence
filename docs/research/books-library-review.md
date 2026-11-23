# Review of the owner's study library (15.11.2026)

Development working document. The project owner gave a folder, "Books to inspire the learning section", on their own
Google Drive for study: books (PDF, DjVu), game databases and study databases (PGN and the closed format of a commercial game database),
the opening repertoire tree, game collections and the full list of files (`full_tree.txt`). The goal is to understand what from it
can be taken into the platform. Nothing from the folder is copied into the repository: games enter our database through the import script
(task 27.2), and everything else is only ideas and methodology.

What came out of it:

* The list of files was parsed completely: 432 folders, 4,922 files, 1.2 GB.
* PGN - selectively: the opening repertoire, pawn structures, "Beautiful games", games from "How to Become a Master".
  The game records in them are bare - only headers and moves, in places someone else's notes with an engine evaluation (we cut them off).
* PDF - imprint data and introductions. These are modern editions (2014-2017) with the rights of compilers and translators.
* DjVu (16 books) were not read: the development machine has no program for this format. Assessed by their titles.
* Study databases in a closed format (`.cbh`, `.cbv`, `.cib`, about 250 databases) cannot be opened with free tools;
  we parsed their chapter titles - they show the structure of the courses.

## The boundary: what we take and what we do not (rule 5 of Part II)

* **We take ideas and methodology**: kinds of exercises, the order of teaching, the classification of techniques, the design of tests. This is not
  protected. We write the texts ourselves in two languages (en, uk), and take the positions as our own (from our CC0 puzzle database, from the archive, from
  generators) or from games.
* **We take games** - moves and headers (players, place, year, result). These are facts. Comments, evaluations and variations
  from the files are cut off at import; our own comments will appear later (task 27.4).
* **The "Beautiful games" collection was compiled by the owner** - it can be taken whole, including the composition of the collection.
* **We do not take**: texts, comments, diagrams, covers, collections of puzzles and exercises from books (a collection is protected
  as a compiled work, even if every position comes from a game), composed problems and studies by modern
  composers, names of commercial programs and databases (rule 5).
* **Names of living chess players** are not used for bot opponents or in advertising; their games in the library are facts.
* **Personal games** (the "PERSONAL GAMES" folder, ~300 PGN, including a child's games, opponents' names; a photo of someone else's
  game collection) - only in the owner's private collection, without publication.

## What is in the folder

| Section | Contents | How we use it |
|---|---|---|
| `# OPENING REPERTOIRE` | The repertoire tree: for White - 26 chapters after 1.e4 (Scandinavian, Alekhine, Pirc, Caro-Kann, French, Russian, Scotch, Spanish, Sicilian: Maroczy, Chelyabinsk, Paulsen, Dragon, Keres, Rauzer, Najdorf); for Black - 35 chapters (Réti, English, queen's pawn openings, Slav with variations, King's Gambit, knight and bishop openings, Four Knights, Scotch, Two Knights Defense, Spanish with the Breyer). The nodes hold `MAIN LINE.pgn` and sample games; large databases of 2-9 MB (~470 MB of PGN in all, with duplicate files in different chapters) | The skeleton goes into advanced starter repertoires (20.1), the games into the library (27.2). The large databases were compiled by the owner while reading the books (decision of 15.11) - into the library publicly |
| `# PAWN STRUCTURES` | 14 structures with sample games (~120): Spanish (e4 against d6), French chain, e4/e5 symmetry, Exchange French, "saw", Maroczy, isolated pawn, hanging pawns, Carlsbad, stonewall, King's Indian chain, wedge in the center, Modern Benoni, hedgehog | Library (public) + the "Pawn structures" module of the Big Course + the structure detector (27.5) |
| `# GAMES` | "Beautiful games" (138, the owner's collection), Capablanca (125), Kasparov (64), Botvinnik (36), Euwe (33), Ivanchuk (2), "How to Become a Master" (4), personal games (~300 PGN and 5 databases), photos of a game collection (171) | Library: "Beautiful games" and master games - public; personal - private; photos - not used |
| `ALL CHESS CHAMPIONS` | Games of 14 world champions from Steinitz to Kramnik: databases in a closed format and 14 zip archives (8 MB) | Library after conversion to PGN (27.3); the history of the champions in the course; new historical opponents (21.5) - only deceased masters |
| `PGN-BOOKS` | ~120 books in the form of study databases: courses on tactics, strategy, endgames, openings, game collections, World Championship matches | Games of the matches and collections go into the library (moves only, 27.3); courses - the structure for the Big Course |
| `CHESS. CLASSICS` and books in the root | Textbooks by Capablanca, Lasker, Nimzowitsch, Réti, Alekhine, Spassky, Fischer; Bloch, Gubnitsky, Ivashchenko, Levenfish, Nikolaev, Panchenko, Seirawan (4 books), Khmelnitsky, Konotop tests (6 levels) | Methodology only |

## What we take: methodology and formats

### Curricula and levels

* **Levels by rating class.** The Konotop tactics tests are divided into six levels: beginners, Class IV, III, II, I,
  high qualification. For players in Ukraine and the former USSR countries, rating classes are clearer than a rating. We build the levels of the Big
  Course and the level exams (22.0) on this scale, showing a rating guide alongside.
* **A program by years of study** (Chekhov - Arkhipov, Class IV-II; Chekhov - Komlyakov, Class I - Candidate Master). First year:
  getting out of check, mate in 1, 2, 3 moves. Second year: tactical weaknesses of a position, the simplest tactical positions,
  mate in 2-3. The senior stage: restricting the opponent's pieces and pawns, strategic play and planning, calculation
  technique, studies for combinational vision. This is the skeleton of the 22.3 programs.
* **A fine difficulty scale** (Ivashchenko, 11 steps of training in combinations) - within a course level, puzzles go
  by steps, not in one list.
* **An exam with a skill profile** (Khmelnitsky, "Chess Exam"): a test by sections, the result is a profile of strong and
  weak sides and an estimate of the level. A model for 22.0 and the skill map 22.1.
* **A course of 64 lessons** (Gubnitsky, Nikolaev, Rublevsky) - a convenient size for one step of the course.
* **Simple endings first, then the middlegame** (Capablanca): the early course levels begin with the simplest mates
  and pawn endings.
* **Programmed learning** (Fischer): one small step, immediately a question and a check. Suits the "Basics" and
  the 14.1 lessons.

### Classification of tactics: technique × goal

Kalinichenko's intensive tactics course lays tactics out along two axes. This is stronger than our flat list of themes.

* **Direct strikes**: mate in 1, double attack, simultaneous attack, discovered attack (with check), discovered check,
  windmill, double check, line attack, absolute and relative pin, traps in the opening, passed pawn,
  intermediate move and check, counterblow, zugzwang, invasion, unstoppable threat, ambush, x-ray, gaining a tempo.
* **Drawing techniques**: theoretical draw, stalemate, "rampant" piece, perpetual check, perpetual attack, perpetual threat,
  positional draw, fortress, blockade.
* **Methods with a goal**: opening lines (for mate, for attack, for invasion, for a double attack, for a line attack,
  for trapping the queen, for a discovered check), conquering a square (a mating one, for invasion), deflection (to mate, from the invasion square,
  from the promotion square, of a defender, of a pinning and blocking piece, with a double attack), decoy (into
  mate, into a mating net, into a pin, into a double attack, into a line attack, into a discovered check, into stalemate, into perpetual check,
  onto a critical square, to gain a tempo), destroying the defense, blockade (with mate, with promotion, of the king's route,
  preventive, stalemate), clearing a square and a line, interference (with mating threats, for promotion, pin,
  line of defense, preventive, forced).
* **Forcing variations** of the same: forced mate, forced double attack and so on.

Decision: a second attribute is added to a theme in the registry (`src/services/themes.py`) - the **goal of the technique** (`mate`,
`material`, `promotion`, `invasion`, `draw`, `tempo`). There are few new themes (the list is in 27.8); the rest is covered by
the "theme × goal" combination.

### New kinds of exercises

* **"Save the game"** - find a draw in a lost position: stalemate, perpetual check, perpetual attack, fortress, blockade,
  "rampant" piece. We have only some of the themes (`perpetual_check`, `stalemate_trick`, `fortress`, `save_by_*`).
* **"Recognize the structure"** - a quick game: position → name of the pawn structure. The structure is determined from the pawns
  automatically; the same detector tags the archive and the library.
* **"Find the plan"** - a position from a sample game of a structure, a choice of the plan from 3-4 options, the review is the continuation of
  the game.
* **"Candidates"** (Kotov, "Think Like a Grandmaster") - before the move, name 2-3 candidate moves; the review shows whether the
  best move was among them.
* **"Miniatures"** (the idea of collections of short games and the encyclopedia of opening mistakes) - a short decisive game from the
  archive, the task is to find the decisive mistake and the punishment. We compile the collection ourselves.
* **"Must-know positions" of the endgame** (the idea of endgame textbooks) - a list of theoretical positions with a
  "mastered" mark, checked against endgame tablebases.
* **Studies for combinational vision** - only studies by composers who died long ago, with an entry in `ATTRIBUTION.md`.
* **Compare two moves** (the idea of creative-thinking textbooks) - which of two moves is stronger and why; the answer is on
  the board.
* **Class test** - a fixed set of positions, timed, the result is an estimate of the level.

### Positional themes that are not in section L

From the strategy classics (the concepts are common, the explanations are our own): blockade, overprotection, centralization, pawn chain and
attack on its base, restricting the mobility of pieces, advantage of the two bishops, exchange of a "bad" bishop, minority
attack (already there), critical position and choice of plan, prophylaxis (already there).

## What we do not do

1. We do not copy texts, comments, diagrams, collections of puzzles and exercises from books - neither from modern ones nor from
   classical ones: the classics here are in translations and compilations with rights still in force.
2. We do not take composed problems and studies by modern composers.
3. We do not mention in the product the commercial programs and databases from which the files were taken.
4. We do not publish personal games or the photo of someone else's collection.
5. We do not make bot opponents with the names of living chess players.
6. We do not use book covers.
7. We do not open game databases of unknown origin to users. The repertoire databases of this folder were compiled by the owner
   (decision of 15.11) - this does not apply to them.

## Owner decisions (15.11)

* The repertoire databases were compiled by the owner while reading the books - we take them, publicly.
* We convert the study databases of the closed format to PGN ourselves (27.3).
* We write the annotations to the library games ourselves; the owner refines them afterwards (27.4).

## What came out of this in the plan

Sprint 27 in `ToDo.md`: the game library (27.1-27.5), the Big Course (27.6-27.12), new exercises and themes (27.8,
27.9), level exams (together with 22.0). The structure of the course is in `docs/research/supercourse.md`.
