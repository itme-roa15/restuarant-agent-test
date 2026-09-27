"""SQLAlchemy models for the sample restaurant database."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str] = mapped_column(String, nullable=False)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)


class Cuisine(Base):
    __tablename__ = "cuisines"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)


class MenuItem(Base):
    __tablename__ = "menu_items"
    __table_args__ = (CheckConstraint("price_cents > 0"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cuisine_id: Mapped[int] = mapped_column(ForeignKey("cuisines.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (CheckConstraint("party_size BETWEEN 1 AND 8"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[str | None] = mapped_column(String)
    guest_name: Mapped[str] = mapped_column(String, nullable=False)
    party_size: Mapped[int] = mapped_column(Integer, nullable=False)
    reservation_time: Mapped[str] = mapped_column(String, nullable=False)
