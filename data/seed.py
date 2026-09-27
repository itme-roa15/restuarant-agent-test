from __future__ import annotations

import argparse

from sqlalchemy import func, select

from pratice_harness.models import MenuItem


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/restaurants.sqlite3", help="SQLite database path")
    args = parser.parse_args()
    from pratice_harness.tools import RestaurantDirectory

    directory = RestaurantDirectory(args.db)
    with directory.Session() as session:
        count = session.scalar(select(func.count()).select_from(MenuItem))
    directory.close()
    print(f"Database ready at {args.db}: {count} menu items.")


if __name__ == "__main__":
    main()
