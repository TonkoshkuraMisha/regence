# Navigation benchmark: where things live on other chess sites and on ours

Development working document. Goal: a full inventory of the menus and page layouts of reference chess sites next to
our own, so that the owner can decide what to rearrange or add. **This is not a plan to copy anyone**: we record
structure (which sections exist, how they are grouped, how much room they get), then decide for ourselves.

Sources:

| Site | Material | Status |
|---|---|---|
| Lichess | Owner's screenshot collage, 1919 px wide, signed-in account, 25.11.2026 | Done (sections 1, 4) |
| Chess.com | Same kind of collage, promised by the owner | Pending (section 2) |
| ChessTempo | Same kind of collage, promised by the owner | Pending (section 3) |
| Regence | Local `dev` (`12630b0`), Playwright at 1920×1080, guest and a fresh signed-in player, 26.11.2026 | Done (section 4) |

The boundary is the same as in `reference-program-analysis.md`: ideas, grouping and proportions are not protected;
names of branded modes, texts, icons and art are, and we take none of them.

Sizes below are measured on the screenshots and are approximate (±10 px); percentages are of a 1920 px viewport.

---

## 1. Lichess

### 1.1 Header

One row, about 60 px high. Left: logo + wordmark. Then six section menus that open on hover, plus a highlighted
"Donate" link. Right: search, friends, challenges (crossed swords), notifications, account name.

| Menu | Items (in order) |
|---|---|
| **Play** | Create a game · Arena tournaments · Swiss tournaments · Simultaneous exhibitions |
| **Puzzles** | Puzzles · Puzzle themes · Puzzle dashboard · Puzzle Streak · Puzzle Storm · Puzzle Racer |
| **Learn** | Chess basics · Practice · Coordinates · Study · Coaches |
| **Watch** | Broadcasts · Lichess TV · Current games · Streamers · Video library |
| **Community** | Players · Friends · Teams (clubs) · Forum · Blog |
| **Tools** | Analysis board · Opening explorer · Board editor · Import game · Advanced search |
| *(link)* | Donate |

Every menu has 4–6 items; nothing personal (inbox, settings) is in them.

### 1.2 Account menu (click on the name)

Profile · Inbox · Preferences · Sign out. Below a divider: Language ▸ · Sound ▸ · Theme ▸ · Board ▸ · Piece set ▸
(each a submenu). Footer: ping and server latency with a signal-bar indicator.

Four navigation items in total; appearance lives here as quick submenus instead of a separate page.

### 1.3 Home page (signed in)

Content box ≈ 1750 px centred (≈ 80 px side margins), three columns **≈ 22% / 45% / 22%**:

* **Left (≈ 420 px):** live streamers (2–3 lines, "Streamers »"); tournament cards "playing now / starts in N min"
  (2 cards); a short "free, open source, no ads" blurb.
* **Centre (≈ 865 px):** tabs **Quick pairing · Lobby · Correspondence**.
  * Quick pairing: a 3×4 grid of tiles (≈ 280×165 px each): 1+0, 2+1 bullet; 3+0, 3+2, 5+0, 5+3 blitz;
    10+0, 10+5, 15+10 rapid; 30+0, 30+20 classical; "Custom". One click = start searching.
  * Lobby: a table (player · rating · time · mode rated/casual + variant icon), rows ≈ 45 px, a "— VARIANT —" divider
    between standard and variant seeks, a settings gear and a rating-graph toggle.
  * Correspondence: the same table with days per move; a "Create a game" button under it.
* **Right (≈ 420 px):** three large buttons stacked (≈ 420×67 px): **Create a game · Challenge a friend · Play with
  the computer**. At the bottom: "N players" / "N games in play" counters.
* **Below the fold (second row, same three columns):** Donate card · news timeline (3 items) · merch card; then a
  live mini-board of a top game with both clocks · three blog cards with images · **Puzzle of the day** board
  ("White to play"); then footer links and an "Open tournaments" table (name, time left bar, duration, players).

### 1.4 "Create a game" dialog

Modal ≈ 440 px wide. Variant dropdown (with a one-line description) → tabs Real time / Correspondence / Unlimited →
two sliders (minutes per side, increment) with numeric badges → a 2×5 row of preset chips → Casual / Rated toggle →
"Your rating: N (category)" → rating range filter (−500 / +500 sliders) → one primary button.

### 1.5 Profile

* **Left column (≈ 270 px):** one row per rating category (UltraBullet, Bullet, Blitz, Rapid, Classical,
  Correspondence, then Puzzles, Puzzle Storm/Racer/Streak): icon, rating, recent change arrow, games count, rank.
  Unplayed categories are greyed.
* **Main block:** name + online dot; counters (tournament points, studies, forum posts, blog posts); actions
  (edit profile, watch, opening database, More ▾); **rating history chart** with ranges 1M / 3M / 6M / YTD / 1Y / ALL
  and a range slider; facts (member since, last seen, time played, TV time, clubs); promo links (coach comparison,
  insights).
