import logging
import os
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import InventoryPath, RequestPriority, Role
from app.models import (
    EmployeeRecipient,
    Item,
    Location,
    MapGridCell,
    RoleAssignment,
    StockPosition,
    UnitOfMeasure,
    User,
    Warehouse,
)
from app.modules.identity.service import AuthenticatedUser
from app.modules.requests.schemas import CreateMaterialRequest, RequestLineInput
from app.modules.requests.service import RequestService
from app.platform.database import SessionLocal
from app.platform.logging import configure_logging
from app.platform.security.tokens import hash_password

logger = logging.getLogger("inventory.seed")


@dataclass(frozen=True, slots=True)
class ItemSeed:
    sku: str
    description: str
    path: InventoryPath
    uom: str
    reorder_point: str
    spectrum_id: str | None
    locations: tuple[tuple[str, str], ...]


def seed_database(session: Session, password: str) -> None:
    existing = session.scalar(select(Warehouse).where(Warehouse.code == "WH1"))
    if existing is not None:
        logger.info("seed_skipped_existing_warehouse")
        return

    warehouse = Warehouse(code="WH1", name="Haynes Main Warehouse")
    each = UnitOfMeasure(code="EA", name="Each", decimal_places=0)
    foot = UnitOfMeasure(code="FT", name="Foot", decimal_places=1)
    box = UnitOfMeasure(code="BOX", name="Box", decimal_places=0)
    session.add_all([warehouse, each, foot, box])
    session.flush()

    location_specs = [
        ("WH1-A01-B02-S01-P01", "A", "01", "02", "01", "01", 10, 0, 0, False),
        ("WH1-A01-B04-S02-P01", "A", "01", "04", "02", "01", 20, 0, 1, False),
        ("WH1-A02-B01-S01-P02", "A", "02", "01", "01", "02", 30, 1, 0, False),
        ("WH1-B01-B03-S02-P01", "B", "01", "03", "02", "01", 40, 1, 1, False),
        ("WH1-C01-B01-S01-P01", "C", "01", "01", "01", "01", 50, 2, 0, False),
        ("WH1-STAGE-01", "STAGE", "00", "01", "00", "01", 900, 2, 1, True),
    ]
    locations: dict[str, Location] = {}
    for code, zone, aisle, bay, shelf, position, sequence, row, column, staging in location_specs:
        location = Location(
            warehouse_id=warehouse.id,
            code=code,
            zone=zone,
            aisle=aisle,
            bay=bay,
            shelf=shelf,
            position=position,
            pick_sequence=sequence,
            is_staging=staging,
        )
        session.add(location)
        session.flush()
        session.add(
            MapGridCell(
                warehouse_id=warehouse.id,
                location_id=location.id,
                row_index=row,
                column_index=column,
                label=code,
            )
        )
        locations[code] = location

    users: dict[str, User] = {}
    user_specs = [
        ("employee", "Alex Employee", (Role.EMPLOYEE,)),
        ("foreman", "Morgan Foreman", (Role.FOREMAN,)),
        ("worker", "Jordan Warehouse", (Role.WAREHOUSE_WORKER,)),
        (
            "manager",
            "Casey Inventory",
            (Role.WAREHOUSE_WORKER, Role.INVENTORY_MANAGER),
        ),
        (
            "admin",
            "Riley Administrator",
            (Role.SYSTEM_ADMINISTRATOR, Role.INVENTORY_MANAGER),
        ),
    ]
    for username, display_name, roles in user_specs:
        user = User(
            warehouse_id=warehouse.id,
            username=username,
            display_name=display_name,
            password_hash=hash_password(password),
        )
        session.add(user)
        session.flush()
        users[username] = user
        session.add_all(
            RoleAssignment(warehouse_id=warehouse.id, user_id=user.id, role=role)
            for role in roles
        )

    recipients: dict[str, EmployeeRecipient] = {}
    recipient_specs = [
        ("E-1001", "Morgan Foreman", users["foreman"].id),
        ("E-1002", "Taylor Brooks", None),
        ("E-1003", "Avery Patel", None),
        ("E-1004", "Alex Employee", users["employee"].id),
    ]
    for employee_number, display_name, linked_user_id in recipient_specs:
        recipient = EmployeeRecipient(
            warehouse_id=warehouse.id,
            employee_number=employee_number,
            display_name=display_name,
            linked_user_id=linked_user_id,
        )
        session.add(recipient)
        recipients[employee_number] = recipient

    uoms = {uom.code: uom for uom in (each, foot, box)}
    item_specs = [
        ItemSeed(
            "WIRE-THHN-12-BLK",
            "12 AWG THHN copper wire, black",
            InventoryPath.SPECTRUM_MANAGED,
            "FT",
            "100",
            "SP-100042",
            (("WH1-A01-B02-S01-P01", "50"), ("WH1-A01-B04-S02-P01", "20")),
        ),
        ItemSeed(
            "BRKR-20A-1P",
            "20A single-pole circuit breaker",
            InventoryPath.SPECTRUM_MANAGED,
            "EA",
            "12",
            "SP-100118",
            (("WH1-A02-B01-S01-P02", "10"),),
        ),
        ItemSeed(
            "EMT-075-10",
            "3/4 inch EMT conduit, 10 ft",
            InventoryPath.SPECTRUM_MANAGED,
            "EA",
            "30",
            "SP-100207",
            (("WH1-C01-B01-S01-P01", "84"),),
        ),
        ItemSeed(
            "TAPE-BLK-34",
            "3/4 inch electrical tape, black",
            InventoryPath.LOCAL_GENERAL_USE,
            "EA",
            "24",
            None,
            (("WH1-B01-B03-S02-P01", "120"),),
        ),
        ItemSeed(
            "GLOVE-CUT-L",
            "Cut-resistant work gloves, large",
            InventoryPath.LOCAL_GENERAL_USE,
            "EA",
            "12",
            None,
            (("WH1-B01-B03-S02-P01", "36"),),
        ),
        ItemSeed(
            "WIRENUT-RED-BOX",
            "Red wire connectors, box of 100",
            InventoryPath.LOCAL_GENERAL_USE,
            "BOX",
            "8",
            None,
            (("WH1-A02-B01-S01-P02", "18"),),
        ),
    ]
    items: dict[str, Item] = {}
    for spec in item_specs:
        item = Item(
            warehouse_id=warehouse.id,
            sku=spec.sku,
            description=spec.description,
            inventory_path=spec.path,
            spectrum_item_id=spec.spectrum_id,
            uom_id=uoms[spec.uom].id,
            reorder_point=Decimal(spec.reorder_point),
        )
        session.add(item)
        session.flush()
        items[item.sku] = item
        for location_code, quantity in spec.locations:
            session.add(
                StockPosition(
                    warehouse_id=warehouse.id,
                    item_id=item.id,
                    location_id=locations[location_code].id,
                    on_hand=Decimal(quantity),
                )
            )
    session.commit()

    foreman = users["foreman"]
    foreman_context = AuthenticatedUser(
        id=foreman.id,
        warehouse_id=warehouse.id,
        warehouse_code=warehouse.code,
        username=foreman.username,
        display_name=foreman.display_name,
        roles=frozenset({Role.FOREMAN}),
    )
    request_service = RequestService(session, foreman_context)
    request_service.create(
        CreateMaterialRequest(
            recipient_id=recipients["E-1001"].id,
            priority=RequestPriority.URGENT,
            urgent_reason="Service crew waiting at counter",
            job_number="4102-HOSPITAL",
            cost_code="26-05-00",
            lines=[
                RequestLineInput(
                    item_id=items["WIRE-THHN-12-BLK"].id, quantity=Decimal("40")
                ),
                RequestLineInput(
                    item_id=items["TAPE-BLK-34"].id, quantity=Decimal("6")
                ),
            ],
        )
    )
    request_service.create(
        CreateMaterialRequest(
            recipient_id=recipients["E-1002"].id,
            job_number="4077-SCHOOL",
            cost_code="26-28-00",
            lines=[
                RequestLineInput(
                    item_id=items["BRKR-20A-1P"].id, quantity=Decimal("16")
                )
            ],
        )
    )
    logger.info("seed_complete")


def main() -> None:
    configure_logging()
    password = os.environ.get("INVENTORY_SEED_PASSWORD")
    if not password:
        raise RuntimeError("INVENTORY_SEED_PASSWORD is required to seed development users")
    with SessionLocal() as session:
        seed_database(session, password)


if __name__ == "__main__":
    main()
