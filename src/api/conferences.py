# --- FILE: src/api/conferences.py ---
"""
Conferences (task 33.6): the season Conference Cup, the player's country in the profile. Rules and the table of countries -
src/services/conferences.py.
"""

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.api.fair_play import optional_user_id
from src.core.errors import DomainError
from src.db.session import get_db
from src.models.user import User
from src.services import arena as arena_service
from src.services import conferences as service
from src.services.arena_schedule import CONFERENCE_ZONES

router = APIRouter()

SEASON = r"^\d{4}-(0[1-9]|1[0-2])$"
_CODES = {"country_unknown": status.HTTP_400_BAD_REQUEST}


class CountryIn(BaseModel):
    """A country for the profile. The server does not use the player's address for this - the player sets the country
    themselves."""
    # ISO 3166-1 alpha-2 country code; null - remove the country from the profile.
    country: str | None = Field(None, min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")


@router.get("")
async def conferences_page(request: Request, season: str | None = Query(None, pattern=SEASON),
                           db: AsyncSession = Depends(get_db)):
    """
    The season Conference Cup (the current month by default), the season's conference matches and upcoming ones, the
    "country -> conference" table for selection in the profile and - for a logged-in player - their country and conference.
    suggested_country -
    the country named by the proxy (only a hint): taken from the header set by the
    COUNTRY_HEADER setting; while the setting is empty, there is no hint. Open to everyone.
    """
    user_id = await optional_user_id(request, db)
    user = await db.get(User, user_id) if user_id is not None else None
    await arena_service.ensure_schedule(db)  # the nearest conference match is created in advance - for signing up
    return {
        **await service.cup(db, season),
        "matches": await service.matches(db, season),
        "conferences": [{"key": key, "timezone": zone} for key, zone in CONFERENCE_ZONES.items()],
        "countries": service.CONFERENCE_OF,
        "suggested_country": service.suggested_country(request.headers),
        "me": service.membership(user) if user else None,
    }


@router.put("/me")
async def set_my_country(payload: CountryIn, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    """
    The country in one's own profile (users.country): the conference depends on it. The conference can be changed once per
    season - otherwise 409 country_change_too_soon; an unknown country code - 400.
    """
    try:
        return await service.set_country(db, user, payload.country)
    except DomainError as exc:
        raise exc.to_http(_CODES.get(exc.code, status.HTTP_409_CONFLICT)) from None
