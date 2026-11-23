# Library game annotations - design (task 27.4)

Development working document: data model, API, editor and order of work, so that comments on library games
(27.1) can be added without reworking what has already been built.

**State as of 17.11.2026.** Stages 1, 2 and 4 are done: the `library_annotations` table (migration `5c657e5a912e`,
statuses `auto / draft / review / approved`), the annotation in the `GET /library/games/{id}` response (`auto` and `approved` are visible
to everyone, drafts to moderators), the "Mentor comments" panel in the library game viewer
(`frontend/src/components/library/LibraryAnnotationPanel.tsx`) and mentor drafts via the offline script
`scripts/annotate_library.py`. Not done: the editor and version history (stage 3), own texts in two languages (en, uk) on top of the
mentor comments, import of comments from the owner's PGN (stage 5). The questions to the owner at the end of the document
remain open.

Owner decision (15.11): we (development) write the comments, and the owner refines them afterwards. Hence the requirements:
a "draft / owner-verified" status, convenient editing right in the game viewer, and an edit history.

## What an annotation is

An annotation is a set of notes on the moves of one game (`library_games.id`) in one original language with translations:

* **ply note** (`ply` 0...N; 0 is before the first move, the "introduction"): text, a move-quality sign (NAG), a position-evaluation
  sign, arrows and highlighted squares;
* **variation**: a sequence of moves from the position before `ply` (an alternative to the game move), with its own notes and
  nested variations (depth up to 3, as in the classics viewer 14.7);
* **author and status** of the whole annotation: `draft` (our draft) -> `review` (handed to the owner) -> `approved`
  (verified by the owner) -> back to `review` when edited after verification;
* **edit history**: every saved version is a full snapshot (annotations are small, <= 50 KB), with the author and time.

Texts are in two languages (en, uk) (en / uk, project rule 1). We write in one language, the other two are translations marked
"translation not verified"; the viewer shows the interface language and, when a translation is missing, the original with a note.

## Data model (new tables, one migration)

```
library_annotations
  id, game_id → library_games (unique: one annotation per game; several authors - later, in a separate table)
  status: draft | review | approved
  source_language: en | uk | ru
  body: JSON  — the annotation document (below)
  author_id → users, updated_by → users, created_at, updated_at, version (int, optimistic locking)

library_annotation_versions
  id, annotation_id, version, body JSON, status, edited_by, created_at
```

The `body` document (JSON, the schema is checked by a pydantic model and a test):

```json
{
  "intro": {"en": "...", "uk": "...", "ru": "..."},
  "notes": [
    {"ply": 12, "nag": "!", "eval": "+=", "text": {"ru": "..."}, "arrows": [["f3", "e5", "green"]], "squares": ["e5"],
     "variations": [{"moves": ["f6e4", "d2e4"], "notes": [{"index": 1, "text": {"ru": "..."}}], "variations": []}]}
  ],
  "translated": {"en": false, "uk": false}
}
```

* `nag` - only from a short list: `!`, `?`, `!!`, `??`, `!?`, `?!`; `eval` - `=`, `+=`, `=+`, `±`, `∓`, `+-`, `-+`,
  `∞` (symbols, not text - no translation needed).
* Variation moves are UCI, checked by python-chess on save; arrow colors are the same as for the board arrows.
* Limits: <= 400 notes, note text <= 1,000 characters per language, variation depth <= 3.

## API

* `GET /library/games/{id}` - adds `annotation` (only `approved` to everyone; `draft` / `review` to the author,
  moderators and the project owner), without history.
* `PUT /library/games/{id}/annotation` - save the document (moderators); the body is `body` + `version`; if someone else has a newer
  version, 409 with the current version (the "do not overwrite someone else's work" rule).
* `POST /library/games/{id}/annotation/status` - change the status (`review` by moderators, `approved` by the owner).
* `GET /library/games/{id}/annotation/versions` and `.../versions/{n}` - history and a snapshot.
* `GET /library/annotations?status=review` - the owner's review queue.
* PGN (`/games/{id}/pgn`) returns comments `{…}`, NAGs `$1…$6` and variations `( … )` in the requested language.

The engine is not called (rule 2 is not affected); the mentor draft is computed in advance by an offline script.

## Editor and viewer

* **Viewer** - the existing `GameViewer` in `library` mode: under the board the note text of the current move, the sign next to the move
  in the move list, variations as nested lines in the list (as in the classics 14.7), arrows and squares on the board.
* **Editing** (moderators) - a "Comment" button in the same viewer: a text field for the current move, a choice of NAG and
  evaluation, arrows drawn with the right mouse button (as in analysis), "Add variation" - the next move on the board goes into a variation.
  Saving is by an explicit button; the draft is not lost in the browser (localStorage, as in the repertoire editor).
* **Owner queue** - a list of games with status `review`, the difference from the last verified version by notes.

## Mentor drafts

For each game an offline script (`scripts/draft_annotations.py`) builds a draft the same way as the classics explanations
14.7: engine evaluation per move (through `get_engine_pool`), detector 11.1 motifs and positional features, texts assembled
from the `coach.*` keys in two languages (en, uk). Only "moments" go into the draft: mistakes (evaluation drop >= 150 cp),
the best move in a critical position, detector tactics, a change of pawn structure (27.5). Such a draft is `draft`,
the author is the service user "Mentor"; after that we edit it and the owner verifies it.

## Order of work

1. Model, migration, pydantic document schema, `GET` with the annotation and `PUT` with a version; schema and permission tests.
2. Viewer in `GameViewer`: notes, NAGs, variations, arrows; PGN export.
3. Editor in the viewer, version history, statuses and the owner queue.
4. Mentor draft script for the "Beautiful games" and "Champions' games" collections, then the rest.
5. Import of comments from the owner's PGN (if the file contains `{…}` and variations, save them as a draft instead of
   discarding them, as the 27.2 import does now).

## Questions for the owner (they do not block stages 1-3)

* Besides the owner, who can mark "verified" (is another reviewer needed)?
* Are comment author credits needed for the reader, or is "regence comments" enough?
