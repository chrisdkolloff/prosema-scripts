# Unit resolution discovery

Generated `2026-09-04T10:43:21.580734+00:00`. Read-only: GET `/unit`, GET `/article` (id/number/name/unitId), SQL mirror.
No writes. Frozen export tables not queried.

## U1. Full unit list

GET `/unit` returned **12** records.
Field union: createdDate, description, id, lastModifiedDate, name, timeUnitAmount, version

| id | name | other fields |
|---|---|---|
| `4302` | `Btl.` | `createdDate`=1780561418346, `description`='Beutel', `lastModifiedDate`=1782983790930, `version`='5' |
| `3564` | `g` | `createdDate`=1780492465210, `description`='Gramm', `lastModifiedDate`=1780492465210, `version`='0' |
| `3567` | `h` | `createdDate`=1780492465220, `description`='Stunde', `lastModifiedDate`=1780492465220, `timeUnitAmount`=3600, `version`='0' |
| `4303` | `Karton` | `createdDate`=1780561442308, `description`='Karton', `lastModifiedDate`=1782808767925, `version`='3' |
| `3563` | `kg` | `createdDate`=1780492465205, `description`='Kilogramm', `lastModifiedDate`=1780492465205, `version`='0' |
| `3565` | `l` | `createdDate`=1780492465214, `description`='Liter', `lastModifiedDate`=1780492465214, `version`='0' |
| `4259` | `lfm` | `createdDate`=1780554592901, `description`='Laufmeter', `lastModifiedDate`=1782808836599, `version`='2' |
| `6526` | `mm` | `createdDate`=1782808643959, `description`='Millimeter', `lastModifiedDate`=1782808643959, `version`='0' |
| `4305` | `Paar` | `createdDate`=1780561593450, `description`='Paar', `lastModifiedDate`=1782808689482, `version`='1' |
| `4304` | `qm` | `createdDate`=1780561493719, `description`='Quadratmeter', `lastModifiedDate`=1782808737490, `version`='1' |
| `393767` | `Sack` | `createdDate`=1787734047880, `description`='Sack', `lastModifiedDate`=1787734047880, `version`='0' |
| `3566` | `Stk.` | `createdDate`=1780492465217, `description`='Stück', `lastModifiedDate`=1782983779312, `version`='2' |

### Raw JSON (two records)

#### sample 1 id `3563`

```json
{
  "id": "3563",
  "version": "0",
  "createdDate": 1780492465205,
  "description": "Kilogramm",
  "lastModifiedDate": 1780492465205,
  "name": "kg"
}
```

#### sample 2 id `3564`

```json
{
  "id": "3564",
  "version": "0",
  "createdDate": 1780492465210,
  "description": "Gramm",
  "lastModifiedDate": 1780492465210,
  "name": "g"
}
```

## Mirror sizes (context)

`weclapp_articles`: 4174 total, 4174 with `missing_since` null (prompt cited 4174).
`weclapp_supply_sources`: 4227 total, 4227 present (prompt cited 4227).
`weclapp_supply_source_links`: 4119.
Article mirror has **no `unit_id` column**. Article-side counts below come from live GET `/article`.

## U2. Units actually used

Live GET `/article`: **4174** records (id-only properties requested; if weclapp ignored `properties`, bodies may be full).
Articles with empty `unitId`: 0.
Present supply sources with empty `unit_id`: 0.

| unitId | name | article count | supply-source count (present) |
|---|---|---:|---:|
| `3566` | Stk. | 2271 | 2286 |
| `4259` | lfm | 1793 | 1820 |
| `4304` | qm | 63 | 63 |
| `4302` | Btl. | 33 | 47 |
| `4303` | Karton | 9 | 9 |
| `6526` | mm | 3 | 0 |
| `393767` | Sack | 1 | 1 |
| `4305` | Paar | 1 | 1 |

Units in `/unit` with **zero** article and zero present-SS use: **4** — `kg` (`3563`), `g` (`3564`), `l` (`3565`), `h` (`3567`).

## U3. Article vs supply-source disagreement

Links compared: 4119.
Both units present and **equal**: 4119.
Both present and **differ**: **0**.
Link article id not in live GET: 0.
Empty SS unit on a link: 0. Empty article unitId: 0.

No disagreements among links where both unit ids are present.

## U4. Per supplier (present supply sources)

| supplier_number | name | default_unit_id | SS n | distinct units | single-unit? |
|---|---|---|---:|---:|---|
| `10000` | DURAL GmbH | `None` | 4214 | 6 | no |
| `10061` | Hülsenfabrik Lenzhard | `None` | 7 | 1 | yes |
| `10739` | Axpel one for all AG | `None` | 5 | 1 | yes |
| `10055` | JURALITH Baustoff GmbH | `None` | 1 | 1 | yes |
| `19998` | Apply-Test | `3566` | 0 | 0 | no |

### supplier `10000` (4214 present SS)

| unitId | name | count | share |
|---|---|---:|---:|
| `3566` | Stk. (3566) | 2274 | 54.0% |
| `4259` | lfm (4259) | 1820 | 43.2% |
| `4304` | qm (4304) | 63 | 1.5% |
| `4302` | Btl. (4302) | 47 | 1.1% |
| `4303` | Karton (4303) | 9 | 0.2% |
| `4305` | Paar (4305) | 1 | 0.0% |

Single-unit supplier: **no**.

### supplier `10055` (1 present SS)

| unitId | name | count | share |
|---|---|---:|---:|
| `393767` | Sack (393767) | 1 | 100.0% |