* **Tabs:** Activity (a day-by-day timeline: "Played N bullet games, rating ±N", win/draw/loss chips) · Games (counters
  all / rated / wins / losses / draws / advanced search; rows with a mini-board, time control, players with rating
  change, result, opening and first moves).

### 1.6 Tournaments

* **Arena list:** left sidebar (my tournaments, calendar, history, FAQ; best players with their trophy; upcoming
  official tournaments with dates) + main area: a **horizontal timeline** (hour columns, a "now" line, coloured bars per
  tournament by speed/category, players count on the bar) and a "Finished" list. "Create tournament" button top right.
* **Swiss list:** "Playing now" and "Starting soon" lists (icon, name, club, rounds, time control, start, players),
  then an explanation, an **Arena vs Swiss comparison table** and a FAQ.

### 1.7 Players

Left submenu (best players, rating distribution, tournament winners, shields, online bots, FIDE players). Main: an
"Online now" column and a grid of **leader cards per category** (3 per row, 10 names each).

---

## 2. Chess.com

*Pending: the owner's screenshot collage. Fill in sections 2.1–2.7 in the same shape as section 1.*

## 3. ChessTempo

*Pending: the owner's screenshot collage. Fill in sections 3.1–3.7 in the same shape as section 1.*

---

## 4. Regence (current `dev`)

### 4.1 Header

52 px. Logo + wordmark, then flat links (no submenus): **Play · Puzzles · School · Tournaments · Trainers ·
Leaderboard · Chess legends ▾** (the only dropdown: 20+ champions with photos, then "Masters of the past").
Right: language switcher · search · notifications · "About" (scales icon) · report a problem (bug icon) ·
settings (guests only) · account / Log in.

### 4.2 Account menu

Header card (avatar, rating, online) then **17 items**: Profile · Puzzles · My games from other sites (import) ·
School · Watch · Tools · Teams · Feed · Messages · Shared analysis (study) · Tournaments · Leaderboard · Settings ·
Report a problem · Log out · Log out on all devices (+ Moderation for moderators). Footer: ping / server.

Four of them (Puzzles, School, Tournaments, Leaderboard) duplicate the header; **Watch, Tools, Teams, Feed,
Messages, Study, Import are reachable only from here.**

### 4.3 Pages reachable only from inside other pages

| Page | Route | Linked from |
|---|---|---|
| Arenas | `/arenas` | Tournaments page card |
| Conferences | `/conferences` | Arena pages |
| Time machine | `/time-machine` | Tournaments page card, masters |
| Game library | `/library` | Watch page |
| Daily workout | `/workout` | Trainers page |
| Training programmes | `/programs` | Trainers page |
| Diagnostic exam | `/exam` | Trainers page, skill map |
| Opening repertoire | `/repertoire` | Trainers page, workout |
| Chess960 | `/play/960` | Trainers page, game viewer |
| Coaches' games | `/train/games` | Trainers page |
| Guess the move | `/guess` | School page, game viewer |
| Community rules | `/rules` | Sign-up dialog |
| Transparency | `/transparency` | About page |

### 4.4 Section pages (what is inside)

| Section | Contents |
|---|---|
| Puzzles | Solve: by rating · of the day · timed (3 or 5 min, three mistakes). Train: themes · drills · defence · save the game. Your games: my mistakes. Side card: puzzle rating, solved, streak, theme filter |
| School | The big course · Chess basics · Mating patterns · Endgame trainer · Master games explained · Guess the master's move · Opening explorer · lesson lists by topic |
| Trainers | Daily workout · Programmes · Diagnostic exam · Repertoire · Chess960 · Coaches' games · board-vision mini-trainers |
| Tournaments | Arenas card · Time machine card · My tournaments · Legends of the week · New tournament form (format, size, time, 40+ opponents as chips) |
| Watch | Game of the day · Game library · tabs Live / Master archive / Collections |
| Tools | Board and explorer · Position editor · Import FEN / PGN · find mate |
| Leaderboard | One table, tabs Bullet / Blitz / Rapid / Classical |

### 4.5 Home page

* **Guest:** an empty page with one card "Login required — please log in at the top right". No lobby, no board, no
  way to try anything.
* **Signed in:** the game hall. Three columns **≈ 23% / 45% / 22%** (435 / 860 / 414 px) — practically the same
  proportions as Lichess:
  * Left: hall header (session score, sound, flip) · **New game** button (opens a 3-step wizard: Opponent → Time →
    Start) · current tournament strip · tabs Lobby challenges / Playing now. With an empty lobby the column is a
    message in the middle of ~800 px of empty space.
  * Centre: the board (≈ 836 px square) with player bars and clocks.
  * Right: move list with tabs Moves / Coach / X-ray, blindfold setting, piece-set picker, navigation, FEN field,
    undo / reset.
  * Nothing below the fold.

