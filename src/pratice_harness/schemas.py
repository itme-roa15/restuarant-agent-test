from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, model_validator


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchCuisineInput(ToolInput):
    query: str = Field(min_length=1)


class CheckMenuInput(ToolInput):
    cuisine_id: StrictInt = Field(gt=0)


class CreateMenuItemInput(ToolInput):
    cuisine_id: StrictInt = Field(gt=0)
    name: str = Field(min_length=1)
    price_usd: Decimal = Field(gt=0, max_digits=8, decimal_places=2)


class UpdateMenuItemInput(ToolInput):
    item_id: StrictInt = Field(gt=0)
    name: str | None = Field(default=None, min_length=1)
    price_usd: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=2)

    @model_validator(mode="after")
    def require_change(self) -> "UpdateMenuItemInput":
        if self.name is None and self.price_usd is None:
            raise ValueError("Supply a name or price_usd to update.")
        return self


class DeleteMenuItemInput(ToolInput):
    item_id: StrictInt = Field(gt=0)


class MakeReservationInput(ToolInput):
    guest_name: str = Field(min_length=1)
    party_size: StrictInt = Field(ge=1, le=8)
    reservation_time: AwareDatetime


class ListReservationsInput(ToolInput):
    time_scope: Literal["all", "past", "upcoming"] = Field(
        default="all",
        description="Use past for previous reservations, upcoming for future reservations, or all for both.",
    )


class UpdateReservationInput(ToolInput):
    reservation_id: StrictInt = Field(gt=0)
    guest_name: str | None = Field(default=None, min_length=1)
    party_size: StrictInt | None = Field(default=None, ge=1, le=8)
    reservation_time: AwareDatetime | None = None

    @model_validator(mode="after")
    def require_change(self) -> "UpdateReservationInput":
        if self.guest_name is None and self.party_size is None and self.reservation_time is None:
            raise ValueError("Supply a reservation field to update.")
        return self


class DeleteReservationInput(ToolInput):
    reservation_id: StrictInt = Field(gt=0)


_TOOLS = (
    ("search_cuisine", "Find a cuisine served by this restaurant by name.", SearchCuisineInput),
    ("check_menu", "Show dishes and item IDs for a cuisine.", CheckMenuInput),
    ("create_menu_item", "Add a dish to a cuisine. Owner only.", CreateMenuItemInput),
    ("update_menu_item", "Change a menu item's name or price. Owner only.", UpdateMenuItemInput),
    ("delete_menu_item", "Remove a menu item. Owner only.", DeleteMenuItemInput),
    ("make_reservation", "Reserve a table for one to eight guests.", MakeReservationInput),
    ("list_reservations", "List reservations visible to the current customer or owner, filtered by time_scope when requested.", ListReservationsInput),
    ("update_reservation", "Change an existing reservation.", UpdateReservationInput),
    ("delete_reservation", "Cancel an existing reservation.", DeleteReservationInput),
)

TOOL_SCHEMAS: dict[str, type[ToolInput]] = {name: schema for name, _, schema in _TOOLS}
TOOL_DEFINITIONS = [
    {"type": "function",
     "function": {"name": name, "description": description, "parameters": schema.model_json_schema()}}
    for name, description, schema in _TOOLS
]
