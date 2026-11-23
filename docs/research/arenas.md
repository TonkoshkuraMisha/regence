# Arenas between players: fair rules, schedule, time controls, groups

A proposal for the owner (17.11). **Owner decisions (17.11): everything as recommended** - "last start" and results after the
last game; groups by strength (open + rating groups + divisions), not by geography; rules: no-show = loss,
early draw gives no points, berserk, lag quota; a compact schedule at launch. The foundation already exists (task 17.2): scheduled arenas, waiting and pairs in Redis, points
2/1/0, "fire" after two wins in a row, Swiss rapid 10+5. Below is what to take from other platforms, which of their shortcomings
to remove and how to arrange it for us. The numbers are starting settings: they are all in one place in the code and can be changed without migrations.

## 0. State as of 17.11.2026

This proposal was accepted by the owner and implemented in sprint 33; below it is kept as a record of the idea and the decisions.
The rules in force are written in the code - at the top of the modules named in the table.

| Plan step | Task | Where in the code | Pull request |
|---|---|---|---|
| Fair ending: last start, results after the last game, no-show, early draw | 33.1 | `src/services/arena.py` | #158 |
| Divisions on overflow (the games-played admission requirement and rating groups were cancelled - see below) | 33.2 | `src/services/arena.py` (`check_entry`, `join`) | #159 |
| Berserk and lag quota | 33.3 | `arena.py` (`berserk`), `src/services/game_state.py` (`lag_credit_ms`) | #160 |
| Schedule by conference, reminders, lobby announcement | 33.4 | `src/services/arena_schedule.py`, `arena.py` (`send_reminders`) | #161 |
| Conferences: country, arena standings, Cup of the month | 33.6 | `src/services/conferences.py` | #162 |
| Arena awards | 33.5 | not done | — |

Differences from the text below, approved by the owner on 17.11: "no more than two arenas at the same time" applies within one
conference; Swiss events belong to each conference (10+5 daily at 15:00, 15+10 on Sundays at 11:00 in its
time); the home zone of the Eastern conference is Delhi; berserk gives no bonus for a win by no-show, and on "fire" the bonus
is added after doubling. Conference matches ("later" in §9) are not done.

**Owner decision of 17.11.2026 - no division of players by strength whatsoever.** The "10 rated games" threshold and arenas with a
rating ceiling (up to 1300 / 1700 / 2100) from §5 were cancelled and removed from the code: any registered player
may enter any arena, and the only condition is fair play. Everything said in §5-§6 below about rating groups and
admission by number of games remains as a history of the discussion and is no longer in force.

## 1. How others do it and what is wrong with that

| Platform | End of the arena | Problem |
|---|---|---|
| chess.com (Arena) | by timer; games in progress are aborted / not counted | the player loses a game already half played; the last minutes are a lottery |
| lichess (Arena) | new pairings stop at the moment of the end; games in progress are finished but **do not count in the table** | the game was played fairly, yet its result is lost; it pays not to start a game near the end |
| lichess (Swiss) | rounds, results after the last round | fair, but long and requires showing up for every round |
| chess.com / lichess | huge open "everyone against everyone" arenas | a 900-rated beginner gets 1800-rated opponents at the top of the table all evening |

What is good about them and worth taking: instant pairing without waiting for a round (arena), points for a streak ("fire", lichess),
"berserk" - half the time for an extra point (lichess), tournaments by rating groups (chess.com), announcements and a
countdown to the start, admission by number of games played (against "sandboxes" and new accounts).

## 2. The main fairness rule: "last start" and the result after the last game

An arena has two moments, both visible to the player from the first minute:

* **Last start** - new pairs are created up to it. It is computed from the time control: `end − game duration`, where
  game duration = `2 × (base + 40 × increment)` (the time both players spend on 40 moves). For 3+2 that is 8 min
  40 s: an arena "until 20:00" gives the last pairs at 19:51.
* **Results** - when the last game started before the last start has ended. Every game played counts in the
  table: both for first place and for the one who started at 19:50:59.

Why this and not "pairs until the very end, results when everyone has finished": then a game started at 19:59:59 holds the whole arena
for another 10 minutes, and the finishing time is unpredictable. With a "last start" almost all games finish by the announced
end, and a rare long one (many moves with increment) just delays the results a little - and is still counted.