Single-unit supplier: **yes**.

### supplier `10061` (7 present SS)

| unitId | name | count | share |
|---|---|---:|---:|
| `3566` | Stk. (3566) | 7 | 100.0% |

Single-unit supplier: **yes**.

### supplier `10739` (5 present SS)

| unitId | name | count | share |
|---|---|---:|---:|
| `3566` | Stk. (3566) | 5 | 100.0% |

Single-unit supplier: **yes**.

## U5. Name shape

Exact `name` strings:

- `Btl.`
- `g`
- `h`
- `Karton`
- `kg`
- `l`
- `lfm`
- `mm`
- `Paar`
- `qm`
- `Sack`
- `Stk.`

Non-id/name fields present on unit records: ['createdDate', 'description', 'lastModifiedDate', 'timeUnitAmount', 'version'].
Separate short name / description field: **no**, unless listed above.
Duplicate names across different ids: none (alias table would need this if matching on name).

Language/abbreviation: listed verbatim above. Looks abbreviated/German mix from the strings themselves (heuristic germanish=True).

## U6. Other unit-ish fields on articleSupplySource

From `scripts/discovery/out/supply_source_read.md` A2, the GET field union is:

`articleNumber`, `articlePrices`, `createdDate`, `customAttributes`, `description`, `dropshippingPossible`, `ean`, `fixedPurchaseQuantity`, `id`, `ignoreInDropshippingAutomation`, `lastModifiedDate`, `matchCode`, `minimumPurchaseQuantity`, `name`, `procurementLeadDays`, `shortDescription1`, `supplierId`, `taxRateType`, `unitId`, `version`

Unit-ish keys **in** that union: ['unitId'].
Unit-ish keys **not** in that union: ['unit', 'unitName', 'supplierUnitId', 'supplierUnit', 'purchaseUnitId', 'packagingUnit', 'packagingUnitId', 'quantityUnitId', 'articleAlternativeQuantities'].
`unitId` is present 4227/4227 on that discovery snapshot.
`minimumPurchaseQuantity` / `fixedPurchaseQuantity` are quantities, not a unit (present 13/4227 each). `customAttributes` is a list on every SS — contents not re-scanned here (earlier read discovery did not flag a unit attribute).
CSV also has `Gebindemenge` / `Mindestbestellmenge`; those map to purchase quantities, not `unitId`.

## U7. CSV import template

File: `data/SupplySourcesWeclapp DemoImportfile_de (28.10.2024)(1).csv`
Exists: True.
Column **Artikel-Mengeneinheit** is present (1-based index 15, Excel letter O in the A2 header map).
Data rows: 0.
Distinct values in that column (empty string counted):

| value | count | matches a weclapp unit `name`? | matches a weclapp unit `id`? |
|---|---:|---|---|

Internal export maps this column from article `unitId` → unit **name** (`scripts/export/generate_weclapp_import.py`: `Artikel-Mengeneinheit` ← `Basiseinheitencode`; `scripts/weclapp/master_columns.py` `unit_name()`). A produced Dural CSV uses values like `lfm` / `Stk.` — names, not ids.

Produced Dural CSV `bezugsquellen_10000_2026-08-25_2020.csv`: 4034 rows. Distinct Artikel-Mengeneinheit:

| value | count | matches unit name? |
|---|---:|---|
| `Stk.` | 2221 | yes |
| `lfm` | 1746 | yes |
| `Btl.` | 31 | yes |
| `qm` | 26 | yes |
| `Karton` | 9 | yes |
| `Paar` | 1 | yes |

Wizard expectation is therefore **the unit `name`**, not the id. `description` on `/unit` is the long German form (Stück, Laufmeter); the CSV uses `name` (Stk., lfm). No separate code field exists on GET `/unit`.

## U8. Is `unitId` writable on PUT?

B1 (`scripts/discovery/supply_source_discovery_write.py`) included `unitId` in the one-extra-field PUT vs known-good. Outcome recorded in `supply_source_write.md`: **accepted** status 200. The payload **echoed the existing** `unitId` (`3566`), it did **not** change it to a different unit.
So: sending `unitId` on PUT is not rejected. **Changing** `unitId` on an existing supply source is **untested** (no live write in this discovery).

## Bridges the data supports

**A. Dropdown of weclapp units.** Supported. Catalogue is small (12 units). Dennis would see the exact `name` strings from U5. Ids stay in the app; template text can be the name. Unused catalogue entries can be hidden or shown — your call.
**B. Free-text matched to names, plus alias table.** Weakly supported as the *primary* path. Names are unique in this tenant (no duplicate names). CSV already uses names (`lfm`, `Stk.`). An alias table is only needed if supplier files use other spellings (Stk vs Stk. vs Stück) — **not evidenced in weclapp's own list**, only in how humans type. Your call whether aliases are worth it before seeing a real template file.
**C. Per-supplier default with per-row override.** Viable as a *default* only for single-unit suppliers: ['10061', '10739', '10055']. Not viable as the only mechanism: seeded `default_unit_id` is NULL on all four, and U4 shows mixed units wherever a supplier is not single-unit. Override (A or B per row) is still required for mixed suppliers.

### Decisions that are yours

- Hide unused `/unit` catalogue rows in a dropdown, or show the full list.
- Whether create copies the **article** unit when SS and article always agree (see U3).
- Whether to seed `suppliers.default_unit_id` from the modal SS unit (only if U4 is single-unit).
- Alias table now vs after the first messy Excel.
- Live PUT that *changes* `unitId` on 999.999.001 (U8 left untested).

