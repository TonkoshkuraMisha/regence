"""
Product metric events (the product_events table). Written by src/services/product_metrics.py, the report to the owner
is computed by scripts/product_metrics.py.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.models.base import Base


class ProductEvent(Base):
    """
    A product event (task 23.5): our own analytics without third-party trackers. Only the event kind, the player and the time -
    no IP, no name, no game contents. Each kind - at most once per UTC day per player: this is enough for
    the funnel (first game, first puzzle) and retention (active days), and the table grows predictably.
    """

    __tablename__ = "product_events"
    __table_args__ = (UniqueConstraint("user_id", "kind", "day", name="uq_product_event_daily"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
