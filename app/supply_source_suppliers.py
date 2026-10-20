"""Supplier catalogue reads and explicit first-use setup for supply-source runs."""

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Supplier, SuppliersAudit
from app.supply_source_runs import SupplySourceRunError, parse_aufschlag_percent
from app.weclapp import map_weclapp_error, weclapp_client_for
from scripts.weclapp.client import WeclappError

PROPERTIES = "id,company,firstName,lastName,supplierNumber,supplier,supplierActive"


def supplier_option(party: dict[str, Any], local: Supplier | None = None) -> dict | None:
    if party.get("supplier") is not True or party.get("supplierActive") is False:
        return None
    party_id = str(party.get("id") or "").strip()
    number = str(party.get("supplierNumber") or "").strip()
    name = (
        str(party.get("company") or "").strip()
        or " ".join(str(party.get(k) or "").strip() for k in ("firstName", "lastName")).strip()
    )
    if not party_id or not number or not name:
        return None
    return {
        "id": str(local.id) if local else f"weclapp:{party_id}",
        "number": number,
        "name": name,
        "label": f"{number} · {name}",
        "needs_setup": local is None,
    }


def supplier_catalogue(db: Session, oid: str) -> list[dict]:
    # Include inactive/deleted locals in the index so a remote read cannot restore them.
    locals_by_party = {s.weclapp_party_id: s for s in db.scalars(select(Supplier))}
    client = weclapp_client_for(db, oid)
    options = []
    try:
        for party in client.iter_pages(
            "party",
            params={
                "supplier-eq": "true",
                "supplierActive-eq": "true",
                "properties": PROPERTIES,
            },
        ):
            local = locals_by_party.get(str(party.get("id") or ""))
            if local and (local.deleted_at is not None or not local.is_active):
                continue
            option = supplier_option(party, local)
            if option:
                options.append(option)
    except WeclappError as exc:
        raise map_weclapp_error(exc) from exc
    return sorted(options, key=lambda o: (o["number"], o["name"].casefold()))


def resolve_supplier(
    db: Session,
    *,
    selection: str,
    user: Mapping[str, Any],
    currency: str = "",
    rate: str = "",
    markup: str = "",
) -> Supplier:
    selection = selection.strip()
    if not selection.startswith("weclapp:"):
        supplier = db.get(Supplier, int(selection)) if selection.isdecimal() else None
        if supplier is None or supplier.deleted_at is not None or not supplier.is_active:
            raise SupplySourceRunError(
                "Bitte einen aktiven Lieferanten aus der Trefferliste auswählen."
            )
        return supplier
    party_id = selection.removeprefix("weclapp:")
    if not party_id.isdecimal():
        raise SupplySourceRunError("Lieferantenauswahl ist ungültig.")
    existing = db.scalar(select(Supplier).where(Supplier.weclapp_party_id == party_id))
    if existing:
        return resolve_supplier(db, selection=str(existing.id), user=user)
    if currency not in {"CHF", "EUR"}:
        raise SupplySourceRunError("Für den neuen Lieferanten bitte die Einkaufswährung auswählen.")
    try:
        kurs = Decimal(rate.strip().replace(",", "."))
        aufschlag = parse_aufschlag_percent(markup)
    except (InvalidOperation, SupplySourceRunError) as exc:
        raise SupplySourceRunError(
            "Für den neuen Lieferanten Kurs und Aufschlag als Zahlen angeben."
        ) from exc
    if not kurs.is_finite() or kurs <= 0 or kurs >= Decimal(10000):
        raise SupplySourceRunError("Kurs muss grösser als 0 und kleiner als 10000 sein.")
    if not aufschlag.is_finite() or not Decimal(0) <= aufschlag < Decimal(100):
        raise SupplySourceRunError(
            "Aufschlag muss zwischen 0 und 10000 Prozent liegen (10000 ausgeschlossen)."
        )
    if kurs != kurs.quantize(Decimal("0.000001")):
        raise SupplySourceRunError("Kurs darf höchstens sechs Nachkommastellen haben.")
    if aufschlag != aufschlag.quantize(Decimal("0.0001")):
        raise SupplySourceRunError("Aufschlag darf höchstens zwei Nachkommastellen haben.")
    if currency == "CHF" and kurs != 1:
        raise SupplySourceRunError("Für CHF muss der Kurs 1 sein.")
    client = weclapp_client_for(db, str(user["oid"]))
    try:
        party = client.get(f"/party/id/{party_id}")
    except WeclappError as exc:
        raise map_weclapp_error(exc) from exc
    option = supplier_option(party) if isinstance(party, dict) else None
    if option is None or str(party.get("id")) != party_id:
        raise SupplySourceRunError(
            "Der gewählte Lieferant ist in weclapp nicht mehr aktiv oder lesbar."
        )
    # Concurrent first uses preserve the settings saved by the first transaction.
    new_id = db.scalar(
        insert(Supplier)
        .values(
            supplier_number=option["number"],
            weclapp_party_id=party_id,
            name=option["name"],
            einkaufswaehrung=currency,
            default_kurs=kurs,
            default_aufschlag=aufschlag,
            default_verkaufswaehrung="CHF",
            is_active=True,
        )
        .on_conflict_do_nothing()
        .returning(Supplier.id)
    )
    supplier = (
        db.get(Supplier, new_id)
        if new_id
        else db.scalar(select(Supplier).where(Supplier.weclapp_party_id == party_id))
    )
    if supplier is None:
        raise SupplySourceRunError(
            "Die Lieferantennummer ist in Tools bereits anders zugeordnet. Bitte prüfen."
        )
    if new_id:
        db.add(
            SuppliersAudit(
                entity="supplier",
                entity_id=supplier.id,
                action="created",
                before=None,
                after={
                    "supplier_number": supplier.supplier_number,
                    "weclapp_party_id": party_id,
                    "name": supplier.name,
                    "einkaufswaehrung": currency,
                    "default_kurs": str(kurs),
                    "default_aufschlag": str(aufschlag),
                    "default_verkaufswaehrung": "CHF",
                },
                actor_oid=str(user["oid"]),
                actor_name=str(user.get("name") or user["oid"]),
            )
        )
    return resolve_supplier(db, selection=str(supplier.id), user=user)
