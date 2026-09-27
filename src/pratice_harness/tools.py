"""SQLAlchemy-backed cuisine, menu, and reservation operations."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from .models import Base, Cuisine, MenuItem, Reservation, Restaurant
from .seed_data import seed_database


class RestaurantDirectory:
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        if str(db_path) != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(URL.create("sqlite+pysqlite", database=str(db_path)))

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
            # SQLite needs this connection setting to enforce the ORM foreign keys.
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        self._initialize()

    def close(self) -> None:
        self.engine.dispose()

    def _initialize(self) -> None:
        inspector = inspect(self.engine)
        if inspector.has_table("restaurants") and any(
            column["name"] == "cuisine" for column in inspector.get_columns("restaurants")
        ):
            raise RuntimeError(
                "This database uses the old multi-restaurant schema. Set RESTAURANT_DB_PATH in .env to a new database path."
            )
        Base.metadata.create_all(self.engine)
        with self.Session.begin() as session:
            seed_database(session)

    def is_owner(self, user_id: str) -> bool:
        with self.Session() as session:
            restaurant = session.get(Restaurant, 1)
            return restaurant is not None and restaurant.owner_id == user_id

    def cuisine_exists(self, cuisine_id: int) -> bool:
        with self.Session() as session:
            return session.get(Cuisine, cuisine_id) is not None

    def menu_item_exists(self, item_id: int) -> bool:
        with self.Session() as session:
            return session.get(MenuItem, item_id) is not None

    def reservation_access(self, reservation_id: int) -> tuple[str | None] | None:
        with self.Session() as session:
            reservation = session.get(Reservation, reservation_id)
            return (reservation.customer_id,) if reservation is not None else None

    def search_cuisine(self, query: str) -> list[dict]:
        with self.Session() as session:
            cuisines = session.scalars(
                select(Cuisine).where(Cuisine.name.ilike(f"%{query}%")).order_by(Cuisine.name)
            ).all()
            return [{"cuisine_id": cuisine.id, "name": cuisine.name} for cuisine in cuisines]

    def check_menu(self, cuisine_id: int) -> dict:
        with self.Session() as session:
            cuisine = session.get(Cuisine, cuisine_id)
            if cuisine is None:
                return {"cuisine_id": cuisine_id, "found": False}
            items = session.scalars(
                select(MenuItem).where(MenuItem.cuisine_id == cuisine_id).order_by(MenuItem.id)
            ).all()
            return {
                "cuisine_id": cuisine_id,
                "cuisine_name": cuisine.name,
                "restaurant_name": "River Table",
                "found": True,
                "menu": [
                    {"item_id": item.id, "name": item.name, "price_usd": item.price_cents / 100}
                    for item in items
                ],
            }

    def create_menu_item(self, cuisine_id: int, name: str, price_usd: Decimal) -> dict:
        with self.Session.begin() as session:
            item = MenuItem(cuisine_id=cuisine_id, name=name, price_cents=int(price_usd * 100))
            session.add(item)
            session.flush()
            item_id = item.id
        return {
            "created": True, "item_id": item_id, "cuisine_id": cuisine_id,
            "name": name, "price_usd": float(price_usd),
        }

    def update_menu_item(self, item_id: int, name: str | None = None, price_usd: Decimal | None = None) -> dict:
        with self.Session.begin() as session:
            item = session.get(MenuItem, item_id)
            if item is None:
                return {"updated": False, "item_id": item_id}
            if name is not None:
                item.name = name
            if price_usd is not None:
                item.price_cents = int(price_usd * 100)
        return {"updated": True, "item_id": item_id}

    def delete_menu_item(self, item_id: int) -> dict:
        with self.Session.begin() as session:
            item = session.get(MenuItem, item_id)
            if item is None:
                return {"deleted": False, "item_id": item_id}
            session.delete(item)
        return {"deleted": True, "item_id": item_id}

    def make_reservation(
        self, guest_name: str, party_size: int, reservation_time: datetime, customer_id: str | None
    ) -> dict:
        if reservation_time <= datetime.now(timezone.utc):
            return {"reserved": False, "reason": "Reservation time must be in the future."}
        when = reservation_time.astimezone(timezone.utc).isoformat()
        with self.Session.begin() as session:
            reservation = Reservation(
                customer_id=customer_id, guest_name=guest_name,
                party_size=party_size, reservation_time=when,
            )
            session.add(reservation)
            session.flush()
            reservation_id = reservation.id
        return {
            "reserved": True,
            "reservation_id": reservation_id,
            "confirmation_id": f"R{reservation_id:04d}",
            "restaurant_name": "River Table",
            "guest_name": guest_name,
            "party_size": party_size,
            "reservation_time": when,
        }

    def list_reservations(
        self, *, customer_id: str | None = None, owner_id: str | None = None,
        time_scope: str = "all",
    ) -> list[dict]:
        with self.Session() as session:
            statement = select(Reservation).order_by(Reservation.id)
            if customer_id is not None:
                statement = statement.where(Reservation.customer_id == customer_id)
            else:
                restaurant = session.get(Restaurant, 1)
                if owner_id is None or restaurant is None or restaurant.owner_id != owner_id:
                    raise ValueError("A valid reservation scope is required.")
            reservations = session.scalars(statement).all()
            if time_scope != "all":
                now = datetime.now(timezone.utc)
                reservations = [
                    reservation for reservation in reservations
                    if (datetime.fromisoformat(reservation.reservation_time) < now)
                    == (time_scope == "past")
                ]
            return [
                {
                    "reservation_id": reservation.id,
                    "guest_name": reservation.guest_name,
                    "party_size": reservation.party_size,
                    "reservation_time": reservation.reservation_time,
                }
                for reservation in reservations
            ]

    def update_reservation(
        self,
        reservation_id: int,
        guest_name: str | None = None,
        party_size: int | None = None,
        reservation_time: datetime | None = None,
    ) -> dict:
        if reservation_time is not None and reservation_time <= datetime.now(timezone.utc):
            return {"updated": False, "reason": "Reservation time must be in the future."}
        with self.Session.begin() as session:
            reservation = session.get(Reservation, reservation_id)
            if reservation is None:
                return {"updated": False, "reservation_id": reservation_id}
            if guest_name is not None:
                reservation.guest_name = guest_name
            if party_size is not None:
                reservation.party_size = party_size
            if reservation_time is not None:
                reservation.reservation_time = reservation_time.astimezone(timezone.utc).isoformat()
        return {"updated": True, "reservation_id": reservation_id}

    def delete_reservation(self, reservation_id: int) -> dict:
        with self.Session.begin() as session:
            reservation = session.get(Reservation, reservation_id)
            if reservation is None:
                return {"deleted": False, "reservation_id": reservation_id}
            session.delete(reservation)
        return {"deleted": True, "reservation_id": reservation_id}
