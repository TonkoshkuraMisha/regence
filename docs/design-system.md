# Regence shared design components

Owner decision of 2026-11-18: the pages looked "disjointed and unprofessional" — each one assembled cards, buttons and
headings from its own classes (the primary button was repeated 126 times, the dark panel 120, the card 58). Now the look
is defined by the shared components in `frontend/src/components/ui`, and pages only compose them. The showcase of all
components is the `/design` page (it is not in the menu).

## Components

| Component | When |
|---|---|
| `Page` + `PageHeader` | Every page. Width: `narrow` — reading and lists (school, rules), `default` — pages with panels (puzzles, tournaments), `wide` — a board with panels (game hall, review). |
| `Section` | A page section with a second-level heading and a slot on the right ("All", a counter). |
| `Card`, `CardGrid` | Sections, modes, tournaments, courses. The `hero` variant is the one main card on a page, `muted` is closed or "coming soon". A card with `to` is a link as a whole. |
| `Button`, `ButtonLink` | Actions. `primary` — **one** main action per screen; `secondary` — ordinary ones; `ghost` — secondary ones; `danger` — irreversible ones. |
| `SegmentedControl` | Modes and filters in a single row instead of a scatter of identical buttons. |
| `Badge` | State: `success` — completed, `accent` — current/new, `danger` — closed/error, `neutral` — reference. |
| `ProgressBar` | Progress such as "3 / 10", readable by screen readers. |
| `EmptyState` | An empty list: what will appear here and one action. |
| `Modal` | A window over the page: a heading with an icon; the close button, Esc and a click outside close it. |

## Rules

1. **One primary button per screen.** The rest are `secondary` or `ghost`.
2. **Spacing rhythm:** 16 px between page blocks (`gap-4`), 8 px inside a section (`gap-2`), 12 px inside a card.
3. **Fonts:** page heading `text-2xl`, section heading `text-lg`, card heading plain bold, explanations `text-sm` with
   a muted color. No more than one line of explanation under the page heading.
4. **A grid instead of a long list:** sections and courses use `CardGrid` (1 / 2 / 3 columns), not a column of wide cards.
5. **Colors only through components.** New shades are not introduced on a page; if a new variant is needed, it is added
   to the component and changes everywhere.
6. **Texts come from the catalogs of the two languages (en, uk)**, as everywhere (CLAUDE.md, rule 1).

## Order of migrating the pages (owner's plan of 18.11)

1. Shared components and the showcase — this step.
2. Puzzles (done): before the start — cards of all modes in the groups "Solve / Train / Your own games" with a
   description, the selected one is `hero` with a "Start" button; with a puzzle open — the same groups as
   `SegmentedControl` tabs; the rating chart has labeled axes. Groups and icons — `components/puzzles/puzzleModes.ts`.
3. School and tournaments (done): school — the "Big course" `hero`, courses and trainers — `CardGrid` (the
   `SCHOOL_CARDS` list in `LearnPage.tsx`), a lesson course has a `ProgressBar`; tournaments — `PageHeader`, the
   "Arenas" and "Time machine" cards, "My tournaments" with a `Badge` of place or status and an `EmptyState`.
4. Game hall: on the right, the tabs "Moves / Chat / Coach / X-ray" (done: a coach warning opens its tab by itself, the
   chat shows the unread count); the board grows back together with the window (#191); "New game" is a step-by-step
   window "Opponent → Time → Start" (`chessboard/NewGameDialog.tsx`, on the shared `Modal`), the choice of opponent is
   remembered, the column holds the lobby, the game in progress and the bot opponent.
