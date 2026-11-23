# --- FILE: migrations/versions/e1a7c3d9b5f2_neutral_bot_identities.py ---

"""neutral_bot_identities

Task 11.0c: the server neither stores nor serves human-language texts - names in the player's language are set by the client.

* Bot users get neutral names: a historical bot gets its own id ("morphy"), the shared workshop opponent gets
  "workshop_opponent" (service accounts "... [bot]" become "<id>_bot").
* Games with workshop archetypes store the key "archetype:<id>" in personality_name instead of the legacy localised name.
* In PGN headers the legacy localised bot names are replaced by PGN names (Latin, as in the masters' archives); archetype names
  become English.

The downgrade restores the former names. A player's personality named exactly like an archetype will become the archetype
on upgrade (they are indistinguishable by data); this affects neither the moves of games nor ratings.

Revision ID: e1a7c3d9b5f2
Revises: c8e1f4a7b2d5
Create Date: 2026-11-13 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1a7c3d9b5f2"
down_revision: str | Sequence[str] | None = "c8e1f4a7b2d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# bot id -> (former user name, name for PGN); the former names are legacy Russian data matched against the database, keep as is
BOTS = {
    "philidor": ("\u0424.-\u0410. \u0424\u0438\u043b\u0438\u0434\u043e\u0440", "Philidor, François-André"),
    "labourdonnais": ("\u041b.-\u0428. \u041b\u0430\u0431\u0443\u0440\u0434\u043e\u043d\u043d\u0435", "La Bourdonnais, Louis-Charles"),
    "staunton": ("\u0413. \u0421\u0442\u0430\u0443\u043d\u0442\u043e\u043d", "Staunton, Howard"),
    "anderssen": ("\u0410. \u0410\u043d\u0434\u0435\u0440\u0441\u0435\u043d", "Anderssen, Adolf"),
    "morphy": ("\u041f\u043e\u043b \u041c\u043e\u0440\u0444\u0438", "Morphy, Paul"),
    "paulsen": ("\u041b. \u041f\u0430\u0443\u043b\u044c\u0441\u0435\u043d", "Paulsen, Louis"),
    "zukertort": ("\u0418. \u0426\u0443\u043a\u0435\u0440\u0442\u043e\u0440\u0442", "Zukertort, Johannes"),
}
WORKSHOP = ("\u0421\u043e\u043f\u0435\u0440\u043d\u0438\u043a-\u0438\u0437-\u043c\u0430\u0441\u0442\u0435\u0440\u0441\u043a\u043e\u0439", "workshop_opponent")

# archetype id -> (former legacy name, name for PGN); matched against the database, keep as is
ARCHETYPES = {
    "rusher": ("\u0422\u043e\u0440\u043e\u043f\u044b\u0433\u0430", "Rusher"),
    "quiet": ("\u0422\u0438\u0445\u043e\u043d\u044f", "Quiet One"),
    "pawn_keeper": ("\u041f\u0435\u0448\u0435\u0447\u043d\u0438\u043a", "Pawn Keeper"),
    "cavalier": ("\u041a\u0430\u0432\u0430\u043b\u0435\u0440\u0438\u0441\u0442", "Cavalier"),
    "centralist": ("\u0426\u0435\u043d\u0442\u0440\u043e\u0432\u0438\u043a", "Centralist"),
    "fortress": ("\u041a\u0440\u0435\u043f\u043e\u0441\u0442\u044c", "Fortress"),
    "adventurer": ("\u0410\u0432\u0430\u043d\u0442\u044e\u0440\u0438\u0441\u0442", "Adventurer"),
    "strategist": ("\u0421\u0442\u0440\u0430\u0442\u0435\u0433", "Strategist"),
    "hunter": ("\u041e\u0445\u043e\u0442\u043d\u0438\u043a", "Hunter"),
    "combinator": ("\u041a\u043e\u043c\u0431\u0438\u043d\u0430\u0442\u043e\u0440", "Combinator"),
}


def _rename_user(old: str, new: str) -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE users SET username = :new, username_key = :new_key "
            "WHERE username = :old AND is_bot "
            "AND NOT EXISTS (SELECT 1 FROM users other WHERE other.username = :new)"
        ),
        {"old": old, "new": new, "new_key": new.casefold()},
    )


def _replace_pgn_names(
        old: str, new: str, *, bot_username: str | None = None, personality_name: str | None = None,
) -> None:
    """
    The name in the White/Black headers - only in games of this bot (or this personality): masters' games in the
    historical archive with the same name in the header (for example "Morphy, Paul") are left alone.
    """
    condition = "pgn LIKE :pattern"
    params: dict[str, str] = {"pattern": f'%"{old}"]%'}
    if bot_username is not None:
        condition += (
            " AND EXISTS (SELECT 1 FROM users bot WHERE bot.username = :bot AND bot.is_bot"
            " AND bot.id IN (games.white_player_id, games.black_player_id))"
        )
        params["bot"] = bot_username
    if personality_name is not None:
        condition += " AND personality_name = :personality"
        params["personality"] = personality_name
    for tag in ("White", "Black"):
        op.get_bind().execute(
            sa.text(f"UPDATE games SET pgn = replace(pgn, :old_tag, :new_tag) WHERE {condition}"),
            {**params, "old_tag": f'[{tag} "{old}"]', "new_tag": f'[{tag} "{new}"]'},
        )


def upgrade() -> None:
    for bot_id, (old_name, pgn_name) in BOTS.items():
        _rename_user(old_name, bot_id)
        _rename_user(f"{old_name} [\u0431\u043e\u0442]", f"{bot_id}_bot")
        for username in (bot_id, f"{bot_id}_bot"):
            _replace_pgn_names(old_name, pgn_name, bot_username=username)
    _rename_user(*WORKSHOP)

    bind = op.get_bind()
    for archetype_id, (old_name, pgn_name) in ARCHETYPES.items():
        key = f"archetype:{archetype_id}"
        bind.execute(
            sa.text("UPDATE games SET personality_name = :key WHERE personality_name = :old"),
            {"key": key, "old": old_name},
        )
        _replace_pgn_names(old_name, pgn_name, personality_name=key)


def downgrade() -> None:
    bind = op.get_bind()
    for archetype_id, (old_name, pgn_name) in ARCHETYPES.items():
        key = f"archetype:{archetype_id}"
        _replace_pgn_names(pgn_name, old_name, personality_name=key)
        bind.execute(
            sa.text("UPDATE games SET personality_name = :old WHERE personality_name = :key"),
            {"key": key, "old": old_name},
        )

    _rename_user(WORKSHOP[1], WORKSHOP[0])
    for bot_id, (old_name, pgn_name) in BOTS.items():
        for username in (bot_id, f"{bot_id}_bot"):
            _replace_pgn_names(pgn_name, old_name, bot_username=username)
        _rename_user(f"{bot_id}_bot", f"{old_name} [\u0431\u043e\u0442]")
        _rename_user(bot_id, old_name)
