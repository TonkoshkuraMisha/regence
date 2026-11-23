"""Skill map (task 22.1): only one's own data - visible only to the player themselves."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.db.session import get_db
from src.models.user import User
from src.services import skills

router = APIRouter()


@router.get("")
async def my_skills(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await skills.skill_map(db, user)
