"""Ежедневная разминка (таск 22.2): план на сегодня и серия дней — по самим тренировкам игрока."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.db.session import get_db
from src.models.user import User
from src.services import weekly_summary, workout

router = APIRouter()


@router.get("")
async def today(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await workout.plan(db, user, workout.utcnow())


@router.get("/week")
async def week(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """«Моя неделя»: итоги последних 7 суток и совет кодом (src/services/weekly_summary.py)."""
    return await weekly_summary.build(db, user)
