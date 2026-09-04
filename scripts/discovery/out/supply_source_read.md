# articleSupplySource discovery — Phase A (read-only)

Tenant: `prosema` (token not printed).
Client base URL used for GETs: tenant `prosema` via WeclappClient.

## Timing pulls (A8 / A10)

- customAttributeDefinition: **29** records, **0.33s**, **1** GET requests
- articleSupplySource (full unfiltered paged pull): **4227** records, **2.35s** wall-clock, **5** GET requests
- article: **4174** records, **5.85s**, **5** GET requests

- party GET by id for 4 distinct supplierIds: **0.43s**, **4** GET requests

- currency: **17** records, **0.17s**, **1** GET

### Article native keys (union) — needed because SS has no articleId

`active`, `applyCashDiscount`, `articleAlternativeQuantities`, `articleCalculationPrices`, `articleCategoryId`, `articleHeight`, `articleImages`, `articleLength`, `articleNetWeight`, `articleNumber`, `articlePrices`, `articleType`, `articleWidth`, `availableForSalesChannels`, `availableInSale`, `averageDeliveryTime`, `batchNumberRequired`, `billOfMaterialPartDeliveryPossible`, `commissionRate`, `createdDate`, `customAttributes`, `customerArticleNumbers`, `customsTariffNumberId`, `defaultLoadingEquipmentIdentifierId`, `defaultPriceCalculationType`, `defaultStoragePlaces`, `defineIndividualTaskTemplates`, `description`, `ean`, `fixedPurchaseQuantity`, `id`, `lastModifiedDate`, `longText`, `lowLevelCode`, `manufacturerId`, `marginCalculationPriceType`, `matchCode`, `minimumPurchaseQuantity`, `name`, `packagingUnitBaseArticleId`, `primarySupplySourceId`, `procurementLeadDays`, `productionArticle`, `productionBillOfMaterialItems`, `productionConfigurationRule`, `purchaseCostCenterId`, `quantityConversions`, `ratingId`, `salesBillOfMaterialItems`, `salesCostCenterId`, `serialNumberRequired`, `shortDescription1`, `shortDescription2`, `showOnDeliveryNote`, `statusId`, `supplySources`, `tags`, `taxRateType`, `unitId`, `useAvailableForSalesChannels`, `useSalesBillOfMaterialItemPrices`, `useSalesBillOfMaterialItemPricesForPurchase`, `useSalesBillOfMaterialSubitemCosts`, `version`

- articles with primarySupplySourceId: **4119/4174**
- articles with non-empty supplySources list: **4119/4174**
Sample `supplySources` + `primarySupplySourceId` from one article:

```json
{
  "articleNumber": "020.020.0010",
  "id": "106693",
  "primarySupplySourceId": "4418",
  "supplySources": [
    {
      "id": "166830",
      "version": "2",
      "articleSupplySourceId": "4418",
      "createdDate": 1783505330796,
      "lastModifiedDate": 1787682203597,
      "positionNumber": 1
    }
  ]
}
```

Join: **4115** supply sources referenced from ≥1 article; **112** supply sources not referenced by any article (via primarySupplySourceId / supplySources).

First 5 unreferenced SS ids / articleNumber / supplierId:
- `6372` articleNumber `1` supplierId `4406`
- `6375` articleNumber `3003000` supplierId `4406`
- `6378` articleNumber `3003100` supplierId `4406`
- `6381` articleNumber `3003250` supplierId `4406`
- `6384` articleNumber `3010100` supplierId `4406`

## A1. Supplier inventory

**Observed:** `articleSupplySource` has **no** `articleId` and **no** `supplierArticleNumber`. The supplier part number lives in SS.`articleNumber`. Article linkage is on the **article** entity (`primarySupplySourceId`, `supplySources[]`). Distinct-article counts below use that join.

| supplierNumber | party id | party name | supply sources | distinct articles |
|---|---|---|---:|---:|
| 10000 | `4406` | DURAL GmbH | 4214 | 4107 |
| 10061 | `197093` | Hülsenfabrik Lenzhard | 7 | 6 |
| 10739 | `394644` | Axpel one for all AG | 5 | 5 |
| 10055 | `178825` | JURALITH Baustoff GmbH | 1 | 1 |

Distinct suppliers (by supplierId): **4**

## A2. Supply-source field shape

### Union of keys across all supply sources

`articleNumber`, `articlePrices`, `createdDate`, `customAttributes`, `description`, `dropshippingPossible`, `ean`, `fixedPurchaseQuantity`, `id`, `ignoreInDropshippingAutomation`, `lastModifiedDate`, `matchCode`, `minimumPurchaseQuantity`, `name`, `procurementLeadDays`, `shortDescription1`, `supplierId`, `taxRateType`, `unitId`, `version`

### Key presence / types across all records

- `articleNumber`: present 4227/4227; types: str×4227
- `articlePrices`: present 4227/4227; types: list×4227
- `createdDate`: present 4227/4227; types: int×4227
- `customAttributes`: present 4227/4227; types: list×4227
- `description`: present 13/4227; types: str×13
- `dropshippingPossible`: present 4227/4227; types: bool×4227
- `ean`: present 17/4227; types: str×17
- `fixedPurchaseQuantity`: present 13/4227; types: str×13
- `id`: present 4227/4227; types: str×4227
- `ignoreInDropshippingAutomation`: present 4227/4227; types: bool×4227
- `lastModifiedDate`: present 4227/4227; types: int×4227
- `matchCode`: present 4178/4227; types: str×4178
- `minimumPurchaseQuantity`: present 13/4227; types: str×13
- `name`: present 4227/4227; types: str×4227
- `procurementLeadDays`: present 13/4227; types: int×13
- `shortDescription1`: present 29/4227; types: str×29
- `supplierId`: present 4227/4227; types: str×4227
- `taxRateType`: present 4227/4227; types: str×4227
- `unitId`: present 4227/4227; types: str×4227
- `version`: present 4227/4227; types: str×4227

### Raw JSON — supplier 10000 (n=3)

Key/type/null for these 3:

