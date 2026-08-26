# Runbook: sales articles created from Lieferantenartikelnummer

**Date:** 2026-08-25  
**Uploaded run:** `5cc06360-74df-4bd0-a4d8-fba0b9acfca1`  
**File:** `bezugsquellen_10000_2026-08-25_2020.csv` (4 034 included rows)

## What happened

Column W (`Verkaufsartikel-Nummer`) was left empty on every exported row. The weclapp Bezugsquellen wizard did not reject those rows. Its failure mode for a missing sales-article link is to **invent a new sales article per row**, numbered from D (`Lieferantenartikelnummer`), and attach it to the **same** supply source as the real PROSEMA article.

This is the second time an unstated weclapp behaviour has cost a run (the first was empty-clears-discounts). For any column that touches a relationship between records, “optional and left empty” has to be tested, not assumed. Nothing in the weclapp documentation states that a missing W creates an article.

## Diagnosis

- Real articles were updated correctly: EK prices and both discounts landed as intended.
- The match key `(D, F)` held. No supply sources were duplicated.
- Junk articles were created **alongside**, not instead of, the real ones.
- Each affected supply source is now a **single shared record** linked to two sales articles.

`Verkaufsartikel-Währung` = `EUR` is correct for PROSEMA sales articles. The CHF figure in the editor is an internal planning number, not the weclapp sales currency. Rev-2 open item §7.2 is closed.

## How many

| Set | Count |
|---|---|
| Included rows in the uploaded export | 4 034 |
| Collision: D already equals a PROSEMA article number in this run | 4 (3 included) |
| Candidates for junk-article cleanup | **4 031** |

The candidate list is `docs/incidents/2026-08-25-verkaufsartikel-aus-d/junk-sales-articles.txt`. That file is the record of what is to be removed.

**Do not delete** numbers in `docs/incidents/2026-08-25-verkaufsartikel-aus-d/collision-do-not-delete.txt`:

| Number | Why |
|---|---|
| `020.010.0360` | D = existing PROSEMA article (included) |
| `020.020.5710` | D = existing PROSEMA article (included) |
| `060.010.800` | D = existing PROSEMA article (included; 3-digit running part) |
| `999.999.001` | Test article; **not** in the uploaded set (`included=false`) |

Before deleting, cross-check the 4 031 against weclapp articles **created in the import window**. Keep only the intersection. Anything created in that window but not on the list belongs to someone else.

## Cleanup — shared supply source

The supply source is shared, not duplicated. Deleting a junk article operates on a record the real article still depends on.

| weclapp behaviour | Result |
|---|---|
| Removes only the junk article’s link | Correct — supply source survives, real link intact |
| Refuses to delete while a supply source is attached | Fine — deactivate instead (prefix name `ZZZ-GELOESCHT-`) |
| Cascades and deletes the shared supply source | **Destroys the real link and the data just imported** |

The third cannot be ruled out by reasoning.

### Cleanup performed 2026-08-25 21:46–22:06

weclapp **removes only the junk article’s link**. The shared supply source survives.

**Test delete:** `03002000` (weclapp id `363536`), created 20:22:38. Real article `010.010.0010` kept supply source `162478` with EK 73.32, D1 50 %, D2 15 %, `Primäre Bezugsquelle` unchanged.

**Batch:** 4 030 remaining articles created after 20:20 that were on the junk list (intersection was exact: 0 extras). All 4 030 deleted. Log: `deletion-log.jsonl`. None of the four collision numbers were touched.

**Spot-check** (five real articles across the batch): supply source present, EK and both discounts match the export, primary flag unchanged, exactly one sales article linked, junk number gone.

## Sequence after cleanup

Cleanup → verify → **fresh pull** → corrected export.

While junk links exist, a pull materialises two `export_row` records for the shared supply source. The duplicate check on `(supplier_article_number, supplier_number)` blocks the download. Any run created before cleanup completes is unusable — discard those drafts rather than editing around the duplicates.

## Export rules (after the fix)

- **W** (`Verkaufsartikel-Nummer`) always carries the PROSEMA article number (`export_row.article_number`). Empty W is a hard error in the validation gate and an assertion in the serialiser.
- **Y** (`Verkaufsartikel-Währung`) is a run setting, default **EUR**. EUR is correct and deliberate, not a placeholder.
- **R** (`Preis-Eintritt`) is a run setting, required, `dd.mm.yyyy`. No silent “today” — the user picks a date.
- **V** stays empty. Do not set `ja` to “make the link work”. If a corrected export with W populated still creates articles, set V to `nein` and retest on `999.999.001` only, not on a batch.

## Remaining open items

- **§7.3** — does R create a price-validity record with X empty, or is it inert? Test on `999.999.001`: export twice with different `price_entry_date` values and inspect price history. Not blocking.
- **§7.4** (Z, Vertriebsweg) remains phase 2, relevant only when creating supply sources rather than updating them.
- **§7.2** (Y currency) is closed.

## Verification of the corrected export

On `999.999.001` first, then three real articles, then the batch:

- No new sales article created
- Existing supply source updated in place
- Exactly one sales article linked
- EK price and both discounts match the export
- Sales currency unchanged (`EUR`)
- `Primäre Bezugsquelle` unchanged
