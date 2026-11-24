"""
All database models in one place.

Importing each model file here is mandatory: Alembic takes tables from Base.metadata after importing this package
(migrations/env.py), tests create the schema the same way. A model from a file that is not imported here will get into neither
the migration nor the `alembic check` check. A table is registered when its file is imported, so a model from an already
imported file is visible to Alembic even if its name is not in the list below (this is currently the case for LibraryAnnotation
from
library.py - it is imported directly from src.models.library). Which tables belong to which site section -
docs/ARCHITECTURE.md, section 3.
"""

from src.models.achievement import UserAchievement
from src.models.arena import Arena, ArenaAward, ArenaGame, ArenaPlayer, ArenaReminder
from src.models.base import Base
from src.models.beta import Feedback, Invite
from src.models.bot_memory import BotOpeningStat, BotRating, BotRival, BotRivalStat, BotTuning, BotTuningLog
from src.models.collection import CollectionEntry
from src.models.email_token import EmailToken
from src.models.game import Game
from src.models.guess import GuessPosition
from src.models.imported_game import ImportedGame
from src.models.ladder import LadderBeaten
from src.models.lesson import LessonProgress
from src.models.library import LibraryCollection, LibraryGame, LibraryGameCollection
from src.models.moderation import Report
from src.models.move import Move
from src.models.personality import BotPersonality
from src.models.position import PositionGame, PositionLibraryGame, PositionStat
from src.models.product_event import ProductEvent
from src.models.puzzle import (
    DefenseDrill,
    DrillRecord,
    PersonalPuzzle,
    Puzzle,
    PuzzleAttempt,
    PuzzleTheme,
    PuzzleTimedScore,
    ThemeProgress,
)
from src.models.repertoire import Repertoire, RepertoireCard, RepertoireMove
from src.models.social import (
    Block,
    DirectMessage,
    Follow,
    HiddenConversation,
    Notification,
    Post,
    PostComment,
    PostLike,
)
from src.models.study import StudyMaterial
from src.models.team import Team, TeamMember
from src.models.tournament import Tournament, TournamentGame, TournamentPlayer
from src.models.trainer import ExamResult, TrainerResult
from src.models.user import User
from src.models.weekly_legends import WeeklyLegendGame

__all__ = [
    "WeeklyLegendGame",
    "PuzzleTimedScore",
    "BotOpeningStat",
    "BotRating",
    "BotRival",
    "BotRivalStat",
    "BotTuning",
    "BotTuningLog",
    "Arena",
    "ArenaAward",
    "ArenaGame",
    "ArenaPlayer",
    "ArenaReminder",
    "Base",
    "BotPersonality",
    "DefenseDrill",
    "DrillRecord",
    "EmailToken",
    "Feedback",
    "Invite",
    "Game",
    "CollectionEntry",
    "Follow",
    "GuessPosition",
    "ImportedGame",
    "Notification",
    "DirectMessage",
    "Block",
    "Post",
    "PostComment",
    "PostLike",
    "HiddenConversation",
    "PositionGame",
    "PositionLibraryGame",
    "PositionStat",
    "LessonProgress",
    "Move",
    "Report",
    "LadderBeaten",
    "PersonalPuzzle",
    "ProductEvent",
    "Puzzle",
    "PuzzleAttempt",
    "PuzzleTheme",
    "ThemeProgress",
    "LibraryCollection",
    "LibraryGame",
    "LibraryGameCollection",
    "Repertoire",
    "RepertoireCard",
    "RepertoireMove",
    "ExamResult",
    "TrainerResult",
    "StudyMaterial",
    "Team",
    "TeamMember",
    "Tournament",
    "TournamentGame",
    "TournamentPlayer",
    "User",
    "UserAchievement",
]

# The imports above are needed for their side effect: when this package is imported all tables end up in Base.metadata.
