from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from pratice_harness.models import Cuisine, MenuItem, Reservation, Restaurant

CUISINES = (
    ("Khmer",
     (("Fish amok", 850), ("Beef lok lak", 900), ("Nom banh chok", 700), ("Bai sach chrouk", 650), ("Kuy teav", 750))),
    ("Italian", (("Margherita pizza", 1000), ("Pasta pomodoro", 950), ("Mushroom risotto", 1100), ("Lasagna", 1200),
                 ("Tiramisu", 650))),
    ("Vegetarian",
     (("Mushroom noodles", 700), ("Tofu stir fry", 800), ("Roasted vegetable bowl", 850), ("Pumpkin soup", 650),
      ("Chickpea salad", 750))),
    ("Japanese", (("Chicken ramen", 1100), ("Vegetable sushi", 900), ("Miso soup", 450), ("Teriyaki tofu", 950),
                  ("Matcha pudding", 600))),
    ("Indian", (("Chana masala", 850), ("Chicken biryani", 1050), ("Dal tadka", 750), ("Palak paneer", 950),
                ("Garlic naan", 350))),
)


def seed_database(session: Session) -> bool:
    """Seed a fresh database once; return whether rows were inserted."""
    if session.scalar(select(Restaurant.id).limit(1)) is not None:
        return False
    session.add(Restaurant(id=1, name="River Table", location="Phnom Penh", owner_id="owner-1"))
    for cuisine_name, menu in CUISINES:
        cuisine = Cuisine(name=cuisine_name)
        session.add(cuisine)
        session.flush()
        session.add_all(
            MenuItem(cuisine_id=cuisine.id, name=item_name, price_cents=cents)
            for item_name, cents in menu
        )
    today = datetime.now(timezone.utc)
    samples = (
        ("customer-1", "Sam", 2, 7),
        ("customer-2", "Ari", 3, 9),
        ("customer-1", "Lee", 4, 11),
        ("customer-2", "Jo", 2, 13),
        ("customer-1", "Mina", 2, 15),
        (None, "Walk-in booking", 4, 17),
    )
    session.add_all(
        Reservation(
            customer_id=customer_id,
            guest_name=guest_name,
            party_size=size,
            reservation_time=(today + timedelta(days=days)).isoformat(),
        )
        for customer_id, guest_name, size, days in samples
    )
    return True