### 4.6 Profile (fresh player)

Left column ≈ 345 px with avatar, name, member since (mostly empty). Main: **Achievements grid first** (≈ 760 px of
height), then posts, then rating tiles (4 categories) and games / win rate / W-D-L.

---

## 5. Cross-map

How each function is reached. "Header" = one click from any page; "Account" = in the account menu; "Inside" = only via
another page; "—" = not found in the code.

| Function | Lichess | Regence | Note |
|---|---|---|---|
| Quick pairing by time control | Home centre, 1 click | Wizard, 3 steps | |
| Lobby of open challenges | Home centre tab | Hall left column tab | |
| Play the computer | Home right button | Wizard step 1 | our bots are a key feature |
| Challenge a friend | Home right button | Wizard (person → link) | |
| Correspondence | Home tab | — | |
| Arenas | Play ▸ | Inside (Tournaments) | |
| Swiss | Play ▸ | Inside (Tournaments form) | |
| Simuls | Play ▸ | — | |
| Historical-field tournaments | — | Inside (Time machine) | ours only |
| Puzzles by rating | Puzzles ▸ | Header → Puzzles | |
| Puzzle themes | Puzzles ▸ | Puzzles page | |
| Puzzle of the day | Home, below fold | Puzzles page | not on our home |
| Timed puzzles | Puzzles ▸ Storm | Puzzles page "Timed" | |
| Puzzle streak / racer | Puzzles ▸ | — (streak counter only) | |
| Puzzle dashboard | Puzzles ▸ | Side card (rating, solved, streak) | |
| Basics / lessons | Learn ▸ | Header → School | |
| Coordinates | Learn ▸ | Trainers (board vision) | |
| Study (shared analysis) | Learn ▸ | Account | |
| Coaches directory | Learn ▸ | — | |
| Courses / programmes / exam / workout | — | Inside (Trainers) | ours only |
| Live games | Watch ▸ | Account → Watch | |
| TV / featured game | Watch ▸ + home mini-board | Watch "Game of the day" | not on our home |
| Broadcasts / streamers / videos | Watch ▸ | — | |
| Master archive / library | Tools ▸ explorer (masters db) | Inside (Watch) + Legends ▾ | ours richer |
| Players / leaders | Community ▸ | Header → Leaderboard (one category at a time) | |
| Online now | Community ▸ Players | — | |
| Friends | Community ▸ + header icon | Search + profile follow | |
| Teams / clubs | Community ▸ | Account | |
| Forum / blog | Community ▸ | Account → Feed | |
| Messages | Account | Account | |
| Analysis board | Tools ▸ | Account → Tools | |
| Opening explorer | Tools ▸ | Tools, School | |
| Board editor | Tools ▸ | Tools "Position editor" | |
| Import game | Tools ▸ | Account + Tools | |
| Advanced game search | Tools ▸ + profile | — | |
| Settings | Account | Account / header (guest) | |
| Appearance quick switch | Account submenus | Settings page + board picker | |
| Online players / games counters | Home right | — | |
| Report a problem | Footer | Header + account | |

---

## 6. Observations (for discussion, not decisions)

1. **Grouping.** Lichess: six menus of 4–6 items each, account menu of 4. Ours: seven flat links + one dropdown,
   account menu of 17, and 13 pages reachable only from inside other pages. Several of our strongest features
   (bots, time machine, programmes, repertoire, library) are two or three clicks deep.
2. **Guest home.** Lichess lets a visitor see the lobby and start playing; ours shows an empty "Login required" card.
3. **Time to first move.** Lichess: one click on a tile. Ours: New game → Opponent → Time → Start.
4. **Proportions are already fine** (≈ 23 / 45 / 22 vs ≈ 22 / 45 / 22). The difference is content: Lichess fills the
   side columns with actions and live signals; our left column is mostly empty when the lobby is empty, and nothing is
   below the fold.
5. **Profile order.** Lichess: ratings and their history first, activity second. Ours: achievements first, ratings at
   the bottom of the first screen.
6. **Tournaments page.** Lichess shows what is running and what starts soon, creation is a button. Ours is dominated by
   the creation form (40+ opponent chips, each with a repeated "(meas.)" label).
7. **Things only we have** and that deserve a visible place: historical bots and legends, time machine, the big course,
   programmes / workout / exam, repertoire, game library, coach and X-ray on the board.

## 7. Open questions for the owner

1. May a guest play a bot (or solve a puzzle) without an account? (Decides what the guest home can offer.)
2. Header model: grouped dropdowns like Lichess, or keep flat links and only move items out of the account menu?
3. Is the game hall (board in the centre) the home page, or should the home page be a hub and the board open on demand?
4. Which of the missing functions are wanted at all: correspondence, simuls, streak/racer-style modes, online counters,
   advanced game search, coaches directory, broadcasts?

Revisit sections 5–7 once Chess.com and ChessTempo are added.