- `articleNumber`: present 3/3; types: str×3
- `articlePrices`: present 3/3; types: list×3
- `createdDate`: present 3/3; types: int×3
- `customAttributes`: present 3/3; types: list×3
- `dropshippingPossible`: present 3/3; types: bool×3
- `ean`: present 1/3; types: str×1
- `id`: present 3/3; types: str×3
- `ignoreInDropshippingAutomation`: present 3/3; types: bool×3
- `lastModifiedDate`: present 3/3; types: int×3
- `matchCode`: present 1/3; types: str×1
- `name`: present 3/3; types: str×3
- `supplierId`: present 3/3; types: str×3
- `taxRateType`: present 3/3; types: str×3
- `unitId`: present 3/3; types: str×3
- `version`: present 3/3; types: str×3

#### sample 1 (id `4418`)

```json
{
  "id": "4418",
  "version": "6",
  "articleNumber": "09018030",
  "articlePrices": [
    {
      "id": "367429",
      "version": "0",
      "createdDate": 1787682159175,
      "currencyId": "261",
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1787682159175,
      "price": "14.88",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "367430",
          "version": "0",
          "createdDate": 1787682159176,
          "lastModifiedDate": 1787682159176,
          "name": "Grundrabatt · Dural Preisliste 2026-08 · Fliesenprofile · Kat. A · 50%",
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "367431",
          "version": "0",
          "createdDate": 1787682159176,
          "lastModifiedDate": 1787682159176,
          "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. A · 50%",
          "type": "REDUCTION_PERCENT",
          "value": "50"
        }
      ],
      "startDate": 1787608800000
    },
    {
      "id": "184808",
      "version": "1",
      "createdDate": 1786007171799,
      "currencyId": "261",
      "endDate": 1787608799999,
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1787682163957,
      "price": "14.88",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "184809",
          "version": "0",
          "createdDate": 1786007171800,
          "lastModifiedDate": 1786007171800,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "184810",
          "version": "0",
          "createdDate": 1786007171800,
          "lastModifiedDate": 1786007171800,
          "type": "REDUCTION_PERCENT",
          "value": "40"
        }
      ],
      "startDate": 1784066400000
    },
    {
      "id": "6021",
      "version": "2",
      "createdDate": 1782238834258,
      "currencyId": "261",
      "endDate": 1784066399999,
      "lastModifiedByUserId": "4471",
      "lastModifiedDate": 1786007174908,
      "price": "14.88",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "6022",
          "version": "0",
          "createdDate": 1782238834258,
          "lastModifiedDate": 1782238834258,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "6023",
          "version": "0",
          "createdDate": 1782238834259,
          "lastModifiedDate": 1782238834259,
          "type": "REDUCTION_PERCENT",
          "value": "40"
        }
      ]
    }
  ],
  "createdDate": 1780567063628,
  "customAttributes": [],
  "dropshippingPossible": true,
  "ean": "4018448005002",
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1787682163956,
  "matchCode": "DSM 30, 250",
  "name": "Abschlussprofil Messing natur 3 mm 250 cm",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "4259"
}
```

#### sample 2 (id `6372`)

```json
{
  "id": "6372",
  "version": "1",
  "articleNumber": "1",
  "articlePrices": [
    {
      "id": "6967",
      "version": "0",
      "createdDate": 1782886111274,
      "currencyId": "261",
      "lastModifiedByUserId": "3553",
      "lastModifiedDate": 1782886111274,
      "price": "73.32",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "6968",
          "version": "0",
          "createdDate": 1782886111275,
          "lastModifiedDate": 1782886111275,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        }
      ],
      "startDate": 1782424800000
    }
  ],
  "createdDate": 1782482500871,
  "customAttributes": [],
  "dropshippingPossible": true,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1782886111339,
  "name": "NIVOFIX NWS ZANGE 1 ST.",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

#### sample 3 (id `6375`)

```json
{
  "id": "6375",
  "version": "1",
  "articleNumber": "3003000",
  "articlePrices": [
    {
      "id": "6969",
      "version": "0",
      "createdDate": 1782886111276,
      "currencyId": "261",
      "lastModifiedByUserId": "3553",
      "lastModifiedDate": 1782886111276,
      "price": "78.72",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "6970",
          "version": "0",
          "createdDate": 1782886111277,
          "lastModifiedDate": 1782886111277,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        }
      ],
      "startDate": 1782424800000
    }
  ],
  "createdDate": 1782482500874,
  "customAttributes": [],
  "dropshippingPossible": true,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1782886111340,
  "name": "NIVOFIX NWS STARTERSET",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

### Raw JSON — other supplier `10061` (n=3)

Key/type/null for these 3:

- `articleNumber`: present 3/3; types: str×3
- `articlePrices`: present 3/3; types: list×3
- `createdDate`: present 3/3; types: int×3
- `customAttributes`: present 3/3; types: list×3
- `description`: present 3/3; types: str×3
- `dropshippingPossible`: present 3/3; types: bool×3
- `fixedPurchaseQuantity`: present 3/3; types: str×3
- `id`: present 3/3; types: str×3
- `ignoreInDropshippingAutomation`: present 3/3; types: bool×3
- `lastModifiedDate`: present 3/3; types: int×3
- `minimumPurchaseQuantity`: present 3/3; types: str×3
- `name`: present 3/3; types: str×3
- `procurementLeadDays`: present 3/3; types: int×3
- `shortDescription1`: present 3/3; types: str×3
- `supplierId`: present 3/3; types: str×3
- `taxRateType`: present 3/3; types: str×3
- `unitId`: present 3/3; types: str×3
- `version`: present 3/3; types: str×3

#### sample 1 (id `197345`)

