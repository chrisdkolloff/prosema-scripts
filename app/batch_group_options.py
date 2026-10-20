"""Resolve registration group attributes against the current weclapp catalogue.

Only group attributes are refreshed; approved article content stays unchanged.
The registry supplies names/codes, never weclapp's selectable-value IDs.
"""

from __future__ import annotations

import copy
from typing import Any

from core.article_payload import LIST_CUSTOM_ATTRS
from scripts.weclapp.article_import import _split_group_label


class GroupOptions:
    def __init__(self, definitions: list[dict[str, Any]], schema: dict[str, Any]):
        if any(not isinstance(definition, dict) for definition in definitions):
            raise ValueError("weclapp-Auswahlkatalog ist ungültig")
        self.definitions: dict[str, dict[str, Any]] = {}
        for label in LIST_CUSTOM_ATTRS.values():
            matches = [d for d in definitions if d.get("label") == label]
            if len(matches) != 1:
                raise ValueError(f"weclapp-Auswahlfeld nicht eindeutig gefunden: {label}")
            definition = matches[0]
            if (
                not definition.get("id")
                or definition.get("attributeType") != "LIST"
                or definition.get("active") is False
                or definition.get("readOnly") is True
                or not isinstance(definition.get("selectableValues"), list)
            ):
                raise ValueError(f"weclapp-Auswahlfeld nicht beschreibbar: {label}")
            if any(not isinstance(option, dict) for option in definition["selectableValues"]):
                raise ValueError(f"weclapp-Auswahlwerte sind ungültig: {label}")
            self.definitions[label] = definition
        # Remove historic IDs as well when a definition has been recreated.
        historic = (schema.get("lookups") or {}).get("customAttributes") or []
        self.group_attribute_ids = {
            str(d["id"])
            for d in [*historic, *definitions]
            if d.get("label") in LIST_CUSTOM_ATTRS.values() and d.get("id")
        }

    def _option_id(self, label: str, value: str) -> str:
        name, code = _split_group_label(value)
        matches: set[str] = set()
        for option in self.definitions[label]["selectableValues"]:
            option_name, option_code = _split_group_label(str(option.get("value") or ""))
            if (
                option_name.casefold() == name.casefold()
                and (option_code is None or code == option_code)
                and option.get("id")
            ):
                matches.add(str(option["id"]))
        if len(matches) != 1:
            raise ValueError(
                f"weclapp-Auswahlwert fehlt oder ist mehrdeutig: {label} / {value}. "
                "Gruppen zuerst in der Gruppenverwaltung auf Tools pflegen und "
                "anschliessend die weclapp-Auswahllisten abgleichen."
            )
        return matches.pop()

    def refresh(self, payload: dict[str, Any], values: dict[str, str]) -> dict[str, Any]:
        out = copy.deepcopy(payload)
        attrs = [
            attr
            for attr in out.get("customAttributes", [])
            if str(attr.get("attributeDefinitionId")) not in self.group_attribute_ids
        ]
        for column, label in LIST_CUSTOM_ATTRS.items():
            value = values.get(column, "").strip()
            if not value:
                raise ValueError(f"Gruppenzuordnung fehlt: {column}")
            attrs.append(
                {
                    "attributeDefinitionId": str(self.definitions[label]["id"]),
                    "selectedValueId": self._option_id(label, value),
                }
            )
        out["customAttributes"] = attrs
        return out