Additionally:

* **Equal chances at the end.** The player sees "until last start: 4:12". Whoever finishes a game after the last start
  no longer plays - but loses nothing: their points are already in the table.
* **No-show.** Not making the first move within 20 s (bullet) / 30 s (otherwise) is a loss without points for the absent player, the opponent
  gets the points for a win and immediately goes back to the queue; the absent player is removed from waiting until pressing "Play" again.
* **An early draw brings no points.** A draw by agreement before move 10 gives 0 points to both (agreed draws do not feed the
  table); a draw by the rules (stalemate, threefold repetition after move 10, insufficient material) counts as usual.
* **Disconnection.** If the connection is lost, the clock runs as in an ordinary game; if you return, you play on. If you leave the arena, the game
  is played out (or lost on time), no new pairs are created, and the place in the table is kept.
* **Lag.** The server counts time from the moment a move is received and subtracts the measured delay within a quota (as at
  lichess): no more than 300 ms per move and no more than 2 s per game. For bullet this matters more than any geography.
* **Tiebreakers when points are equal:** rating performance in the arena, then fewer games played
  (whoever scored the same points faster ranks higher), then whoever reached the final score earlier.

## 3. Points

* Win 2, draw 1, loss 0 (as now).
* "Fire": after two wins in a row each next win is 4 and a draw is 2; the streak is broken by a draw or a loss (as now).
* "Berserk" (new, optional for the player before the first move): half of the base time for yourself and no increment; a win
  brings +1 point. Not available in the 1+0 pool (there it is a lottery).
* The opponent is not repeated twice in a row; pairs are by closeness of points, then rating; with every 10 s of waiting the permitted difference
  grows, so that nobody waits longer than ~20 s.

## 4. Time controls and duration

The rule: an arena must fit **8-12 games** for an ordinary player, otherwise the table is decided by chance.
Game duration `2 × (base + 40 × increment)`:

| Time control | Game ≈ | Arena duration | Games per player | Comment |
|---|---|---|---|---|
| Bullet 1+0 | 2 min | 30 min | 10-12 | only for bullet fans; no "berserk" |
| Bullet 2+1 | 5 min | 45 min | 7-9 | fairer than 1+0 thanks to the increment |
| Blitz 3+2 | 9 min | 60 min | 6-7 | the main control: the increment removes the "flag" at 1 second |
| Blitz 5+3 | 14 min | 90 min | 6 | the evening "main tournament" |
| Rapid 10+5 | 27 min | — | — | **Swiss only**: 5-7 rounds, results after the last round |
| Rapid 15+10 | 43 min | — | — | once a week, Swiss of 5 rounds |

We set an increment everywhere except 1+0: it makes the ending fair (nobody loses on the flag with an extra piece) and hardly
lengthens the arena.

## 5. How many participants and how to group them

**An arena needs no "overall" ceiling:** pairs are created among those waiting, and 30 and 3,000 participants play equally
fast. But in one big open arena weak and strong players meet more often than we would like. So we group
**by strength, not by geography**:

* **Open arena** - for everyone (as now).
* **Arenas by rating group in the control**: up to 1300, up to 1700, up to 2100 - for the mass of players this is the main format
  (at chess.com they are more popular than open ones). The rating is fixed on entry; for the week before the arena - not above the ceiling
  (against "dropping" the rating for prizes).
* **Divisions on overflow**: if the arena has more than 500 active players, the next entrants go into a second division of the same
  arena (its own table, the same time and rules), by rating on entry.

**Why not by country, IP or continent:**

* fairness does not grow from it - strong and weak players are everywhere; lag is cured by a quota (item 2), not by borders;
* IP is unreliable (VPN, mobile networks) and it is extra personal data;
* with our audience, splitting by region would leave 5-10 people in an arena - pairs would wait for minutes.

**Where geography is still needed:** only in the **schedule time**. We have one server (Europe); the main arenas
are set for the evening in Europe/Ukraine (18:00-22:00 Kyiv time), the rest round the clock but less often. If noticeable
audiences appear in America/Asia, we will add "evening" arenas for their time zone, not separate pools. A separate server in a region
makes sense only with a large growth of bullet - and then it is a decision about latency, not about tournaments.

