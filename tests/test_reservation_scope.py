"""Reservation time filters keep customer results scoped to the signed-in user."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pratice_harness.harness import Actor, SecurityHarness
from pratice_harness.models import Reservation
from pratice_harness.tools import RestaurantDirectory


class ReservationScopeTests(unittest.TestCase):
    def test_customer_past_filter_excludes_upcoming_and_other_customers(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = RestaurantDirectory(Path(folder) / "restaurant.sqlite3")
            try:
                past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
                with directory.Session.begin() as session:
                    own = Reservation(
                        customer_id="customer-1", guest_name="Past customer-1",
                        party_size=2, reservation_time=past,
                    )
                    other = Reservation(
                        customer_id="customer-2", guest_name="Past customer-2",
                        party_size=2, reservation_time=past,
                    )
                    session.add_all([own, other])

                harness = SecurityHarness(directory)
                actor = Actor("customer", "customer-1")
                past_result = json.loads(harness.validate_and_run(
                    "list_reservations", '{"time_scope":"past"}', actor,
                ))
                upcoming_result = json.loads(harness.validate_and_run(
                    "list_reservations", '{"time_scope":"upcoming"}', actor,
                ))
                self.assertEqual(past_result["status"], "success")
                self.assertEqual([row["guest_name"] for row in past_result["data"]], ["Past customer-1"])
                self.assertEqual(
                    [row["guest_name"] for row in upcoming_result["data"]],
                    ["Sam", "Lee", "Mina"],
                )
                invalid = json.loads(harness.validate_and_run(
                    "list_reservations", '{"time_scope":"later"}', actor,
                ))
                self.assertEqual(invalid["error_type"], "ValidationError")
            finally:
                directory.close()


if __name__ == "__main__":
    unittest.main()
