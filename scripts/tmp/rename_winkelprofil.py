"""Rename Abschlussprofil → Winkelprofil in Untergruppe Abschlussprofile Winkel.

Dry-run (default):

    PYTHONPATH=. python scripts/tmp/rename_winkelprofil.py

Write to weclapp:

    PYTHONPATH=. python scripts/tmp/rename_winkelprofil.py --apply

Strip ', Artikelnummer: …' from Langtext of every article:

    PYTHONPATH=. python scripts/tmp/rename_winkelprofil.py --artikelnummer-all
    PYTHONPATH=. python scripts/tmp/rename_winkelprofil.py --artikelnummer-all --apply

Remove [ and ] from Grundmaterial on every article:

    PYTHONPATH=. python scripts/tmp/rename_winkelprofil.py --grundmaterial
    PYTHONPATH=. python scripts/tmp/rename_winkelprofil.py --grundmaterial --apply

Normalize aussenecke/innenecke → Aussenecke/Innenecke in name, Langtext, Kurzbeschreibung:

    PYTHONPATH=. python scripts/tmp/rename_winkelprofil.py --ecken
    PYTHONPATH=. python scripts/tmp/rename_winkelprofil.py --ecken --apply

Replace winkel-abschlussprofil → Winkelprofil in name, Langtext, Kurzbeschreibung:

    PYTHONPATH=. python scripts/tmp/rename_winkelprofil.py --winkel-abschluss
    PYTHONPATH=. python scripts/tmp/rename_winkelprofil.py --winkel-abschluss --apply

Normalize verbinder → Verbinder in name, Langtext, Kurzbeschreibung:

    PYTHONPATH=. python scripts/tmp/rename_winkelprofil.py --verbinder
    PYTHONPATH=. python scripts/tmp/rename_winkelprofil.py --verbinder --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.weclapp.client import WeclappClient
from scripts.weclapp.config import load_config

UNTER = "Abschlussprofile Winkel"
FIELDS = ("name", "longText", "shortDescription1")
ARTIKELNUMMER_TAIL = re.compile(r",\s*Artikelnummer:\s*[^\s<]+")
AUSSENECKE = re.compile(r"aussenecke", re.IGNORECASE)
INNENECKE = re.compile(r"innenecke", re.IGNORECASE)
WINKEL_ABSCHLUSS = re.compile(r"winkel-abschlussprofil", re.IGNORECASE)
VERBINDER = re.compile(
    r"(?<![A-Za-zÄÖÜäöüß-])verbinder(?![A-Za-zÄÖÜäöüß-])",
    re.IGNORECASE,
)


def strip_artikelnummer(text: str) -> str:
    return ARTIKELNUMMER_TAIL.sub("", text)


def strip_grundmaterial_brackets(text: str) -> str:
    return text.replace("[", "").replace("]", "")


def normalize_ecken(text: str) -> str:
    return INNENECKE.sub("Innenecke", AUSSENECKE.sub("Aussenecke", text))


def replace_winkel_abschluss(text: str) -> str:
    return WINKEL_ABSCHLUSS.sub("Winkelprofil", text)


def normalize_verbinder(text: str) -> str:
    return VERBINDER.sub("Verbinder", text)


def grundmaterial_attr_id(client: WeclappClient) -> str:
    for definition in client.iter_pages("customAttributeDefinition"):
        label = str(definition.get("label") or definition.get("attributeKey") or "")
        if label.strip() == "Grundmaterial":
            return str(definition["id"])
    raise SystemExit("Custom-Attribut Grundmaterial nicht gefunden")


def rewrite(text: str, *, field: str) -> str:
    text = text.replace("Winkel-Abschlussprofil", "Winkelprofil").replace(
        "Abschlussprofil", "Winkelprofil"
    )
    if field == "longText":
        text = strip_artikelnummer(text)
    return text


def attr_text(attr: dict) -> str:
    parts = [
        attr.get("stringValue"),
        attr.get("selectedValue"),
        attr.get("displayValue"),
    ]
    return " ".join(str(p) for p in parts if p)


def in_untergruppe(article: dict, cat_ids: set[str]) -> bool:
    if str(article.get("articleCategoryId") or "") in cat_ids:
        return True
    return any(UNTER in attr_text(a) for a in (article.get("customAttributes") or []))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--artikelnummer-all",
        action="store_true",
        help="Nur Langtext: ', Artikelnummer: …' in allen Artikeln entfernen.",
    )
    parser.add_argument(
        "--grundmaterial",
        action="store_true",
        help="Eckige Klammern aus Grundmaterial in allen Artikeln entfernen.",
    )
    parser.add_argument(
        "--ecken",
        action="store_true",
        help="aussenecke/innenecke → Aussenecke/Innenecke in Name, Langtext, Kurzbeschreibung.",
    )
    parser.add_argument(
        "--winkel-abschluss",
        action="store_true",
        help="winkel-abschlussprofil → Winkelprofil in Name, Langtext, Kurzbeschreibung.",
    )
    parser.add_argument(
        "--verbinder",
        action="store_true",
        help="verbinder → Verbinder in Name, Langtext, Kurzbeschreibung.",
    )
    args = parser.parse_args()

    client = WeclappClient(load_config())
    cat_ids: set[str] = set()
    gm_id = ""
    catalog_wide = (
        args.artikelnummer_all
        or args.grundmaterial
        or args.ecken
        or args.winkel_abschluss
        or args.verbinder
    )
    if args.grundmaterial:
        gm_id = grundmaterial_attr_id(client)
    if not catalog_wide:
        cats = list(
            client.iter_pages(
                "articleCategory", params={"properties": "id,name,parentCategoryId"}
            )
        )
        cat_ids = {str(c["id"]) for c in cats if (c.get("name") or "").strip() == UNTER}
        if not cat_ids:
            raise SystemExit(f"Kategorie {UNTER!r} nicht gefunden")

    changed = skipped = 0
    for art in client.iter_pages("article"):
        if not catalog_wide and not in_untergruppe(art, cat_ids):
            continue
        payload: dict = {}
        preview: dict[str, tuple[str, str]] = {}
        if args.grundmaterial:
            attrs = [dict(a) for a in (art.get("customAttributes") or []) if isinstance(a, dict)]
            for attr in attrs:
                if str(attr.get("attributeDefinitionId") or "") != gm_id:
                    continue
                val = attr.get("stringValue")
                if not isinstance(val, str) or "[" not in val and "]" not in val:
                    continue
                new = strip_grundmaterial_brackets(val)
                if new == val:
                    continue
                attr["stringValue"] = new
                payload["customAttributes"] = attrs
                preview["Grundmaterial"] = (val, new)
                break
        elif args.winkel_abschluss:
            for field in FIELDS:
                val = art.get(field)
                if not isinstance(val, str):
                    continue
                new = replace_winkel_abschluss(val)
                if new != val:
                    payload[field] = new
                    preview[field] = (val, new)
        elif args.verbinder:
            for field in FIELDS:
                val = art.get(field)
                if not isinstance(val, str):
                    continue
                new = normalize_verbinder(val)
                if new != val:
                    payload[field] = new
                    preview[field] = (val, new)
        elif args.ecken:
            for field in FIELDS:
                val = art.get(field)
                if not isinstance(val, str):
                    continue
                new = normalize_ecken(val)
                if new != val:
                    payload[field] = new
                    preview[field] = (val, new)
        elif args.artikelnummer_all:
            val = art.get("longText")
            if isinstance(val, str):
                new = strip_artikelnummer(val)
                if new != val:
                    payload["longText"] = new
                    preview["longText"] = (val, new)
        else:
            for field in FIELDS:
                val = art.get(field)
                if not isinstance(val, str):
                    continue
                new = rewrite(val, field=field)
                if new != val:
                    payload[field] = new
                    preview[field] = (val, new)
        if not payload:
            skipped += 1
            continue
        changed += 1
        print(art.get("articleNumber"))
        for field, (old, new) in preview.items():
            print(f"  {field}:")
            print(f"    alt: {old!r}")
            print(f"    neu: {new!r}")
        if args.apply:
            body = dict(payload)
            if art.get("version") is not None:
                body["version"] = art["version"]
            client.put(
                f"/article/id/{art['id']}",
                params={"ignoreMissingProperties": "true"},
                json=body,
            )

    print(
        f"\nZu ändern: {changed}  ohne Treffer: {skipped}  "
        f"APPLY={args.apply}  artikelnummer_all={args.artikelnummer_all}  "
        f"grundmaterial={args.grundmaterial}  ecken={args.ecken}  "
        f"winkel_abschluss={args.winkel_abschluss}  verbinder={args.verbinder}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