```json
{
  "id": "197345",
  "version": "3",
  "articleNumber": "0100.001",
  "articlePrices": [
    {
      "id": "197346",
      "version": "1",
      "createdDate": 1786022449060,
      "currencyId": "265",
      "lastModifiedByUserId": "184074",
      "lastModifiedDate": 1786082459128,
      "price": "3.5",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [],
      "startDate": 1785967200000
    }
  ],
  "createdDate": 1786022449059,
  "customAttributes": [],
  "description": "<p>Kartonhülsen, spiral&nbsp;40 x 3 x 2530 mm beidseitig mit weissen Plastickdeckeln&nbsp;</p>",
  "dropshippingPossible": false,
  "fixedPurchaseQuantity": "100",
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1786084141637,
  "minimumPurchaseQuantity": "100",
  "name": "Kartonhülsen, spiral P10",
  "procurementLeadDays": 21,
  "shortDescription1": "Kartonhülsen 40 x 3 x 2530mm",
  "supplierId": "197093",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}

#### sample 2 (id `197359`)

```json
{
  "id": "197359",
  "version": "4",
  "articleNumber": "0100.002",
  "articlePrices": [
    {
      "id": "197364",
      "version": "1",
      "createdDate": 1786022891910,
      "currencyId": "265",
      "lastModifiedByUserId": "184074",
      "lastModifiedDate": 1786082500449,
      "price": "3.7",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [],
      "startDate": 1785967200000
    }
  ],
  "createdDate": 1786022833160,
  "customAttributes": [],
  "description": "<p>Kartonhülsen, spiral&nbsp;40 x 3 x 3030 mm beidseitig mit weissen Plastickdeckeln&nbsp;</p>",
  "dropshippingPossible": false,
  "fixedPurchaseQuantity": "100",
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1786084184538,
  "minimumPurchaseQuantity": "100",
  "name": "Kartonhülsen, spiral P10",
  "procurementLeadDays": 21,
  "shortDescription1": "Kartonhülsen 40 x 3 x 3030mm",
  "supplierId": "197093",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}

#### sample 3 (id `197397`)

