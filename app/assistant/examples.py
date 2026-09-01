"""Example questions shown as the assistant input placeholder.

One is picked at random in the browser on each page load. Keep these
answerable with the catalogue tools (counts, filters, sorts, groups,
datenstand). Do not include known refusals (VPE numeric, column-to-column,
missing fields such as Lieferzeit). Swiss spelling: ss, never ß.
"""

from __future__ import annotations

EXAMPLE_QUESTIONS: tuple[str, ...] = (
    "Wie viele Artikel gibt es?",
    "Wie aktuell sind die Daten und wie viele Artikel sind drin?",
    "Wie viele Artikel haben wir pro Hauptgruppe?",
    "Welche Artikel von Dural wiegen mehr als 2 kg?",
    "Zeig mir alle eloxierten Artikel",
    "Was sind die teuersten Artikel bei den Duschsystemen?",
    "Wieviele Balkonwinkelprofile sind länger als 50 cm?",
    "Welche Artikel in der Hauptgruppe Profile sind aus Messing?",
    "Artikel die im Shop aktiv sind aber in weclapp nicht aktiv",
    "Welche Artikel von Dural haben keinen Einkaufspreis?",
    "Wie viele Artikel werden in Stück verkauft?",
    "Was sind die schwersten Matten?",
    "Welche Untergruppen gibt es bei den Profilen?",
    "Welche aktiven Dural-Artikel kosten mehr als 50 Euro und sind im Shop verfügbar?",
    "Zeig die günstigsten silber eloxierten Balkonprofile",
    "Welche Artikel haben keine EAN-Nummer?",
    "Welche Mengeneinheiten kommen vor?",
    "Welche Artikel sind inaktiv?",
)
