# Strength profile of the historical bots by game phase

Script: `scripts/measure_bot_phases.py` (bot against itself, Stockfish depth-10 evaluator; 3 games per bot, losses capped at 1000 cp).
Table cell: average loss in centipawns / share of moves with a loss >200 cp / share of moves with a loss >100 cp.
Full table: `bot_phase_profile_table.md`.

## Findings
- The profile is **uneven**: from move 21 on, the average loss for most bots is 50-75 cp, blunders >200 cp are 5-9% of moves, mistakes >100 cp are 15-22%; in the book and the first moves it is 6-30 cp.
- Even exceptions: `lasker` (10/33/37), `tal` (8/14/30) - their losses are small in every phase.
- The growth of losses after the book is a consequence of Stockfish move selection at UCI_Elo without an error model by rating and phase.
- The sample is small (3 games), so the figures are indicative; acceptance requires a run of at least 50 games per bot.

Conclusion for the regence-engine own engine: the error model must be uniform across the whole game (task M11).