```json
{
  "id": "197397",
  "version": "3",
  "articleNumber": "0100.004",
  "articlePrices": [
    {
      "id": "197398",
      "version": "2",
      "createdDate": 1786082108275,
      "currencyId": "265",
      "lastModifiedByUserId": "184074",
      "lastModifiedDate": 1786082316200,
      "price": "4.25",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [],
      "startDate": 1785967200000
    }
  ],
  "createdDate": 1786082108274,
  "customAttributes": [],
  "description": "<p>Kartonhülsen, spiral&nbsp;40 x 3 x 3030 mm beidseitig mit weissen Plastickdeckeln&nbsp;</p>",
  "dropshippingPossible": false,
  "fixedPurchaseQuantity": "100",
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1786085380738,
  "minimumPurchaseQuantity": "100",
  "name": "Kartonhülsen, Ø 60 x 3 x 3030mm",
  "procurementLeadDays": 21,
  "shortDescription1": "Kartonhülsen 40 x 3 x 3030mm",
  "supplierId": "197093",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}

## A3. Version field

- key `version` present on **4227/4227** records
- non-null on **4227/4227**
- types: {'str': 4227}
- first 10 values: `['6', '1', '1', '2', '1', '1', '1', '1', '1', '1']`
- PUT enforcement: **not tested** (Phase B).

## A4. Currency and price-entry

No top-level currency field on articleSupplySource. Currency lives on nested `articlePrices[].currencyId` (observed).

Currency id catalog from GET /currency:

- id `261` name `EUR` iso `None` keys=['createdDate', 'currencySymbol', 'id', 'lastModifiedDate', 'name', 'version']
- id `262` name `USD` iso `None` keys=['createdDate', 'currencySymbol', 'id', 'lastModifiedDate', 'name', 'version']
- id `263` name `CAD` iso `None` keys=['createdDate', 'currencySymbol', 'id', 'lastModifiedDate', 'name', 'version']
- id `264` name `GBP` iso `None` keys=['createdDate', 'currencySymbol', 'id', 'lastModifiedDate', 'name', 'version']
- id `265` name `CHF` iso `None` keys=['createdDate', 'currencySymbol', 'id', 'lastModifiedDate', 'name', 'version']
- id `266` name `JPY` iso `None` keys=['createdDate', 'currencySymbol', 'id', 'lastModifiedDate', 'name', 'version']
- id `267` name `CNY` iso `None` keys=['createdDate', 'currencySymbol', 'id', 'lastModifiedDate', 'name', 'version']
- id `268` name `TRY` iso `None` keys=['createdDate', 'currencySymbol', 'id', 'lastModifiedDate', 'name', 'version']
- id `269` name `SEK` iso `None` keys=['createdDate', 'currencySymbol', 'id', 'lastModifiedDate', 'name', 'version']
- id `270` name `NOK` iso `None` keys=['createdDate', 'currencySymbol', 'id', 'lastModifiedDate', 'name', 'version']
- id `271` name `DKK` iso `None` keys=['createdDate', 'currencySymbol', 'id', 'lastModifiedDate', 'name', 'version']
- id `272` name `KRW` iso `None` keys=['createdDate', 'currencySymbol', 'id', 'lastModifiedDate', 'name', 'version']
- id `273` name `INR` iso `None` keys=['createdDate', 'currencySymbol', 'id', 'lastModifiedDate', 'name', 'version']
- id `274` name `ILS` iso `None` keys=['createdDate', 'currencySymbol', 'id', 'lastModifiedDate', 'name', 'version']
- id `275` name `CZK` iso `None` keys=['createdDate', 'currencySymbol', 'id', 'lastModifiedDate', 'name', 'version']
- id `276` name `PLN` iso `None` keys=['createdDate', 'currencySymbol', 'id', 'lastModifiedDate', 'name', 'version']
- id `277` name `RUB` iso `None` keys=['createdDate', 'currencySymbol', 'id', 'lastModifiedDate', 'name', 'version']

Supply sources with articlePrices: **4225/4227**
Total nested price rows: **8362**
Union of articlePrices keys: ['createdDate', 'currencyId', 'endDate', 'id', 'lastModifiedByUserId', 'lastModifiedDate', 'price', 'priceScaleType', 'priceScaleValue', 'reductionAdditions', 'startDate', 'version']

Distinct currencyId on nested prices (count = price rows, not SS):

- `currencyId=261 iso/name='EUR'` → 8350
- `currencyId=265 iso/name='CHF'` → 12

startDate presence on price rows: {'has startDate': 8360, 'missing startDate key': 2}

currencyId on prices with endDate=null/absent, per supply source:

- `('261',)` → 4211 supply sources
- `('265',)` → 12 supply sources
- `()` → 4 supply sources

Party currency keys (one count per distinct supplier, not per SS):

- `currencyId='261'` → 2 suppliers
- `currencyId='265'` → 2 suppliers

CSV template columns (1-based / Excel letter):

- **R** = `Preis-Eintritt`
- **V** = `Zugehörigen Verkaufsartikel erstellen oder aktualisieren`
- **W** = `Verkaufsartikel-Nummer`

Full header for reference:

A:ARTIKELNAME;B:Handelssprache;C:Lokaler Artikelname;D:Lieferantenartikelnummer;E:Lieferanten Firmenname;F:LIEFERANTENNUMMER;G:Bruttokaufpreis;H:Zu- und Abschläge Bezeichnung 1;I:Zu- und Abschläge Preisart 1;J:Zu- und Abschläge Wert 1;K:Zu- und Abschläge Bezeichnung 2;L:Zu- und Abschläge Preisart 2;M:Zu- und Abschläge Wert 2;N:Währung;O:Artikel-Mengeneinheit;P:Matchcode;Q:Artikel aktiv;R:Preis-Eintritt;S:Warengruppen-Name;T:Warengruppen Beschreibung;U:Steuersatz;V:Zugehörigen Verkaufsartikel erstellen oder aktualisieren;W:Verkaufsartikel-Nummer;X:Bruttopreis des zugehörigen Verkaufsartikels;Y:Verkaufsartikel-Währung;Z:Vertriebsweg;AA:Vertriebsweg-Steuersatz;AB:Kurztext 1;AC:Handelssprache;AD:Lokalisierte Kurztext 1;AE:Kurztext 2;AF:Handelssprache;AG:Lokalisierte Kurztext 2;AH:Artikelbeschreibung;AI:Handelssprache;AJ:Lokalisierte Artikelbeschreibung;AK:Interner Hinweis;AL:Handelssprache;AM:Lokalisierter interner Hinweis;AN:Artikel-Langbeschreibung;AO:Handelssprache;AP:Lokalisierte Lange Artikelbeschreibung;AQ:EAN-Nummer;AR:MPN-Nummer;AS:Artikeltyp;AT:Serienartikel;AU:Hersteller;AV:Bruttogewicht;AW:Nettogewicht;AX:Zolltarifnummer;AY:Länge Artikel;AZ:Breite Artikel;BA:Höhe Artikel;BB:Herstellertyp;BC:Einführungsdatum;BD:Sicherheitstage;BE:Mindestlagerbestand;BF:Zielbestand;BG:Wiederbeschaffungstage;BH:Durchschnittliche Lieferzeit;BI:Mindestbestellmenge;BJ:Gebindemenge;BK:Lieferantenbestand;BL:Dropshipping möglich;BM:In Dropshipping-Automatisierung ignorieren;BN:Kostenstelle Verkauf;BO:Kostenstelle Einkauf;BP:Kostenart;BQ:Primäre Bezugsquelle

Supply-source keys that look date-ish: ['createdDate', 'lastModifiedDate']

Supply-source keys that look article-link-ish: ['articleNumber', 'articlePrices', 'createdDate']

### Column mapping (evidence labeled)

- **R / Preis-Eintritt** → nested `articlePrices[].startDate` (epoch ms). **Evidence: field-name** (startDate = price valid-from). `createdDate`/`lastModifiedDate` on the SS itself are audit timestamps, not price entry. Value-match vs a known CSV row: **not done** in this probe (no CSV row joined).
- **V / Zugehörigen Verkaufsartikel erstellen oder aktualisieren**: no ja/nein field on GET articleSupplySource. **Guess:** CSV-wizard-only, not persisted.
- **W / Verkaufsartikel-Nummer**: SS.`articleNumber` is **not** the PROSEMA number (samples are supplier-style like `09018030`). The sales-article link is the reverse join (article.supplySources → SS id). **Inference:** W is the article.articleNumber of the linked sales article, not a field stored on the SS GET body. Direct field-name match on SS: **none**.
- **D / Lieferantenartikelnummer** → SS.`articleNumber`. **Evidence: value shape** (not PROSEMA MMM.SSS.NNNN) plus missing `supplierArticleNumber` key.

Sample current-price startDate values (prices with no endDate):
- SS `4418` SS.articleNumber `09018030` startDate `1787608800000` utc `2026-08-24T22:00:00+00:00` price `14.88` currencyId `261`
- SS `6372` SS.articleNumber `1` startDate `1782424800000` utc `2026-06-25T22:00:00+00:00` price `73.32` currencyId `261`
- SS `6375` SS.articleNumber `3003000` startDate `1782424800000` utc `2026-06-25T22:00:00+00:00` price `78.72` currencyId `261`
- SS `6378` SS.articleNumber `3003100` startDate `1782424800000` utc `2026-06-25T22:00:00+00:00` price `34.8` currencyId `261`
- SS `6381` SS.articleNumber `3003250` startDate `1782424800000` utc `2026-06-25T22:00:00+00:00` price `52.56` currencyId `261`
- SS `6384` SS.articleNumber `3010100` startDate `1782424800000` utc `2026-06-25T22:00:00+00:00` price `4.18` currencyId `261`
- SS `6387` SS.articleNumber `3011100` startDate `1782424800000` utc `2026-06-25T22:00:00+00:00` price `4.14` currencyId `261`
- SS `6390` SS.articleNumber `3019250` startDate `1782424800000` utc `2026-06-25T22:00:00+00:00` price `3.06` currencyId `261`

## A5. Supplier article number on the article itself

SAN on the supply source is `articleNumber` (there is no `supplierArticleNumber` key). Comparisons below use that field via the article→SS join.

Articles whose own articleNumber equals a linked SS.articleNumber: **4/4174**

### customAttributeDefinition inventory

| id | label | attributeKey | entity | type |
|---|---|---|---|---|
| `7464` | Artikelbeschreibung (Prosema) | `nulli6h18crqglcrh8` | `` | `LARGE_TEXT` |
| `7462` | Bestand übertragen (Prosema) | `nulli9pc3id0k3h4f2` | `` | `BOOLEAN` |
| `198526` | Bodenleger | `i3cnuvds6ejapv` | `` | `BOOLEAN` |
| `7444` | Breite in mm | `i6ai35uklsqv70` | `` | `STRING` |
| `198523` | Dachdecker | `i3s3s2ntu2jp9p` | `` | `BOOLEAN` |
| `4266` | Farbe | `iaeru44p1ipukc` | `` | `STRING` |
| `7468` | Gewichtseinheit | `nulli9e6dend227b81` | `` | `STRING` |
| `4293` | Grundmaterial | `i2oofds1hupf3t` | `` | `STRING` |
| `226369` | Hauptwarengruppe (Auswahl) | `hauptwarengruppe_shopify_auswahl` | `` | `LIST` |
| `7449` | Höhe in mm | `ilf1c5g7s1rve` | `` | `STRING` |
| `7460` | Im Shop aktiv (Prosema) | `nulli1mvt8dfbqd7uj` | `` | `BOOLEAN` |
| `7458` | Im Shop verfügbar (Prosema) | `nulli648fnd2qep6si` | `` | `BOOLEAN` |
| `7466` | Im Shop verfügbar (Prosema) | `nulli2sertrjdhkv4a` | `` | `BOOLEAN` |
| `7474` | Kunden-ID (Prosema) | `nulli9srj1ugcp39` | `` | `STRING` |
| `198520` | Landschaftsgärtner | `idseegdp90e84` | `` | `BOOLEAN` |
| `7447` | Länge in cm | `ibeec932mvk554` | `` | `STRING` |
| `4262` | Oberfläche | `i3belv31sj6pif` | `` | `STRING` |
| `198529` | Plattenleger | `i6id6mobvffgf6` | `` | `BOOLEAN` |
| `7470` | Produkt-ID (Prosema) | `nulli8dlfcpo9fbnkt` | `` | `STRING` |
| `4500` | Produktfamilie | `i31etd35dn6e95` | `` | `STRING` |
| `4497` | Rabattcode | `ibpet5am0iv3rm` | `` | `STRING` |
| `4399` | VPE 1 | `ie9lusv0jhbuvu` | `` | `STRING` |
| `4401` | VPE 2 | `ic4oc5t4h4nmrm` | `` | `STRING` |
| `4403` | VPE 3 | `iaspf4eifupcd6` | `` | `STRING` |
| `7472` | Varianten-ID (Prosema) | `nullifeei3jfdtb9ur` | `` | `STRING` |
| `4395` | Verkaufseinheit | `i2a7vau9a4ioa3` | `` | `STRING` |
| `4264` | Verpackung | `ic85fk1c627ha5` | `` | `STRING` |
| `184050` | Vertriebsregion | `i2jb7s4qjro278` | `` | `STRING` |
| `226383` | Warengruppe (Auswahl) | `warengruppe_shopify_auswahl` | `` | `LIST` |

Custom-attribute labels treated as PN candidates (name heuristic): []

Also reporting every custom attribute that is non-empty on ≥1 article, so a poorly named field is not missed.

### Native article fields

Extra native keys matching manufacturer/ean/part/sku/gtin/mpn: ['billOfMaterialPartDeliveryPossible', 'ean', 'manufacturerId']

#### `manufacturerPartNumber` — non-empty on **0/4174** articles


#### `ean` — non-empty on **4138/4174** articles

- articleNumber `020.020.0010` ean `4018448005002` | SS.articleNumber: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` ean `4018448053706` | SS.articleNumber: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` ean `4018448053720` | SS.articleNumber: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` ean `4018448039472` | SS.articleNumber: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0050` ean `4018448039571` | SS.articleNumber: ['10000:09018064'] | match: does not equal any linked SS.articleNumber
- equality vs linked SS.articleNumber: **0/4138**

#### `matchCode` — non-empty on **4157/4174** articles

- articleNumber `020.020.0010` matchCode `DSM 30, 250` | SS.articleNumber: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` matchCode `DSM 30-ZF, 250` | SS.articleNumber: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` matchCode `DSM 60-ZF, 250` | SS.articleNumber: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` matchCode `DSM 60, 250` | SS.articleNumber: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0050` matchCode `DSM 60-SP, 250` | SS.articleNumber: ['10000:09018064'] | match: does not equal any linked SS.articleNumber
- equality vs linked SS.articleNumber: **0/4157**

#### `articleNumber` — non-empty on **4174/4174** articles

- articleNumber `990.010.0010` articleNumber `990.010.0010` | SS.articleNumber: — | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0010` articleNumber `020.020.0010` | SS.articleNumber: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` articleNumber `020.020.0020` | SS.articleNumber: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` articleNumber `020.020.0030` | SS.articleNumber: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` articleNumber `020.020.0040` | SS.articleNumber: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- equality vs linked SS.articleNumber: **4/4174**

#### `internalNote` — non-empty on **0/4174** articles


#### `shortDescription1` — non-empty on **4171/4174** articles

- articleNumber `990.010.0010` shortDescription1 `Standard-Ladehilfsmittel` | SS.articleNumber: — | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0010` shortDescription1 `Winkelprofil Messing natur 3 mm 250 cm` | SS.articleNumber: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` shortDescription1 `Biegbares Winkelprofil Messing natur 3 mm 250 cm` | SS.articleNumber: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` shortDescription1 `Biegbares Winkelprofil Messing natur 6mm 250 cm` | SS.articleNumber: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` shortDescription1 `Winkelprofil Messing natur 6mm 250 cm` | SS.articleNumber: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- equality vs linked SS.articleNumber: **0/4171**

#### `shortDescription2` — non-empty on **6/4174** articles

- articleNumber `020.020.1910` shortDescription2 `Winkelprofil V2A 7mm // 250cm` | SS.articleNumber: — | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.1960` shortDescription2 `Winkelprofil natur V2A 17mm // 250cm` | SS.articleNumber: ['10000:9028170'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.1970` shortDescription2 `Winkelprofil V2A 17 mm, Länge 250 cm` | SS.articleNumber: ['10000:90281701'] | match: does not equal any linked SS.articleNumber
- articleNumber `010.030.0040` shortDescription2 `Mechanische Biegevorrichtung` | SS.articleNumber: ['10000:08125999'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.5730` shortDescription2 `Winkelprofil Edelstahl (V2A, 304) hochglanzpoliert 9 // 250 cm` | SS.articleNumber: ['10000:09028091'] | match: does not equal any linked SS.articleNumber
- equality vs linked SS.articleNumber: **0/6**

#### `billOfMaterialPartDeliveryPossible` — non-empty on **4174/4174** articles

- articleNumber `990.010.0010` billOfMaterialPartDeliveryPossible `False` | SS.articleNumber: — | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0010` billOfMaterialPartDeliveryPossible `False` | SS.articleNumber: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` billOfMaterialPartDeliveryPossible `False` | SS.articleNumber: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` billOfMaterialPartDeliveryPossible `False` | SS.articleNumber: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` billOfMaterialPartDeliveryPossible `False` | SS.articleNumber: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- equality vs linked SS.articleNumber: **0/4174**

#### `manufacturerId` — non-empty on **4159/4174** articles

- articleNumber `990.010.0010` manufacturerId `178925` | SS.articleNumber: — | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0010` manufacturerId `178925` | SS.articleNumber: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` manufacturerId `178925` | SS.articleNumber: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` manufacturerId `178925` | SS.articleNumber: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` manufacturerId `178925` | SS.articleNumber: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- equality vs linked SS.articleNumber: **0/4159**

### Custom attributes (all labels with any non-empty value)

#### attr `Bestand übertragen (Prosema)` — non-empty on **4174/4174** articles

- equality vs linked SS.articleNumber: **0/4174**
- articleNumber `990.010.0010` value `False` | SANs: — | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0010` value `False` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `False` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `False` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `False` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber

#### attr `Bodenleger` — non-empty on **4174/4174** articles

- equality vs linked SS.articleNumber: **0/4174**
- articleNumber `990.010.0010` value `False` | SANs: — | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0010` value `False` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `False` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `False` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `False` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber

#### attr `Dachdecker` — non-empty on **4174/4174** articles

- equality vs linked SS.articleNumber: **0/4174**
- articleNumber `990.010.0010` value `False` | SANs: — | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0010` value `False` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `False` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `False` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `False` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber

#### attr `Im Shop aktiv (Prosema)` — non-empty on **4174/4174** articles

- equality vs linked SS.articleNumber: **0/4174**
- articleNumber `990.010.0010` value `True` | SANs: — | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0010` value `True` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `True` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `True` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `True` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber

#### attr `Im Shop verfügbar (Prosema)` — non-empty on **4174/4174** articles

- equality vs linked SS.articleNumber: **0/4174**
- articleNumber `990.010.0010` value `True` | SANs: — | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0010` value `True` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `True` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `True` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `True` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber

#### attr `Landschaftsgärtner` — non-empty on **4174/4174** articles

- equality vs linked SS.articleNumber: **0/4174**
- articleNumber `990.010.0010` value `False` | SANs: — | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0010` value `False` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `False` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `False` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `False` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber

#### attr `Plattenleger` — non-empty on **4174/4174** articles

- equality vs linked SS.articleNumber: **0/4174**
- articleNumber `990.010.0010` value `False` | SANs: — | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0010` value `True` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `True` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `True` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `True` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber

#### attr `VPE 1` — non-empty on **4161/4174** articles

- equality vs linked SS.articleNumber: **0/4161**
- articleNumber `020.020.0010` value `10` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `10` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `10` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `10` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0050` value `10` | SANs: ['10000:09018064'] | match: does not equal any linked SS.articleNumber

#### attr `Gewichtseinheit` — non-empty on **4158/4174** articles

- equality vs linked SS.articleNumber: **0/4158**
- articleNumber `020.020.0010` value `KILOGRAM` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `KILOGRAM` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `KILOGRAM` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `KILOGRAM` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0050` value `KILOGRAM` | SANs: ['10000:09018064'] | match: does not equal any linked SS.articleNumber

#### attr `Produkt-ID (Prosema)` — non-empty on **4158/4174** articles

- equality vs linked SS.articleNumber: **0/4158**
- articleNumber `020.020.0010` value `gid://shopify/Product/15986683445578` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `gid://shopify/Product/15986684264778` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `gid://shopify/Product/15986684985674` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `gid://shopify/Product/15986685772106` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0050` value `gid://shopify/Product/15986687410506` | SANs: ['10000:09018064'] | match: does not equal any linked SS.articleNumber

#### attr `Rabattcode` — non-empty on **4158/4174** articles

- equality vs linked SS.articleNumber: **0/4158**
- articleNumber `020.020.0010` value `A` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `A` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `A` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `A` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0050` value `A` | SANs: ['10000:09018064'] | match: does not equal any linked SS.articleNumber

#### attr `Varianten-ID (Prosema)` — non-empty on **4158/4174** articles

- equality vs linked SS.articleNumber: **0/4158**
- articleNumber `020.020.0010` value `gid://shopify/ProductVariant/63188149698890` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `gid://shopify/ProductVariant/63188183679306` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `gid://shopify/ProductVariant/63188200784202` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `gid://shopify/ProductVariant/63188217954634` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0050` value `gid://shopify/ProductVariant/63188253507914` | SANs: ['10000:09018064'] | match: does not equal any linked SS.articleNumber

#### attr `Verkaufseinheit` — non-empty on **4157/4174** articles

- equality vs linked SS.articleNumber: **0/4157**
- articleNumber `020.020.0010` value `lfm` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `lfm` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `lfm` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `lfm` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0050` value `lfm` | SANs: ['10000:09018064'] | match: does not equal any linked SS.articleNumber

#### attr `Hauptwarengruppe (Auswahl)` — non-empty on **4156/4174** articles

- equality vs linked SS.articleNumber: **0/4156**
- articleNumber `020.020.0010` value `226371` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `226371` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `226371` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `226371` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0050` value `226371` | SANs: ['10000:09018064'] | match: does not equal any linked SS.articleNumber

#### attr `Produktfamilie` — non-empty on **4155/4174** articles

- equality vs linked SS.articleNumber: **0/4155**
- articleNumber `020.020.0010` value `DUROSOL` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `DUROSOL` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `DUROSOL` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `DUROSOL` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0050` value `DUROSOL` | SANs: ['10000:09018064'] | match: does not equal any linked SS.articleNumber

#### attr `Warengruppe (Auswahl)` — non-empty on **3956/4174** articles

- equality vs linked SS.articleNumber: **0/3956**
- articleNumber `020.020.0010` value `226389` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `226389` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `226389` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `226389` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0050` value `226389` | SANs: ['10000:09018064'] | match: does not equal any linked SS.articleNumber

#### attr `Farbe` — non-empty on **3917/4174** articles

- equality vs linked SS.articleNumber: **0/3917**
- articleNumber `020.020.0010` value `Natur` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `Natur` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `Natur` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `Natur` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0050` value `Natur` | SANs: ['10000:09018064'] | match: does not equal any linked SS.articleNumber

#### attr `Oberfläche` — non-empty on **3602/4174** articles

- equality vs linked SS.articleNumber: **0/3602**
- articleNumber `020.020.0010` value `unbehandelt` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `unbehandelt` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `unbehandelt` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `unbehandelt` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0050` value `hochglanzpoliert` | SANs: ['10000:09018064'] | match: does not equal any linked SS.articleNumber

#### attr `Höhe in mm` — non-empty on **3570/4174** articles

- equality vs linked SS.articleNumber: **0/3570**
- articleNumber `020.020.0010` value `3` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `3` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `6` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `6` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0050` value `6` | SANs: ['10000:09018064'] | match: does not equal any linked SS.articleNumber

#### attr `Grundmaterial` — non-empty on **3316/4174** articles

- equality vs linked SS.articleNumber: **0/3316**
- articleNumber `020.020.0010` value `Messing` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `Messing` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `Messing` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `Messing` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0050` value `Messing` | SANs: ['10000:09018064'] | match: does not equal any linked SS.articleNumber

#### attr `Länge in cm` — non-empty on **2408/4174** articles

- equality vs linked SS.articleNumber: **0/2408**
- articleNumber `020.020.0010` value `250` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `250` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `250` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `250` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0050` value `250` | SANs: ['10000:09018064'] | match: does not equal any linked SS.articleNumber

#### attr `Verpackung` — non-empty on **1833/4174** articles

- equality vs linked SS.articleNumber: **0/1833**
- articleNumber `050.010.0240` value `Beutel, 1 Stück` | SANs: ['10000:0911100201'] | match: does not equal any linked SS.articleNumber
- articleNumber `050.010.0250` value `Beutel, 1 Stück` | SANs: ['10000:0911100202'] | match: does not equal any linked SS.articleNumber
- articleNumber `050.010.0260` value `Beutel, 1 Stück` | SANs: ['10000:0911100203'] | match: does not equal any linked SS.articleNumber
- articleNumber `050.010.0270` value `Beutel, 1 Stück` | SANs: ['10000:0911120201'] | match: does not equal any linked SS.articleNumber
- articleNumber `050.010.0280` value `Beutel, 1 Stück` | SANs: ['10000:0911120202'] | match: does not equal any linked SS.articleNumber

#### attr `VPE 2` — non-empty on **1765/4174** articles

- equality vs linked SS.articleNumber: **0/1765**
- articleNumber `020.020.0010` value `40` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0020` value `40` | SANs: ['10000:0901803099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0030` value `40` | SANs: ['10000:0901806099'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `40` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0050` value `40` | SANs: ['10000:09018064'] | match: does not equal any linked SS.articleNumber

#### attr `Breite in mm` — non-empty on **814/4174** articles

- equality vs linked SS.articleNumber: **0/814**
- articleNumber `050.010.0010` value `80` | SANs: ['10000:9020551'] | match: does not equal any linked SS.articleNumber
- articleNumber `050.010.0020` value `80` | SANs: ['10000:09020552'] | match: does not equal any linked SS.articleNumber
- articleNumber `050.010.0030` value `80` | SANs: ['10000:09020751'] | match: does not equal any linked SS.articleNumber
- articleNumber `050.010.0040` value `80` | SANs: ['10000:09020752'] | match: does not equal any linked SS.articleNumber
- articleNumber `050.010.0050` value `80` | SANs: ['10000:09020951'] | match: does not equal any linked SS.articleNumber

#### attr `VPE 3` — non-empty on **107/4174** articles

- equality vs linked SS.articleNumber: **0/107**
- articleNumber `020.020.0010` value `300` | SANs: ['10000:09018030'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0040` value `300` | SANs: ['10000:09018063'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0050` value `300` | SANs: ['10000:09018064'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0070` value `300` | SANs: ['10000:09018083'] | match: does not equal any linked SS.articleNumber
- articleNumber `020.020.0080` value `300` | SANs: ['10000:09018084'] | match: does not equal any linked SS.articleNumber

## A6. Rabattcode population

Articles with non-empty Rabattcode: **4158/4174**

Distinct Rabattcode values:

- `A` → 2765
- `NET` → 916
- `T` → 177
- `I` → 91
- `MAT` → 89
- `C` → 84
- `B` → 36

Cross-tab: Rabattcode × suppliers on that article's supply sources

| Rabattcode | supplierNumber(s) | article count |
|---|---|---:|
| `A` | 10000 DURAL GmbH | 2723 |
| `NET` | 10000 DURAL GmbH | 913 |
| `T` | 10000 DURAL GmbH | 177 |
| `I` | 10000 DURAL GmbH | 91 |
| `C` | 10000 DURAL GmbH | 84 |
| `MAT` | 10000 DURAL GmbH | 83 |
| `A` | (no supply sources) | 42 |
| `B` | 10000 DURAL GmbH | 36 |
| `MAT` | (no supply sources) | 6 |
| `NET` | (no supply sources) | 3 |

## A7. Duplicate supply sources

Articles with more than one supply source for the same supplier: **0** (article,supplier) pairs

(none)

(SS.articleNumber, supplier) pairs on more than one article (or unlinked SS + article): **4**

1. SAN `95000630CI31` supplier `10000 DURAL GmbH` → ['060.030.0040', '060.030.0070']
2. SAN `95001610CI31` supplier `10000 DURAL GmbH` → ['060.030.0050', '060.030.0080']
3. SAN `951003018FGT` supplier `10000 DURAL GmbH` → ['060.060.0010', '060.060.0030']
4. SAN `ETSAK347I20` supplier `10000 DURAL GmbH` → ['060.010.0510', '060.010.0800']

Supply sources with empty articleNumber: **0**


## A7b (join sanity)

Supply sources linked from more than one article: **4** (incident-style shared SS).

1. SS `162262` SAN `95000630CI31` articles ['060.030.0040', '060.030.0070']
2. SS `162310` SAN `95001610CI31` articles ['060.030.0050', '060.030.0080']
3. SS `162350` SAN `951003018FGT` articles ['060.060.0010', '060.060.0030']
4. SS `162458` SAN `ETSAK347I20` articles ['060.010.0510', '060.010.0800']

## A8. Server-side filtering

Filter target supplierId=`4406` supplierNumber=`10000`
Also trying articleNumber-eq=`09018030` articleId-eq=`4216`

### `{'supplierId-eq': '4406'}`

```json
{
  "params": {
    "supplierId-eq": "4406"
  },
  "ok": true,
  "status": 200,
  "elapsed_s": 0.077,
  "result_count_this_page": 5,
  "sample_ids": [
    "4418",
    "6372",
    "6375",
    "6378",
    "6381"
  ],
  "error": null
}
```

Full paged pull with this filter: **4214** records; distinct supplierId: `['4406']`; distinct SS.articleNumber count: 4214

### `{'supplierNumber-eq': '10000'}`

```json
{
  "params": {
    "supplierNumber-eq": "10000"
  },
  "ok": false,
  "status": 400,
  "elapsed_s": 0.067,
  "result_count_this_page": 0,
  "sample_ids": [],
  "error": {
    "detail": "unexpected filter property",
    "error": "unexpected filter property",
    "status": 400,
    "title": "validation failed",
    "type": "/webapp/view/api/errors.html#!/errors/validation",
    "validationErrors": [
      {
        "detail": "unexpected filter property: supplierNumber",
        "instance": "articleSupplySource",
        "location": "supplierNumber-eq",
        "title": "referenced entity not found",
        "type": "/webapp/view/api/errors.html#!/validation/reference"
      }
    ]
  }
}
```

### `{'partyId-eq': '4406'}`

```json
{
  "params": {
    "partyId-eq": "4406"
  },
  "ok": false,
  "status": 400,
  "elapsed_s": 0.08,
  "result_count_this_page": 0,
  "sample_ids": [],
  "error": {
    "detail": "unexpected filter property",
    "error": "unexpected filter property",
    "status": 400,
    "title": "validation failed",
    "type": "/webapp/view/api/errors.html#!/errors/validation",
    "validationErrors": [
      {
        "detail": "unexpected filter property: partyId",
        "instance": "articleSupplySource",
        "location": "partyId-eq",
        "title": "referenced entity not found",
        "type": "/webapp/view/api/errors.html#!/validation/reference"
      }
    ]
  }
}
```

### `{'supplier-eq': '4406'}`

```json
{
  "params": {
    "supplier-eq": "4406"
  },
  "ok": false,
  "status": 400,
  "elapsed_s": 0.072,
  "result_count_this_page": 0,
  "sample_ids": [],
  "error": {
    "detail": "unexpected filter property",
    "error": "unexpected filter property",
    "status": 400,
    "title": "validation failed",
    "type": "/webapp/view/api/errors.html#!/errors/validation",
    "validationErrors": [
      {
        "detail": "unexpected filter property: supplier",
        "instance": "articleSupplySource",
        "location": "supplier-eq",
        "title": "referenced entity not found",
        "type": "/webapp/view/api/errors.html#!/validation/reference"
      }
    ]
  }
}
```

### `{'articleId-eq': '4216'}`

```json
{
  "params": {
    "articleId-eq": "4216"
  },
  "ok": false,
  "status": 400,
  "elapsed_s": 0.105,
  "result_count_this_page": 0,
  "sample_ids": [],
  "error": {
    "detail": "unexpected filter property",
    "error": "unexpected filter property",
    "status": 400,
    "title": "validation failed",
    "type": "/webapp/view/api/errors.html#!/errors/validation",
    "validationErrors": [
      {
        "detail": "unexpected filter property: articleId",
        "instance": "articleSupplySource",
        "location": "articleId-eq",
        "title": "referenced entity not found",
        "type": "/webapp/view/api/errors.html#!/validation/reference"
      }
    ]
  }
}
```

### `{'articleNumber-eq': '09018030'}`

```json
{
  "params": {
    "articleNumber-eq": "09018030"
  },
  "ok": true,
  "status": 200,
  "elapsed_s": 0.084,
  "result_count_this_page": 1,
  "sample_ids": [
    "4418"
  ],
  "error": null
}
```

Full paged pull with this filter: **1** records; distinct supplierId: `['4406']`; distinct SS.articleNumber count: 1

Full unfiltered pull (from A10): **4227** records, **2.35s**, **5** requests.

## A9. Articles without a supply source for a given supplier

Largest non-Dural supplier: number `10061` party `197093` name `Hülsenfabrik Lenzhard` (7 supply sources, 6 distinct linked articles).
Total articles in tenant: **4174**
Articles with ≥1 SS for this supplier: **6**
Articles with **no** SS for this supplier (create-path population): **4168**
Meaningful data? yes, some linked articles

## Design-assumption flags (from Phase A only)

- Phase B was **not** run.
- See A5 for whether a supplier PN lives on the article (tier-3 matching).
- See A7 for uniqueness of (D, F) analogue (SS.articleNumber + supplier).
- See A8 for whether full-tenant paging can be avoided.

