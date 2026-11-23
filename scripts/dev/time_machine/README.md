# "Time Machine" content: how a tournament is added

Tournaments and masters of the past are stored in code (`src/services/time_machine.py`, `src/services/bots/guests.py`) and in the three
client catalogs. These files are not edited by hand: a new entry is a **batch** (JSON) that a script applies, and
the final table is checked against the source by another script. All commands run from the repository root.

## Steps

1. **Download the source page** into the local cache (`.cache/`, not committed to the repository):

   ```
   python scripts/dev/time_machine/wiki_fetch.py scripts/dev/time_machine/.cache "Hastings 1895 chess tournament"
   ```

2. **Write a batch** `batches/batchN.json`: new masters (id, PGN name, life years, strength, character, a name and
   a line about the master in three languages) and tournaments (key, year, format, rounds, a "participant - score" table, title, place,
   a story and the real result in three languages). A sample is any of the finished batches.

   - Life years come from the first line of the master's article, not from memory: on 17.11 memory failed four times.
   - Only long-dead masters: the death year is no later than 1995. Without life years only participants of tournaments before 1905.
   - Namesakes are separate entries (Jacques Schwarz is not Adolf Schwarz, Frantisek Treybal is not Karel Treybal).
   - The line about a master contains only what the source confirms.

3. **Check the table against the source before applying:**

   ```
   python scripts/dev/time_machine/verify_batch.py scripts/dev/time_machine/batches/batch8.json
   ```

   In every row - the same player, the same score, the sum of the row's cells equals the score. The mapping "tournament key -> cache
   file and table number" is the `SOURCES` dict at the start of the script. If the final's scores add up with ones carried over from a
   preliminary tournament - `verify_carried_scores.py`.

4. **Apply the batch** to the server registries and client catalogs: `python scripts/dev/time_machine/apply_batch.py
   scripts/dev/time_machine/batches/batchN.json`.

5. **Check:** `uv run pytest tests/test_time_machine.py tests/test_time_machine_play.py -q` (general checks of any
   entry: order and sharing of places, sum of scores, entering the tournament, names and texts in three languages) and the client tests.

## What the finished batches are

`batches/batch2...13.json` - a record of what was added and in what form. Later corrections (life years,
lines about masters, signature openings) were made directly in the registries and catalogs, so they are the source of truth, not the
batches: there is no need to apply an old batch again, the script will refuse to add an existing entry.

## Re-checking the whole registry

`PYTHONPATH=. uv run python scripts/dev/time_machine/verify_registry.py` checks the already added tournaments against the
English sources more strictly: the participant's surname **and first name**, the score, the sum of the row's cells. Different spellings of the same
person's name (Wilhelm/William Steinitz, Dawid/David Janowski, Gersz/Georg Salwe) and typos in the sources themselves
(Vidmar at Carlsbad 1911: the table has 15½, by the row and the overall total - 15; the Schiffers and Schowalter cells at Vienna 1898)
are entered into the `KNOWN_SPELLINGS` and `KNOWN_SOURCE_TYPOS` lists at the start of the script - it must print `ALL OK`.

Wikipedia texts are distributed under the CC BY-SA licence; only facts (the field and scores) are taken into the repository,
the tournament stories are written anew.
