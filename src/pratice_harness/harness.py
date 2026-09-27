from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import ValidationError

from .schemas import TOOL_SCHEMAS
from .tools import RestaurantDirectory

PERMISSIONS = {
    "guest": frozenset({"search_cuisine", "check_menu"}),
    "customer": frozenset({
        "search_cuisine", "check_menu", "make_reservation", "list_reservations",
        "update_reservation", "delete_reservation",
    }),
    "owner": frozenset(TOOL_SCHEMAS),
}
MENU_WRITES = frozenset({"create_menu_item", "update_menu_item", "delete_menu_item"})
RESERVATION_WRITES = frozenset({"update_reservation", "delete_reservation"})


@dataclass(frozen=True)
class Actor:
    role: str
    user_id: str

    def __post_init__(self) -> None:
        if self.role not in PERMISSIONS:
            raise ValueError(f"Unknown role: {self.role}")
        if not self.user_id:
            raise ValueError("A session user ID is required")


class SecurityHarness:
    def __init__(self, directory: RestaurantDirectory) -> None:
        self.directory = directory

    def authorize(self, actor: Actor, tool_name: str) -> bool:
        return tool_name in PERMISSIONS[actor.role]

    @staticmethod
    def _error(error_type: str, message: str) -> str:
        return json.dumps({"status": "error", "error_type": error_type, "message": message})

    def _check_resource(self, tool_name: str, args: dict, actor: Actor) -> str | None:
        if actor.role == "owner" and tool_name not in {"search_cuisine", "check_menu"}:
            if not self.directory.is_owner(actor.user_id):
                return self._error("PermissionDenied", "This session does not own the restaurant.")

        if tool_name in MENU_WRITES:
            if tool_name == "create_menu_item" and not self.directory.cuisine_exists(args["cuisine_id"]):
                return self._error("NotFound", "Cuisine not found.")
            if tool_name != "create_menu_item" and not self.directory.menu_item_exists(args["item_id"]):
                return self._error("NotFound", "Menu item not found.")

        if tool_name in RESERVATION_WRITES:
            access = self.directory.reservation_access(args["reservation_id"])
            if access is None:
                return self._error("NotFound", "Reservation not found.")
            (customer_id,) = access
            allowed = (actor.role == "customer" and customer_id == actor.user_id) or actor.role == "owner"
            if not allowed:
                return self._error("PermissionDenied", "This session cannot manage that reservation.")
        return None

    def validate_and_run(self, tool_name: str, raw_args: str | dict, actor: Actor) -> str:
        if tool_name not in TOOL_SCHEMAS:
            return self._error("UnknownTool", f"Unknown tool '{tool_name}'.")
        if not self.authorize(actor, tool_name):
            return self._error("PermissionDenied", f"Role '{actor.role}' cannot invoke '{tool_name}'.")

        schema = TOOL_SCHEMAS[tool_name]
        try:
            args = (
                schema.model_validate_json(raw_args)
                if isinstance(raw_args, str)
                else schema.model_validate(raw_args)
            ).model_dump()
        except (ValidationError, TypeError, ValueError):
            return self._error("ValidationError", f"Invalid arguments for '{tool_name}'.")

        try:
            resource_error = self._check_resource(tool_name, args, actor)
            if resource_error:
                return resource_error
            operation = getattr(self.directory, tool_name)
            if tool_name == "make_reservation":
                args["customer_id"] = actor.user_id if actor.role == "customer" else None
            elif tool_name == "list_reservations":
                key = "customer_id" if actor.role == "customer" else "owner_id"
                args[key] = actor.user_id
            data = operation(**args)
        except Exception:
            return self._error("ToolExecutionError", f"Tool '{tool_name}' failed during execution.")
        return json.dumps({"status": "success", "data": data})
