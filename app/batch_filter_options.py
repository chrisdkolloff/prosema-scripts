"""Read current batch search choices with the signed-in user's weclapp token."""

from app.supply_source_suppliers import PROPERTIES, supplier_option
from app.weclapp import weclapp_client_for


def live_filter_options(db, oid: str) -> dict:
    client = weclapp_client_for(db, oid)
    definitions = list(client.iter_pages("customAttributeDefinition"))
    matches = [
        d
        for d in definitions
        if d.get("label") == "Hauptwarengruppe (Auswahl)" and d.get("active") is not False
    ]
    if len(matches) != 1:
        raise ValueError("Hauptgruppen-Auswahl in weclapp nicht eindeutig gefunden.")
    main = [
        str(v.get("value") or "").strip()
        for v in matches[0].get("selectableValues", [])
        if v.get("active") is not False
    ]
    categories = [str(c.get("name") or "").strip() for c in client.iter_pages("articleCategory")]
    suppliers = []
    for party in client.iter_pages(
        "party",
        params={
            "supplier-eq": "true",
            "supplierActive-eq": "true",
            "properties": PROPERTIES,
        },
    ):
        option = supplier_option(party)
        if option:
            suppliers.append(option)
    return {
        "hauptgruppen": sorted(set(filter(None, main)), key=str.casefold),
        "kategorien": sorted(set(filter(None, categories)), key=str.casefold),
        "lieferanten": sorted(suppliers, key=lambda s: (s["name"].casefold(), s["number"])),
    }