**Admission:** at least 10 rated games in this control (against new accounts and "sandboxes"), no cheating
flag, with a confirmed email for arenas with prizes/titles.

## 6. Schedule at launch and growth

While there are few players, the main danger is **splitting them** across five simultaneous arenas. So:

* **Launch (few players):** every hour a blitz 3+2 (60 min); in an hour a bullet 2+1 (45 min); at 20:00 Kyiv time an
  "evening" 5+3 (90 min); once a week a Swiss 15+10 (5 rounds) and once a day a Swiss 10+5 (5 rounds).
  No more than two arenas run at the same time.
* **Growth:** when the average arena stably has more than 40 participants, we add rating groups (up to 1300 / up to 1700 /
  up to 2100) at the same hours; at 500+, divisions.
* **The schedule is corrected from data:** we save the number of participants and games of each arena; once a week we look
  at which slots stand empty.

Announcements: 5 minutes before the start, a notification to those who pressed "remind me"; in the lobby, the nearest arena with a countdown.

## 7. Awards and motivation

* The arena top three get a podium celebration (already there: cup, wreath, confetti, fanfare) and an entry in the profile.
* Titles for streaks: "arena winner", "ten arenas in the top three".
* A monthly table by the sum of arena points in a control (league), without influence on the rating.

## 8. Implementation plan

1. **Fair ending (the main thing):** "last start" by control, results after the last game, arena status
   `closing` ("waiting for the last games"), timers in the interface, no-show, early draw without points, order on equal points.
2. **Admission and groups:** admission by number of games and flag; arenas by rating group; divisions on overflow.
3. **Berserk and lag quota** (the quota is common to all PvP games and is useful outside arenas too).
4. **New schedule and announcements:** controls and durations from item 4, reminders, the nearest arena in the lobby.
5. **Awards:** celebration for the top three, titles, monthly arena league.

Each step is a separate PR with tests; step 1 can be started right after the rules are approved.

## 9. Conferences (owner decision, 17.11)

Five world conferences named after the compass directions from Ukraine; every country in the world is in exactly one. This is a **team
competition on top of the common pool**: pairs in arenas are still by strength from all over the world, but each player's point also goes into
the standings of their conference.

* **Central:** Ukraine, Poland, Moldova, Romania, Slovakia, Czechia, Hungary, Lithuania, Latvia, Estonia, Georgia,
  Armenia, Azerbaijan.
* **Western:** France, Spain, Portugal, Benelux, Switzerland, Austria; all of North and South America.
* **Northern:** Germany, United Kingdom, Ireland, Denmark, Norway, Sweden, Finland, Iceland.
* **Southern:** Italy, Greece, the Balkans, Bulgaria, Turkey, Cyprus, the Middle East, all of Africa.
* **Eastern:** Russia, Belarus, Central Asia, India and South Asia, China, Japan, Korea, Southeast Asia,
  Australia and Oceania.

The remaining countries (small European states and so on) go by the nearest neighbor; the full table of ISO codes is in the code.

* **Membership** - the country in the profile (by IP it is only suggested); it can be changed no more than once per season (against switching to
  the winning team). No country means no conference (the player plays but brings no conference points).
* **Standings:** every arena has a conference table (the sum of points of the conference's best N players, so that a larger audience does not
  win by numbers: N = 10 at the start); a monthly Conference Cup by the sum of arena standings; conference matches
  (team against team, boards by strength).
* **Conference matches (scheme approved by the owner on 18.11):** once a week (Saturday) a match of two conferences in a round-robin
  system (10 pairs - a cycle in 10 weeks); sign-up is open to any player of the two conferences; an hour before the start, those signed up on each
  side line up by rating, board 1 against board 1, the number of boards by the smaller side; on a board two games (with white and
  with black), 5+3, rated; win 1, draw ½, the score is the sum over boards; an evening convenient for both, otherwise the host's evening,
  and the host alternates; the table of the season's matches is on the conferences page.
* **Schedule by conference (owner decision, 17.11):** each conference has a "home" time zone (Central -
  Kyiv, Western - New York, Northern - Berlin/London, Southern - Istanbul, Eastern - Delhi/Beijing); in its evening arenas
  run more often, at night less often. Arenas are open to everyone: if there are few people in their own time zone, a player goes to an arena of another conference,
  and their points still count toward their own.
