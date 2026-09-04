# articleSupplySource discovery — Phase B

allow_live=True
target=999.999.001
PUT uses ignoreMissingProperties=true (same query param as article write path).
article id=`353023` version=`21`
supply source ids on article: ['353019']
baseline SS id=`353019` version=`'1'` SAN=`999.999.001` name=`TEST ARTICLE - DO NOT USE FOR REAL DATA` supplierId=`4406`
## Known-good PUT (also B4 no-op if values unchanged)

### known-good candidate 1

- outcome: **accepted** status `200`
```json
{
  "id": "353019",
  "version": "2",
  "articleNumber": "999.999.001",
  "articlePrices": [
    {
      "id": "353344",
      "version": "0",
      "createdDate": 1787681735231,
      "currencyId": "261",
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1787681735231,
      "price": "48.9",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353345",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353346",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
          "type": "REDUCTION_PERCENT",
          "value": "15"
        }
      ],
      "startDate": 1787608800000
    },
    {
      "id": "353020",
      "version": "2",
      "createdDate": 1787655003677,
      "currencyId": "261",
      "endDate": 1787608799000,
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1788510963662,
      "price": "48.22",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353021",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353022",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "0"
        }
      ],
      "startDate": 1784066400000
    }
  ],
  "createdDate": 1787655003676,
  "customAttributes": [],
  "dropshippingPossible": true,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1788510963672,
  "matchCode": "FLEX 310 M, 1",
  "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

- after no-op-ish PUT: version `1` → `2` lastModifiedDate `1787681735233` → `1788510963672` name unchanged=True
- B4 Dennis UI audit: **unknown** (not observable via this API).

- **No-op PUT bumped version** (or lastModifiedDate changed).

## B2 Optimistic locking

### B2a correct version

- outcome: **accepted** status `200`
```json
{
  "id": "353019",
  "version": "2",
  "articleNumber": "999.999.001",
  "articlePrices": [
    {
      "id": "353344",
      "version": "0",
      "createdDate": 1787681735231,
      "currencyId": "261",
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1787681735231,
      "price": "48.9",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353345",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353346",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
          "type": "REDUCTION_PERCENT",
          "value": "15"
        }
      ],
      "startDate": 1787608800000
    },
    {
      "id": "353020",
      "version": "2",
      "createdDate": 1787655003677,
      "currencyId": "261",
      "endDate": 1787608799000,
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1788510963662,
      "price": "48.22",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353021",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353022",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "0"
        }
      ],
      "startDate": 1784066400000
    }
  ],
  "createdDate": 1787655003676,
  "customAttributes": [],
  "dropshippingPossible": true,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1788510963672,
  "matchCode": "FLEX 310 M, 1",
  "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

- version now `2`

### B2b stale version

- outcome: **rejected** status `409`
```json
{
  "detail": "optimistic lock error",
  "error": "optimistic lock error",
  "instance": "articleSupplySource/id/353019",
  "status": 409,
  "title": "optimistic lock error",
  "type": "/webapp/view/api/errors.html#!/errors/optimistic_lock"
}
```

- name after stale PUT: `TEST ARTICLE - DO NOT USE FOR REAL DATA` (changed=False)

### B2c version omitted

- outcome: **accepted** status `200`
```json
{
  "id": "353019",
  "version": "3",
  "articleNumber": "999.999.001",
  "articlePrices": [
    {
      "id": "353344",
      "version": "0",
      "createdDate": 1787681735231,
      "currencyId": "261",
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1787681735231,
      "price": "48.9",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353345",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353346",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
          "type": "REDUCTION_PERCENT",
          "value": "15"
        }
      ],
      "startDate": 1787608800000
    },
    {
      "id": "353020",
      "version": "2",
      "createdDate": 1787655003677,
      "currencyId": "261",
      "endDate": 1787608799000,
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1788510963662,
      "price": "48.22",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353021",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353022",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "0"
        }
      ],
      "startDate": 1784066400000
    }
  ],
  "createdDate": 1787655003676,
  "customAttributes": [],
  "dropshippingPossible": true,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1788510964540,
  "matchCode": "FLEX 310 M, 1",
  "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA NOV",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

- name after omit-version PUT: `TEST ARTICLE - DO NOT USE FOR REAL DATA NOV` (changed=True)
- **DANGER: PUT succeeded with version omitted.** Same class of bug as the article path before we made version mandatory.

## B1 Read-only fields (one extra field vs known-good)

### B1 field `id`

- outcome: **accepted** status `200`
```json
{
  "id": "353019",
  "version": "4",
  "articleNumber": "999.999.001",
  "articlePrices": [
    {
      "id": "353344",
      "version": "0",
      "createdDate": 1787681735231,
      "currencyId": "261",
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1787681735231,
      "price": "48.9",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353345",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353346",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
          "type": "REDUCTION_PERCENT",
          "value": "15"
        }
      ],
      "startDate": 1787608800000
    },
    {
      "id": "353020",
      "version": "2",
      "createdDate": 1787655003677,
      "currencyId": "261",
      "endDate": 1787608799000,
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1788510963662,
      "price": "48.22",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353021",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353022",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "0"
        }
      ],
      "startDate": 1784066400000
    }
  ],
  "createdDate": 1787655003676,
  "customAttributes": [],
  "dropshippingPossible": true,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1788510964942,
  "matchCode": "FLEX 310 M, 1",
  "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

### B1 field `createdDate`

- outcome: **accepted** status `200`
```json
{
  "id": "353019",
  "version": "4",
  "articleNumber": "999.999.001",
  "articlePrices": [
    {
      "id": "353344",
      "version": "0",
      "createdDate": 1787681735231,
      "currencyId": "261",
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1787681735231,
      "price": "48.9",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353345",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353346",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
          "type": "REDUCTION_PERCENT",
          "value": "15"
        }
      ],
      "startDate": 1787608800000
    },
    {
      "id": "353020",
      "version": "2",
      "createdDate": 1787655003677,
      "currencyId": "261",
      "endDate": 1787608799000,
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1788510963662,
      "price": "48.22",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353021",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353022",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "0"
        }
      ],
      "startDate": 1784066400000
    }
  ],
  "createdDate": 1787655003676,
  "customAttributes": [],
  "dropshippingPossible": true,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1788510964942,
  "matchCode": "FLEX 310 M, 1",
  "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

### B1 field `lastModifiedDate`

- outcome: **accepted** status `200`
```json
{
  "id": "353019",
  "version": "4",
  "articleNumber": "999.999.001",
  "articlePrices": [
    {
      "id": "353344",
      "version": "0",
      "createdDate": 1787681735231,
      "currencyId": "261",
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1787681735231,
      "price": "48.9",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353345",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353346",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
          "type": "REDUCTION_PERCENT",
          "value": "15"
        }
      ],
      "startDate": 1787608800000
    },
    {
      "id": "353020",
      "version": "2",
      "createdDate": 1787655003677,
      "currencyId": "261",
      "endDate": 1787608799000,
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1788510963662,
      "price": "48.22",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353021",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353022",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "0"
        }
      ],
      "startDate": 1784066400000
    }
  ],
  "createdDate": 1787655003676,
  "customAttributes": [],
  "dropshippingPossible": true,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1788510964942,
  "matchCode": "FLEX 310 M, 1",
  "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

### B1 field `customAttributes`

- outcome: **accepted** status `200`
```json
{
  "id": "353019",
  "version": "4",
  "articleNumber": "999.999.001",
  "articlePrices": [
    {
      "id": "353344",
      "version": "0",
      "createdDate": 1787681735231,
      "currencyId": "261",
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1787681735231,
      "price": "48.9",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353345",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353346",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
          "type": "REDUCTION_PERCENT",
          "value": "15"
        }
      ],
      "startDate": 1787608800000
    },
    {
      "id": "353020",
      "version": "2",
      "createdDate": 1787655003677,
      "currencyId": "261",
      "endDate": 1787608799000,
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1788510963662,
      "price": "48.22",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353021",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353022",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "0"
        }
      ],
      "startDate": 1784066400000
    }
  ],
  "createdDate": 1787655003676,
  "customAttributes": [],
  "dropshippingPossible": true,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1788510964942,
  "matchCode": "FLEX 310 M, 1",
  "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

### B1 field `dropshippingPossible`

- outcome: **accepted** status `200`
```json
{
  "id": "353019",
  "version": "4",
  "articleNumber": "999.999.001",
  "articlePrices": [
    {
      "id": "353344",
      "version": "0",
      "createdDate": 1787681735231,
      "currencyId": "261",
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1787681735231,
      "price": "48.9",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353345",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353346",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
          "type": "REDUCTION_PERCENT",
          "value": "15"
        }
      ],
      "startDate": 1787608800000
    },
    {
      "id": "353020",
      "version": "2",
      "createdDate": 1787655003677,
      "currencyId": "261",
      "endDate": 1787608799000,
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1788510963662,
      "price": "48.22",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353021",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353022",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "0"
        }
      ],
      "startDate": 1784066400000
    }
  ],
  "createdDate": 1787655003676,
  "customAttributes": [],
  "dropshippingPossible": true,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1788510964942,
  "matchCode": "FLEX 310 M, 1",
  "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

### B1 field `ignoreInDropshippingAutomation`

- outcome: **accepted** status `200`
```json
{
  "id": "353019",
  "version": "4",
  "articleNumber": "999.999.001",
  "articlePrices": [
    {
      "id": "353344",
      "version": "0",
      "createdDate": 1787681735231,
      "currencyId": "261",
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1787681735231,
      "price": "48.9",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353345",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353346",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
          "type": "REDUCTION_PERCENT",
          "value": "15"
        }
      ],
      "startDate": 1787608800000
    },
    {
      "id": "353020",
      "version": "2",
      "createdDate": 1787655003677,
      "currencyId": "261",
      "endDate": 1787608799000,
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1788510963662,
      "price": "48.22",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353021",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353022",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "0"
        }
      ],
      "startDate": 1784066400000
    }
  ],
  "createdDate": 1787655003676,
  "customAttributes": [],
  "dropshippingPossible": true,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1788510964942,
  "matchCode": "FLEX 310 M, 1",
  "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

### B1 field `matchCode`

- outcome: **accepted** status `200`
```json
{
  "id": "353019",
  "version": "4",
  "articleNumber": "999.999.001",
  "articlePrices": [
    {
      "id": "353344",
      "version": "0",
      "createdDate": 1787681735231,
      "currencyId": "261",
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1787681735231,
      "price": "48.9",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353345",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353346",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
          "type": "REDUCTION_PERCENT",
          "value": "15"
        }
      ],
      "startDate": 1787608800000
    },
    {
      "id": "353020",
      "version": "2",
      "createdDate": 1787655003677,
      "currencyId": "261",
      "endDate": 1787608799000,
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1788510963662,
      "price": "48.22",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353021",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353022",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "0"
        }
      ],
      "startDate": 1784066400000
    }
  ],
  "createdDate": 1787655003676,
  "customAttributes": [],
  "dropshippingPossible": true,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1788510964942,
  "matchCode": "FLEX 310 M, 1",
  "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

### B1 field `articleNumber`

- outcome: **accepted** status `200`
```json
{
  "id": "353019",
  "version": "4",
  "articleNumber": "999.999.001",
  "articlePrices": [
    {
      "id": "353344",
      "version": "0",
      "createdDate": 1787681735231,
      "currencyId": "261",
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1787681735231,
      "price": "48.9",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353345",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353346",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
          "type": "REDUCTION_PERCENT",
          "value": "15"
        }
      ],
      "startDate": 1787608800000
    },
    {
      "id": "353020",
      "version": "2",
      "createdDate": 1787655003677,
      "currencyId": "261",
      "endDate": 1787608799000,
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1788510963662,
      "price": "48.22",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353021",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353022",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "0"
        }
      ],
      "startDate": 1784066400000
    }
  ],
  "createdDate": 1787655003676,
  "customAttributes": [],
  "dropshippingPossible": true,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1788510964942,
  "matchCode": "FLEX 310 M, 1",
  "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

### B1 field `supplierId`

- outcome: **accepted** status `200`
```json
{
  "id": "353019",
  "version": "4",
  "articleNumber": "999.999.001",
  "articlePrices": [
    {
      "id": "353344",
      "version": "0",
      "createdDate": 1787681735231,
      "currencyId": "261",
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1787681735231,
      "price": "48.9",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353345",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353346",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
          "type": "REDUCTION_PERCENT",
          "value": "15"
        }
      ],
      "startDate": 1787608800000
    },
    {
      "id": "353020",
      "version": "2",
      "createdDate": 1787655003677,
      "currencyId": "261",
      "endDate": 1787608799000,
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1788510963662,
      "price": "48.22",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353021",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353022",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "0"
        }
      ],
      "startDate": 1784066400000
    }
  ],
  "createdDate": 1787655003676,
  "customAttributes": [],
  "dropshippingPossible": true,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1788510964942,
  "matchCode": "FLEX 310 M, 1",
  "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

### B1 field `taxRateType`

- outcome: **accepted** status `200`
```json
{
  "id": "353019",
  "version": "4",
  "articleNumber": "999.999.001",
  "articlePrices": [
    {
      "id": "353344",
      "version": "0",
      "createdDate": 1787681735231,
      "currencyId": "261",
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1787681735231,
      "price": "48.9",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353345",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353346",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
          "type": "REDUCTION_PERCENT",
          "value": "15"
        }
      ],
      "startDate": 1787608800000
    },
    {
      "id": "353020",
      "version": "2",
      "createdDate": 1787655003677,
      "currencyId": "261",
      "endDate": 1787608799000,
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1788510963662,
      "price": "48.22",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353021",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353022",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "0"
        }
      ],
      "startDate": 1784066400000
    }
  ],
  "createdDate": 1787655003676,
  "customAttributes": [],
  "dropshippingPossible": true,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1788510964942,
  "matchCode": "FLEX 310 M, 1",
  "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

### B1 field `unitId`

- outcome: **accepted** status `200`
```json
{
  "id": "353019",
  "version": "4",
  "articleNumber": "999.999.001",
  "articlePrices": [
    {
      "id": "353344",
      "version": "0",
      "createdDate": 1787681735231,
      "currencyId": "261",
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1787681735231,
      "price": "48.9",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353345",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353346",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
          "type": "REDUCTION_PERCENT",
          "value": "15"
        }
      ],
      "startDate": 1787608800000
    },
    {
      "id": "353020",
      "version": "2",
      "createdDate": 1787655003677,
      "currencyId": "261",
      "endDate": 1787608799000,
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1788510963662,
      "price": "48.22",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353021",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353022",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "0"
        }
      ],
      "startDate": 1784066400000
    }
  ],
  "createdDate": 1787655003676,
  "customAttributes": [],
  "dropshippingPossible": true,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1788510964942,
  "matchCode": "FLEX 310 M, 1",
  "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

### B1 field `articlePrices`

- outcome: **accepted** status `200`
```json
{
  "id": "353019",
  "version": "4",
  "articleNumber": "999.999.001",
  "articlePrices": [
    {
      "id": "353344",
      "version": "0",
      "createdDate": 1787681735231,
      "currencyId": "261",
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1787681735231,
      "price": "48.9",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353345",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353346",
          "version": "0",
          "createdDate": 1787681735231,
          "lastModifiedDate": 1787681735231,
          "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
          "type": "REDUCTION_PERCENT",
          "value": "15"
        }
      ],
      "startDate": 1787608800000
    },
    {
      "id": "353020",
      "version": "2",
      "createdDate": 1787655003677,
      "currencyId": "261",
      "endDate": 1787608799000,
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1788510963662,
      "price": "48.22",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": [
        {
          "id": "353021",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "50"
        },
        {
          "id": "353022",
          "version": "0",
          "createdDate": 1787655003677,
          "lastModifiedDate": 1787655003677,
          "type": "REDUCTION_PERCENT",
          "value": "0"
        }
      ],
      "startDate": 1784066400000
    }
  ],
  "createdDate": 1787655003676,
  "customAttributes": [],
  "dropshippingPossible": true,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1788510964942,
  "matchCode": "FLEX 310 M, 1",
  "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

- skip `fixedPurchaseQuantity`: not on GET of this SS
- skip `minimumPurchaseQuantity`: not on GET of this SS
- skip `procurementLeadDays`: not on GET of this SS
- skip `shortDescription1`: not on GET of this SS
Rejected (read-only or invalid when included): (none)
Accepted: ['id', 'createdDate', 'lastModifiedDate', 'customAttributes', 'dropshippingPossible', 'ignoreInDropshippingAutomation', 'matchCode', 'articleNumber', 'supplierId', 'taxRateType', 'unitId', 'articlePrices']

## B1b poison: valid name change + one rejected field

No rejected field to poison with.

## B3 Minimal create

Starting create payload:
```json
{
  "articleId": "353023",
  "supplierId": "4406",
  "articleNumber": "DISCOVERY-PROBE-DO-NOT-USE",
  "name": "DISCOVERY-PROBE",
  "unitId": "3566",
  "taxRateType": "STANDARD",
  "dropshippingPossible": false,
  "ignoreInDropshippingAutomation": true,
  "articlePrices": [
    {
      "price": "1.00",
      "currencyId": "261",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0"
    }
  ]
}
```

### B3 full create

- outcome: **rejected** status `400`
```json
{
  "detail": "Validation failed",
  "error": "Validation failed",
  "status": 400,
  "title": "validation failed",
  "type": "/webapp/view/api/errors.html#!/errors/validation",
  "validationErrors": [
    {
      "detail": "property articleId is unknown",
      "errorCode": "platform.unknown_property",
      "instance": "articleSupplySource",
      "location": "articleId",
      "title": "values are inconsistent",
      "type": "/webapp/view/api/errors.html#!/validation/consistency"
    }
  ]
}
```

## B5 Currency on create

party currencyId=`261` SS current price currencyId=`261` mismatch candidate=`265`
### B5 create with mismatched currencyId

- outcome: **rejected** status `400`
```json
{
  "detail": "Validation failed",
  "error": "Validation failed",
  "status": 400,
  "title": "validation failed",
  "type": "/webapp/view/api/errors.html#!/errors/validation",
  "validationErrors": [
    {
      "detail": "property articleId is unknown",
      "errorCode": "platform.unknown_property",
      "instance": "articleSupplySource",
      "location": "articleId",
      "title": "values are inconsistent",
      "type": "/webapp/view/api/errors.html#!/validation/consistency"
    }
  ]
}
```

Template gap (inference vs today's CSV columns, not a live POST of the CSV): create likely needs articleId (PROSEMA article) which the CSV expresses as W; supplierId from F; SAN as D/articleNumber; unitId from O; prices from G+N+R. V is still unknown as an API field.

Cleanup: no leftovers reported.

## Request / response log

### 1. GET /article status=200

```json
{
  "ts": "2026-09-04T08:36:03.172757+00:00",
  "method": "GET",
  "path": "/article",
  "params": {
    "articleNumber-eq": "999.999.001",
    "pageSize": 1000,
    "page": 1
  },
  "request_body": null,
  "status": 200,
  "response_body": {
    "result": [
      {
        "id": "353023",
        "version": "21",
        "active": false,
        "applyCashDiscount": true,
        "articleAlternativeQuantities": [],
        "articleCalculationPrices": [],
        "articleCategoryId": "20378",
        "articleHeight": "0.0035",
        "articleImages": [
          {
            "id": "353025",
            "version": "0",
            "createdDate": 1787655003686,
            "fileName": "110.050.0030-1_471b346b-75ab-4a9b-9098-2fe71e406d6a.jpg",
            "lastModifiedDate": 1787655003686,
            "mainImage": true
          }
        ],
        "articleLength": "2.95",
        "articleNetWeight": "0.15",
        "articleNumber": "999.999.001",
        "articlePrices": [
          {
            "id": "353043",
            "version": "0",
            "createdDate": 1787655003690,
            "currencyId": "265",
            "lastModifiedByUserId": "17470",
            "lastModifiedDate": 1787655003690,
            "price": "33.63",
            "priceScaleType": "SCALE_FROM",
            "priceScaleValue": "0",
            "reductionAdditions": [],
            "salesChannel": "GROSS1",
            "startDate": 1784066400000
          },
          {
            "id": "353044",
            "version": "0",
            "createdDate": 1787655003690,
            "currencyId": "265",
            "lastModifiedByUserId": "17470",
            "lastModifiedDate": 1787655003690,
            "price": "33.63",
            "priceScaleType": "SCALE_FROM",
            "priceScaleValue": "0",
            "reductionAdditions": [],
            "salesChannel": "NET1",
            "startDate": 1784066400000
          }
        ],
        "articleType": "STORABLE",
        "articleWidth": "0.0165",
        "availableForSalesChannels": [],
        "availableInSale": false,
        "averageDeliveryTime": 2,
        "batchNumberRequired": false,
        "billOfMaterialPartDeliveryPossible": false,
        "commissionRate": "100",
        "createdDate": 1787655003685,
        "customAttributes": [
          {
            "attributeDefinitionId": "4293",
            "stringValue": "TPU"
          },
          {
            "attributeDefinitionId": "4262",
            "stringValue": "geriffelt"
          },
          {
            "attributeDefinitionId": "4266",
            "stringValue": "Grau"
          },
          {
            "attributeDefinitionId": "4264",
            "stringValue": "Karton, 12 Folien á 3 Rippen"
          },
          {
            "attributeDefinitionId": "4395",
            "stringValue": "Folie"
          },
          {
            "attributeDefinitionId": "4399",
            "stringValue": "1"
          },
          {
            "attributeDefinitionId": "4401"
          },
          {
            "attributeDefinitionId": "4403"
          },
          {
            "attributeDefinitionId": "4497",
            "stringValue": "NET"
          },
          {
            "attributeDefinitionId": "4500",
            "stringValue": "TACRIP F DIN"
          },
          {
            "attributeDefinitionId": "7444",
            "stringValue": "16,5"
          },
          {
            "attributeDefinitionId": "7447",
            "stringValue": "29,5"
          },
          {
            "attributeDefinitionId": "7449",
            "stringValue": "3,5"
          },
          {
            "attributeDefinitionId": "198520",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "198523",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "198526",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "198529",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "226369",
            "selectedValueId": "226380"
          },
          {
            "attributeDefinitionId": "226383",
            "selectedValueId": "226431"
          },
          {
            "attributeDefinitionId": "7458",
            "booleanValue": true
          },
          {
            "attributeDefinitionId": "7460",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "7462",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "7464"
          },
          {
            "attributeDefinitionId": "7468",
            "stringValue": "KILOGRAM"
          },
          {
            "attributeDefinitionId": "7470",
            "stringValue": "gid://shopify/Product/15993284886858"
          },
          {
            "attributeDefinitionId": "7472",
            "stringValue": "gid://shopify/ProductVariant/63328582500682"
          }
        ],
        "customerArticleNumbers": [],
        "customsTariffNumberId": "4320",
        "defaultPriceCalculationType": "MARGIN_CALCULATION",
        "defaultStoragePlaces": [],
        "defineIndividualTaskTemplates": false,
        "ean": "4018448095256",
        "lastModifiedDate": 1788354677638,
        "longText": "<p>Die taktile Rippenfolie für taktile Leitsysteme und Richtungsfelder dient zur Ausbildung von Leitstreifen und Richtungsfeldern. Die Rippenstruktur ist taktil erfassbar und unterstützt eine klare Wegeführung auf geeigneten Bodenbelägen. Material: TPU. Oberfläche: geriffelt, Farbe: grau. Abmessungen: 3,5 mm, Breite 16,5 mm. Selbstklebende Ausführung. Verpackungseinheit: Karton, 12 Folien á 3 Rippen.</p>",
        "lowLevelCode": 0,
        "manufacturerId": "178925",
        "marginCalculationPriceType": "PURCHASE_PRICE_PRODUCTION_COST",
        "matchCode": "FLEX 310 M, 1",
        "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
        "packagingUnitBaseArticleId": "353023",
        "primarySupplySourceId": "353019",
        "procurementLeadDays": 10,
        "productionArticle": false,
        "productionBillOfMaterialItems": [],
        "productionConfigurationRule": "ALL_COMPONENTS",
        "purchaseCostCenterId": "7572",
        "quantityConversions": [],
        "salesBillOfMaterialItems": [],
        "salesCostCenterId": "7570",
        "serialNumberRequired": false,
        "shortDescription1": "Taktile Rippenfolie TPU geriffelt grau 3,5 mm, Breite 16,5 mm Karton, 12 Folien á 3 Rippen für taktile Leitsysteme und Richtungsfelder",
        "showOnDeliveryNote": false,
        "supplySources": [
          {
            "id": "353024",
            "version": "1",
            "articleSupplySourceId": "353019",
            "createdDate": 1787655003685,
            "lastModifiedDate": 1787681735247,
            "positionNumber": 1
          }
        ],
        "tags": [],
        "taxRateType": "STANDARD",
        "unitId": "3566",
        "useAvailableForSalesChannels": false,
        "useSalesBillOfMaterialItemPrices": false,
        "useSalesBillOfMaterialItemPricesForPurchase": false,
        "useSalesBillOfMaterialSubitemCosts": false
      }
    ]
  },
  "skipped": false
}
```

### 2. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:03.330643+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "1",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "1",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799999,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735233,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1787681735233,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 3. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:03.419825+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "1",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "1",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799999,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735233,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1787681735233,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 4. PUT /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:03.709621+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "version": "2",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA"
  },
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "2",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510963672,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 5. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:03.803194+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "2",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510963672,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 6. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:03.910533+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "2",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510963672,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 7. PUT /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:04.068898+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "version": "2",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA"
  },
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "2",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510963672,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 8. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:04.155947+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "2",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510963672,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 9. PUT /articleSupplySource/id/353019 status=409

```json
{
  "ts": "2026-09-04T08:36:04.236750+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "version": "0",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA __SS_PROBE__"
  },
  "status": 409,
  "response_body": {
    "detail": "optimistic lock error",
    "error": "optimistic lock error",
    "instance": "articleSupplySource/id/353019",
    "status": 409,
    "title": "optimistic lock error",
    "type": "/webapp/view/api/errors.html#!/errors/optimistic_lock"
  },
  "skipped": false
}
```

### 10. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:04.350893+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "2",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510963672,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 11. PUT /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:04.576620+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA NOV"
  },
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "3",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964540,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA NOV",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 12. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:04.679750+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "3",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964540,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA NOV",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 13. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:04.800638+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "3",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964540,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA NOV",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 14. PUT /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:04.929701+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "version": "3",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA"
  },
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 15. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:05.087750+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 16. PUT /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:05.209830+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "version": "4",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA"
  },
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 17. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:05.332316+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 18. PUT /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:05.435472+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "version": "4",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "createdDate": 1787655003676
  },
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 19. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:05.615111+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 20. PUT /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:05.735296+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "version": "4",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "lastModifiedDate": 1788510964942
  },
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 21. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:05.817817+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 22. PUT /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:05.925710+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "version": "4",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "customAttributes": []
  },
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 23. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:06.015893+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 24. PUT /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:06.135696+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "version": "4",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "dropshippingPossible": true
  },
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 25. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:06.257279+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 26. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:06.348059+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 27. PUT /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:06.476997+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "version": "4",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "ignoreInDropshippingAutomation": false
  },
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 28. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:06.568483+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 29. PUT /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:06.760389+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "version": "4",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "matchCode": "FLEX 310 M, 1"
  },
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 30. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:06.846796+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 31. PUT /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:06.952337+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "version": "4",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "articleNumber": "999.999.001"
  },
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 32. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:07.035529+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 33. PUT /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:07.184806+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "version": "4",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406"
  },
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 34. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:07.269396+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 35. PUT /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:07.524797+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "version": "4",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "taxRateType": "STANDARD"
  },
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 36. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:07.712156+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 37. PUT /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:07.826098+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "version": "4",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "unitId": "3566"
  },
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 38. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:07.912416+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 39. PUT /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:08.019056+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "version": "4",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ]
  },
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 40. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:08.110783+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 41. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:08.231470+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 42. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:08.315071+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 43. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:08.404901+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 44. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:08.489021+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### 45. GET /party/id/4406 status=200

```json
{
  "ts": "2026-09-04T08:36:08.618574+00:00",
  "method": "GET",
  "path": "/party/id/4406",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "4406",
    "version": "7",
    "addresses": [
      {
        "id": "4407",
        "version": "4",
        "city": "Ruppach-Goldhausen",
        "countryCode": "DE",
        "createdDate": 1780566532738,
        "deliveryAddress": false,
        "invoiceAddress": true,
        "lastModifiedDate": 1787830480268,
        "lastName": "Dural GmbH",
        "phoneNumber": "+49 2602 9261 0",
        "primaryAddress": true,
        "street1": "Südring 11",
        "zipcode": "56412"
      }
    ],
    "bankAccounts": [],
    "commercialLanguageId": "280",
    "commissionBlock": false,
    "commissionSalesPartners": [],
    "company": "DURAL GmbH",
    "competitor": false,
    "contacts": [],
    "createdDate": 1780566532739,
    "currencyId": "261",
    "customAttributes": [],
    "customer": false,
    "customerActive": true,
    "customerAllowDropshippingOrderCreation": true,
    "customerBlocked": false,
    "customerBusinessType": "B2B",
    "customerCategoryId": "4160",
    "customerDeliveryBlock": false,
    "customerInsolvent": false,
    "customerInsured": false,
    "customerSalesStageHistory": [],
    "customerUseCustomsTariffNumber": false,
    "email": "M.Kuhl@dural.de",
    "enableDropshippingInNewSupplySources": false,
    "factoring": false,
    "fixedResponsibleUser": false,
    "formerSalesPartner": false,
    "habitualExporter": false,
    "invoiceAddressId": "4407",
    "invoiceBlock": false,
    "lastModifiedDate": 1787830480294,
    "leadSourceId": "4120",
    "onlineAccounts": [],
    "optInEmail": false,
    "optInLetter": false,
    "optInPhone": false,
    "optInSms": false,
    "partyEmailAddresses": [],
    "partyHabitualExporterLettersOfIntent": [],
    "partyType": "ORGANIZATION",
    "primaryAddressId": "4407",
    "purchaseViaPlafond": false,
    "regionId": "4068",
    "responsibleUserId": "184074",
    "salesPartner": false,
    "supplier": true,
    "supplierActive": true,
    "supplierMergeItemsForOcrInvoiceUpload": false,
    "supplierMinimumPurchaseOrderAmount": "6001",
    "supplierNumber": "10000",
    "supplierOrderBlock": false,
    "supplierPaymentMethodId": "3872",
    "supplierShipmentMethodId": "3487",
    "supplierTermOfPaymentId": "3841",
    "tags": [],
    "topics": []
  },
  "skipped": false
}
```

### 46. POST /articleSupplySource status=400

```json
{
  "ts": "2026-09-04T08:36:08.759818+00:00",
  "method": "POST",
  "path": "/articleSupplySource",
  "params": null,
  "request_body": {
    "articleId": "353023",
    "supplierId": "4406",
    "articleNumber": "DISCOVERY-PROBE-DO-NOT-USE",
    "name": "DISCOVERY-PROBE",
    "unitId": "3566",
    "taxRateType": "STANDARD",
    "dropshippingPossible": false,
    "ignoreInDropshippingAutomation": true,
    "articlePrices": [
      {
        "price": "1.00",
        "currencyId": "261",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0"
      }
    ]
  },
  "status": 400,
  "response_body": {
    "detail": "Validation failed",
    "error": "Validation failed",
    "status": 400,
    "title": "validation failed",
    "type": "/webapp/view/api/errors.html#!/errors/validation",
    "validationErrors": [
      {
        "detail": "property articleId is unknown",
        "errorCode": "platform.unknown_property",
        "instance": "articleSupplySource",
        "location": "articleId",
        "title": "values are inconsistent",
        "type": "/webapp/view/api/errors.html#!/validation/consistency"
      }
    ]
  },
  "skipped": false
}
```

### 47. POST /articleSupplySource status=400

```json
{
  "ts": "2026-09-04T08:36:08.945105+00:00",
  "method": "POST",
  "path": "/articleSupplySource",
  "params": null,
  "request_body": {
    "articleId": "353023",
    "supplierId": "4406",
    "articleNumber": "DISCOVERY-PROBE-DO-NOT-USE-CHF",
    "name": "DISCOVERY-PROBE",
    "unitId": "3566",
    "taxRateType": "STANDARD",
    "dropshippingPossible": false,
    "ignoreInDropshippingAutomation": true,
    "articlePrices": [
      {
        "price": "1.00",
        "currencyId": "265",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0"
      }
    ]
  },
  "status": 400,
  "response_body": {
    "detail": "Validation failed",
    "error": "Validation failed",
    "status": 400,
    "title": "validation failed",
    "type": "/webapp/view/api/errors.html#!/errors/validation",
    "validationErrors": [
      {
        "detail": "property articleId is unknown",
        "errorCode": "platform.unknown_property",
        "instance": "articleSupplySource",
        "location": "articleId",
        "title": "values are inconsistent",
        "type": "/webapp/view/api/errors.html#!/validation/consistency"
      }
    ]
  },
  "skipped": false
}
```

### 48. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:09.087122+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```



---
## Follow-up after articleId unknown on POST

article `999.999.001` id=`353023` version=`24`
existing SS `353019` name=`TEST ARTICLE - DO NOT USE FOR REAL DATA`
### B1b PUT name + unknown articleId

- outcome: **rejected** status `400`
```json
{
  "detail": "Validation failed",
  "error": "Validation failed",
  "status": 400,
  "title": "validation failed",
  "type": "/webapp/view/api/errors.html#!/errors/validation",
  "validationErrors": [
    {
      "detail": "property articleId is unknown",
      "errorCode": "platform.unknown_property",
      "instance": "articleSupplySource/id/353019",
      "location": "articleId",
      "title": "values are inconsistent",
      "type": "/webapp/view/api/errors.html#!/validation/consistency"
    }
  ]
}
```

- name after: `TEST ARTICLE - DO NOT USE FOR REAL DATA` applied=False
### B1 extra lastModifiedByUserId on SS

- outcome: **rejected** status `400`
```json
{
  "detail": "Validation failed",
  "error": "Validation failed",
  "status": 400,
  "title": "validation failed",
  "type": "/webapp/view/api/errors.html#!/errors/validation",
  "validationErrors": [
    {
      "detail": "property lastModifiedByUserId is unknown",
      "errorCode": "platform.unknown_property",
      "instance": "articleSupplySource/id/353019",
      "location": "lastModifiedByUserId",
      "title": "values are inconsistent",
      "type": "/webapp/view/api/errors.html#!/validation/consistency"
    }
  ]
}
```

### B3 POST without articleId (full)

- outcome: **rejected** status `400`
```json
{
  "detail": "ignoreInDropshippingAutomation cannot be changed",
  "error": "ignoreInDropshippingAutomation cannot be changed",
  "status": 400,
  "title": "validation failed",
  "type": "/webapp/view/api/errors.html#!/errors/validation",
  "validationErrors": []
}
```

### B3 POST ignoreMissingProperties no articleId

- outcome: **rejected** status `400`
```json
{
  "detail": "ignoreInDropshippingAutomation cannot be changed",
  "error": "ignoreInDropshippingAutomation cannot be changed",
  "status": 400,
  "title": "validation failed",
  "type": "/webapp/view/api/errors.html#!/errors/validation",
  "validationErrors": []
}
```

### B3 supplierId+articleNumber+name

- outcome: **rejected** status `400`
```json
{
  "detail": "unit is required",
  "error": "unit is required",
  "status": 400,
  "title": "validation failed",
  "type": "/webapp/view/api/errors.html#!/errors/validation",
  "validationErrors": [
    {
      "detail": "value must not be empty",
      "instance": "articleSupplySource",
      "location": "unitId",
      "title": "value must not be empty",
      "type": "/webapp/view/api/errors.html#!/validation/not_empty"
    }
  ]
}
```

### B3 +unitId

- outcome: **accepted** status `200`
```json
{
  "id": "399490",
  "version": "0",
  "articleNumber": "DISCOVERY-PROBE-DO-NOT-USE-U",
  "articlePrices": [],
  "createdDate": 1788511001248,
  "customAttributes": [],
  "dropshippingPossible": false,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1788511001248,
  "name": "DISCOVERY-PROBE",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

### B5 POST mismatch CHF without articleId

- outcome: **accepted** status `200`
```json
{
  "id": "399493",
  "version": "0",
  "articleNumber": "DISCOVERY-PROBE-DO-NOT-USE-CHF",
  "articlePrices": [
    {
      "id": "399494",
      "version": "0",
      "createdDate": 1788511001385,
      "currencyId": "265",
      "lastModifiedByUserId": "17470",
      "lastModifiedDate": 1788511001385,
      "price": "1",
      "priceScaleType": "SCALE_FROM",
      "priceScaleValue": "0",
      "reductionAdditions": []
    }
  ],
  "createdDate": 1788511001385,
  "customAttributes": [],
  "dropshippingPossible": false,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1788511001384,
  "name": "DISCOVERY-PROBE",
  "supplierId": "4406",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

- returned first price currencyId: 265

### article PUT supplySources

- outcome: **rejected** status `400`
```json
{
  "detail": "duplicate supplier",
  "error": "duplicate supplier",
  "status": 400,
  "title": "validation failed",
  "type": "/webapp/view/api/errors.html#!/errors/validation",
  "validationErrors": []
}
```

### DELETE created 399490

- outcome: **accepted** status `200`
```json
null
```

### DELETE created 399493

- outcome: **accepted** status `200`
```json
null
```

final article version `24` primary SS `353019` supplySources=[{'id': '353024', 'version': '4', 'articleSupplySourceId': '353019', 'createdDate': 1787655003685, 'lastModifiedDate': 1788510964953, 'positionNumber': 1}]
final SS name `TEST ARTICLE - DO NOT USE FOR REAL DATA` version `4`
Follow-up cleanup: no leftovers.

## Follow-up request log

### F1. GET /article status=200

```json
{
  "ts": "2026-09-04T08:36:40.114849+00:00",
  "method": "GET",
  "path": "/article",
  "params": {
    "articleNumber-eq": "999.999.001",
    "pageSize": 1000,
    "page": 1
  },
  "request_body": null,
  "status": 200,
  "response_body": {
    "result": [
      {
        "id": "353023",
        "version": "24",
        "active": false,
        "applyCashDiscount": true,
        "articleAlternativeQuantities": [],
        "articleCalculationPrices": [],
        "articleCategoryId": "20378",
        "articleHeight": "0.0035",
        "articleImages": [
          {
            "id": "353025",
            "version": "0",
            "createdDate": 1787655003686,
            "fileName": "110.050.0030-1_471b346b-75ab-4a9b-9098-2fe71e406d6a.jpg",
            "lastModifiedDate": 1787655003686,
            "mainImage": true
          }
        ],
        "articleLength": "2.95",
        "articleNetWeight": "0.15",
        "articleNumber": "999.999.001",
        "articlePrices": [
          {
            "id": "353043",
            "version": "0",
            "createdDate": 1787655003690,
            "currencyId": "265",
            "lastModifiedByUserId": "17470",
            "lastModifiedDate": 1787655003690,
            "price": "33.63",
            "priceScaleType": "SCALE_FROM",
            "priceScaleValue": "0",
            "reductionAdditions": [],
            "salesChannel": "GROSS1",
            "startDate": 1784066400000
          },
          {
            "id": "353044",
            "version": "0",
            "createdDate": 1787655003690,
            "currencyId": "265",
            "lastModifiedByUserId": "17470",
            "lastModifiedDate": 1787655003690,
            "price": "33.63",
            "priceScaleType": "SCALE_FROM",
            "priceScaleValue": "0",
            "reductionAdditions": [],
            "salesChannel": "NET1",
            "startDate": 1784066400000
          }
        ],
        "articleType": "STORABLE",
        "articleWidth": "0.0165",
        "availableForSalesChannels": [],
        "availableInSale": false,
        "averageDeliveryTime": 2,
        "batchNumberRequired": false,
        "billOfMaterialPartDeliveryPossible": false,
        "commissionRate": "100",
        "createdDate": 1787655003685,
        "customAttributes": [
          {
            "attributeDefinitionId": "4293",
            "stringValue": "TPU"
          },
          {
            "attributeDefinitionId": "4262",
            "stringValue": "geriffelt"
          },
          {
            "attributeDefinitionId": "4266",
            "stringValue": "Grau"
          },
          {
            "attributeDefinitionId": "4264",
            "stringValue": "Karton, 12 Folien á 3 Rippen"
          },
          {
            "attributeDefinitionId": "4395",
            "stringValue": "Folie"
          },
          {
            "attributeDefinitionId": "4399",
            "stringValue": "1"
          },
          {
            "attributeDefinitionId": "4401"
          },
          {
            "attributeDefinitionId": "4403"
          },
          {
            "attributeDefinitionId": "4497",
            "stringValue": "NET"
          },
          {
            "attributeDefinitionId": "4500",
            "stringValue": "TACRIP F DIN"
          },
          {
            "attributeDefinitionId": "7444",
            "stringValue": "16,5"
          },
          {
            "attributeDefinitionId": "7447",
            "stringValue": "29,5"
          },
          {
            "attributeDefinitionId": "7449",
            "stringValue": "3,5"
          },
          {
            "attributeDefinitionId": "198520",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "198523",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "198526",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "198529",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "226369",
            "selectedValueId": "226380"
          },
          {
            "attributeDefinitionId": "226383",
            "selectedValueId": "226431"
          },
          {
            "attributeDefinitionId": "7458",
            "booleanValue": true
          },
          {
            "attributeDefinitionId": "7460",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "7462",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "7464"
          },
          {
            "attributeDefinitionId": "7468",
            "stringValue": "KILOGRAM"
          },
          {
            "attributeDefinitionId": "7470",
            "stringValue": "gid://shopify/Product/15993284886858"
          },
          {
            "attributeDefinitionId": "7472",
            "stringValue": "gid://shopify/ProductVariant/63328582500682"
          }
        ],
        "customerArticleNumbers": [],
        "customsTariffNumberId": "4320",
        "defaultPriceCalculationType": "MARGIN_CALCULATION",
        "defaultStoragePlaces": [],
        "defineIndividualTaskTemplates": false,
        "ean": "4018448095256",
        "lastModifiedDate": 1788510964953,
        "longText": "<p>Die taktile Rippenfolie für taktile Leitsysteme und Richtungsfelder dient zur Ausbildung von Leitstreifen und Richtungsfeldern. Die Rippenstruktur ist taktil erfassbar und unterstützt eine klare Wegeführung auf geeigneten Bodenbelägen. Material: TPU. Oberfläche: geriffelt, Farbe: grau. Abmessungen: 3,5 mm, Breite 16,5 mm. Selbstklebende Ausführung. Verpackungseinheit: Karton, 12 Folien á 3 Rippen.</p>",
        "lowLevelCode": 0,
        "manufacturerId": "178925",
        "marginCalculationPriceType": "PURCHASE_PRICE_PRODUCTION_COST",
        "matchCode": "FLEX 310 M, 1",
        "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
        "packagingUnitBaseArticleId": "353023",
        "primarySupplySourceId": "353019",
        "procurementLeadDays": 10,
        "productionArticle": false,
        "productionBillOfMaterialItems": [],
        "productionConfigurationRule": "ALL_COMPONENTS",
        "purchaseCostCenterId": "7572",
        "quantityConversions": [],
        "salesBillOfMaterialItems": [],
        "salesCostCenterId": "7570",
        "serialNumberRequired": false,
        "shortDescription1": "Taktile Rippenfolie TPU geriffelt grau 3,5 mm, Breite 16,5 mm Karton, 12 Folien á 3 Rippen für taktile Leitsysteme und Richtungsfelder",
        "showOnDeliveryNote": false,
        "supplySources": [
          {
            "id": "353024",
            "version": "4",
            "articleSupplySourceId": "353019",
            "createdDate": 1787655003685,
            "lastModifiedDate": 1788510964953,
            "positionNumber": 1
          }
        ],
        "tags": [],
        "taxRateType": "STANDARD",
        "unitId": "3566",
        "useAvailableForSalesChannels": false,
        "useSalesBillOfMaterialItemPrices": false,
        "useSalesBillOfMaterialItemPricesForPurchase": false,
        "useSalesBillOfMaterialSubitemCosts": false
      }
    ]
  },
  "skipped": false
}
```

### F2. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:40.218588+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### F3. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:40.293483+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### F4. PUT /articleSupplySource/id/353019 status=400

```json
{
  "ts": "2026-09-04T08:36:40.364238+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "version": "4",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA __SS_PROBE__",
    "articleId": "353023"
  },
  "status": 400,
  "response_body": {
    "detail": "Validation failed",
    "error": "Validation failed",
    "status": 400,
    "title": "validation failed",
    "type": "/webapp/view/api/errors.html#!/errors/validation",
    "validationErrors": [
      {
        "detail": "property articleId is unknown",
        "errorCode": "platform.unknown_property",
        "instance": "articleSupplySource/id/353019",
        "location": "articleId",
        "title": "values are inconsistent",
        "type": "/webapp/view/api/errors.html#!/validation/consistency"
      }
    ]
  },
  "skipped": false
}
```

### F5. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:40.491249+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### F6. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:40.555608+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### F7. PUT /articleSupplySource/id/353019 status=400

```json
{
  "ts": "2026-09-04T08:36:40.636327+00:00",
  "method": "PUT",
  "path": "/articleSupplySource/id/353019",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353019",
    "version": "4",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "lastModifiedByUserId": "17470"
  },
  "status": 400,
  "response_body": {
    "detail": "Validation failed",
    "error": "Validation failed",
    "status": 400,
    "title": "validation failed",
    "type": "/webapp/view/api/errors.html#!/errors/validation",
    "validationErrors": [
      {
        "detail": "property lastModifiedByUserId is unknown",
        "errorCode": "platform.unknown_property",
        "instance": "articleSupplySource/id/353019",
        "location": "lastModifiedByUserId",
        "title": "values are inconsistent",
        "type": "/webapp/view/api/errors.html#!/validation/consistency"
      }
    ]
  },
  "skipped": false
}
```

### F8. POST /articleSupplySource status=400

```json
{
  "ts": "2026-09-04T08:36:40.839949+00:00",
  "method": "POST",
  "path": "/articleSupplySource",
  "params": null,
  "request_body": {
    "supplierId": "4406",
    "articleNumber": "DISCOVERY-PROBE-DO-NOT-USE",
    "name": "DISCOVERY-PROBE",
    "unitId": "3566",
    "taxRateType": "STANDARD",
    "dropshippingPossible": false,
    "ignoreInDropshippingAutomation": true,
    "articlePrices": [
      {
        "price": "1.00",
        "currencyId": "261",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0"
      }
    ]
  },
  "status": 400,
  "response_body": {
    "detail": "ignoreInDropshippingAutomation cannot be changed",
    "error": "ignoreInDropshippingAutomation cannot be changed",
    "status": 400,
    "title": "validation failed",
    "type": "/webapp/view/api/errors.html#!/errors/validation",
    "validationErrors": []
  },
  "skipped": false
}
```

### F9. POST /articleSupplySource status=400

```json
{
  "ts": "2026-09-04T08:36:40.973133+00:00",
  "method": "POST",
  "path": "/articleSupplySource",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "supplierId": "4406",
    "articleNumber": "DISCOVERY-PROBE-DO-NOT-USE",
    "name": "DISCOVERY-PROBE",
    "unitId": "3566",
    "taxRateType": "STANDARD",
    "dropshippingPossible": false,
    "ignoreInDropshippingAutomation": true,
    "articlePrices": [
      {
        "price": "1.00",
        "currencyId": "261",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0"
      }
    ]
  },
  "status": 400,
  "response_body": {
    "detail": "ignoreInDropshippingAutomation cannot be changed",
    "error": "ignoreInDropshippingAutomation cannot be changed",
    "status": 400,
    "title": "validation failed",
    "type": "/webapp/view/api/errors.html#!/errors/validation",
    "validationErrors": []
  },
  "skipped": false
}
```

### F10. POST /articleSupplySource status=400

```json
{
  "ts": "2026-09-04T08:36:41.068497+00:00",
  "method": "POST",
  "path": "/articleSupplySource",
  "params": null,
  "request_body": {
    "supplierId": "4406",
    "articleNumber": "DISCOVERY-PROBE-DO-NOT-USE-MIN",
    "name": "DISCOVERY-PROBE"
  },
  "status": 400,
  "response_body": {
    "detail": "unit is required",
    "error": "unit is required",
    "status": 400,
    "title": "validation failed",
    "type": "/webapp/view/api/errors.html#!/errors/validation",
    "validationErrors": [
      {
        "detail": "value must not be empty",
        "instance": "articleSupplySource",
        "location": "unitId",
        "title": "value must not be empty",
        "type": "/webapp/view/api/errors.html#!/validation/not_empty"
      }
    ]
  },
  "skipped": false
}
```

### F11. POST /articleSupplySource status=200

```json
{
  "ts": "2026-09-04T08:36:41.267957+00:00",
  "method": "POST",
  "path": "/articleSupplySource",
  "params": null,
  "request_body": {
    "supplierId": "4406",
    "articleNumber": "DISCOVERY-PROBE-DO-NOT-USE-U",
    "name": "DISCOVERY-PROBE",
    "unitId": "3566"
  },
  "status": 200,
  "response_body": {
    "id": "399490",
    "version": "0",
    "articleNumber": "DISCOVERY-PROBE-DO-NOT-USE-U",
    "articlePrices": [],
    "createdDate": 1788511001248,
    "customAttributes": [],
    "dropshippingPossible": false,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788511001248,
    "name": "DISCOVERY-PROBE",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### F12. POST /articleSupplySource status=200

```json
{
  "ts": "2026-09-04T08:36:41.355138+00:00",
  "method": "POST",
  "path": "/articleSupplySource",
  "params": null,
  "request_body": {
    "supplierId": "4406",
    "articleNumber": "DISCOVERY-PROBE-DO-NOT-USE-CHF",
    "name": "DISCOVERY-PROBE",
    "unitId": "3566",
    "taxRateType": "STANDARD",
    "articlePrices": [
      {
        "price": "1.00",
        "currencyId": "265",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0"
      }
    ]
  },
  "status": 200,
  "response_body": {
    "id": "399493",
    "version": "0",
    "articleNumber": "DISCOVERY-PROBE-DO-NOT-USE-CHF",
    "articlePrices": [
      {
        "id": "399494",
        "version": "0",
        "createdDate": 1788511001385,
        "currencyId": "265",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788511001385,
        "price": "1",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": []
      }
    ],
    "createdDate": 1788511001385,
    "customAttributes": [],
    "dropshippingPossible": false,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788511001384,
    "name": "DISCOVERY-PROBE",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```

### F13. GET /article status=200

```json
{
  "ts": "2026-09-04T08:36:41.438493+00:00",
  "method": "GET",
  "path": "/article",
  "params": {
    "articleNumber-eq": "999.999.001",
    "pageSize": 1000,
    "page": 1
  },
  "request_body": null,
  "status": 200,
  "response_body": {
    "result": [
      {
        "id": "353023",
        "version": "24",
        "active": false,
        "applyCashDiscount": true,
        "articleAlternativeQuantities": [],
        "articleCalculationPrices": [],
        "articleCategoryId": "20378",
        "articleHeight": "0.0035",
        "articleImages": [
          {
            "id": "353025",
            "version": "0",
            "createdDate": 1787655003686,
            "fileName": "110.050.0030-1_471b346b-75ab-4a9b-9098-2fe71e406d6a.jpg",
            "lastModifiedDate": 1787655003686,
            "mainImage": true
          }
        ],
        "articleLength": "2.95",
        "articleNetWeight": "0.15",
        "articleNumber": "999.999.001",
        "articlePrices": [
          {
            "id": "353043",
            "version": "0",
            "createdDate": 1787655003690,
            "currencyId": "265",
            "lastModifiedByUserId": "17470",
            "lastModifiedDate": 1787655003690,
            "price": "33.63",
            "priceScaleType": "SCALE_FROM",
            "priceScaleValue": "0",
            "reductionAdditions": [],
            "salesChannel": "GROSS1",
            "startDate": 1784066400000
          },
          {
            "id": "353044",
            "version": "0",
            "createdDate": 1787655003690,
            "currencyId": "265",
            "lastModifiedByUserId": "17470",
            "lastModifiedDate": 1787655003690,
            "price": "33.63",
            "priceScaleType": "SCALE_FROM",
            "priceScaleValue": "0",
            "reductionAdditions": [],
            "salesChannel": "NET1",
            "startDate": 1784066400000
          }
        ],
        "articleType": "STORABLE",
        "articleWidth": "0.0165",
        "availableForSalesChannels": [],
        "availableInSale": false,
        "averageDeliveryTime": 2,
        "batchNumberRequired": false,
        "billOfMaterialPartDeliveryPossible": false,
        "commissionRate": "100",
        "createdDate": 1787655003685,
        "customAttributes": [
          {
            "attributeDefinitionId": "4293",
            "stringValue": "TPU"
          },
          {
            "attributeDefinitionId": "4262",
            "stringValue": "geriffelt"
          },
          {
            "attributeDefinitionId": "4266",
            "stringValue": "Grau"
          },
          {
            "attributeDefinitionId": "4264",
            "stringValue": "Karton, 12 Folien á 3 Rippen"
          },
          {
            "attributeDefinitionId": "4395",
            "stringValue": "Folie"
          },
          {
            "attributeDefinitionId": "4399",
            "stringValue": "1"
          },
          {
            "attributeDefinitionId": "4401"
          },
          {
            "attributeDefinitionId": "4403"
          },
          {
            "attributeDefinitionId": "4497",
            "stringValue": "NET"
          },
          {
            "attributeDefinitionId": "4500",
            "stringValue": "TACRIP F DIN"
          },
          {
            "attributeDefinitionId": "7444",
            "stringValue": "16,5"
          },
          {
            "attributeDefinitionId": "7447",
            "stringValue": "29,5"
          },
          {
            "attributeDefinitionId": "7449",
            "stringValue": "3,5"
          },
          {
            "attributeDefinitionId": "198520",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "198523",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "198526",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "198529",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "226369",
            "selectedValueId": "226380"
          },
          {
            "attributeDefinitionId": "226383",
            "selectedValueId": "226431"
          },
          {
            "attributeDefinitionId": "7458",
            "booleanValue": true
          },
          {
            "attributeDefinitionId": "7460",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "7462",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "7464"
          },
          {
            "attributeDefinitionId": "7468",
            "stringValue": "KILOGRAM"
          },
          {
            "attributeDefinitionId": "7470",
            "stringValue": "gid://shopify/Product/15993284886858"
          },
          {
            "attributeDefinitionId": "7472",
            "stringValue": "gid://shopify/ProductVariant/63328582500682"
          }
        ],
        "customerArticleNumbers": [],
        "customsTariffNumberId": "4320",
        "defaultPriceCalculationType": "MARGIN_CALCULATION",
        "defaultStoragePlaces": [],
        "defineIndividualTaskTemplates": false,
        "ean": "4018448095256",
        "lastModifiedDate": 1788510964953,
        "longText": "<p>Die taktile Rippenfolie für taktile Leitsysteme und Richtungsfelder dient zur Ausbildung von Leitstreifen und Richtungsfeldern. Die Rippenstruktur ist taktil erfassbar und unterstützt eine klare Wegeführung auf geeigneten Bodenbelägen. Material: TPU. Oberfläche: geriffelt, Farbe: grau. Abmessungen: 3,5 mm, Breite 16,5 mm. Selbstklebende Ausführung. Verpackungseinheit: Karton, 12 Folien á 3 Rippen.</p>",
        "lowLevelCode": 0,
        "manufacturerId": "178925",
        "marginCalculationPriceType": "PURCHASE_PRICE_PRODUCTION_COST",
        "matchCode": "FLEX 310 M, 1",
        "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
        "packagingUnitBaseArticleId": "353023",
        "primarySupplySourceId": "353019",
        "procurementLeadDays": 10,
        "productionArticle": false,
        "productionBillOfMaterialItems": [],
        "productionConfigurationRule": "ALL_COMPONENTS",
        "purchaseCostCenterId": "7572",
        "quantityConversions": [],
        "salesBillOfMaterialItems": [],
        "salesCostCenterId": "7570",
        "serialNumberRequired": false,
        "shortDescription1": "Taktile Rippenfolie TPU geriffelt grau 3,5 mm, Breite 16,5 mm Karton, 12 Folien á 3 Rippen für taktile Leitsysteme und Richtungsfelder",
        "showOnDeliveryNote": false,
        "supplySources": [
          {
            "id": "353024",
            "version": "4",
            "articleSupplySourceId": "353019",
            "createdDate": 1787655003685,
            "lastModifiedDate": 1788510964953,
            "positionNumber": 1
          }
        ],
        "tags": [],
        "taxRateType": "STANDARD",
        "unitId": "3566",
        "useAvailableForSalesChannels": false,
        "useSalesBillOfMaterialItemPrices": false,
        "useSalesBillOfMaterialItemPricesForPurchase": false,
        "useSalesBillOfMaterialSubitemCosts": false
      }
    ]
  },
  "skipped": false
}
```

### F14. PUT /article/id/353023 status=400

```json
{
  "ts": "2026-09-04T08:36:41.523490+00:00",
  "method": "PUT",
  "path": "/article/id/353023",
  "params": {
    "ignoreMissingProperties": "true"
  },
  "request_body": {
    "id": "353023",
    "version": "24",
    "supplySources": [
      {
        "id": "353024",
        "version": "4",
        "articleSupplySourceId": "353019",
        "createdDate": 1787655003685,
        "lastModifiedDate": 1788510964953,
        "positionNumber": 1
      },
      {
        "articleSupplySourceId": "399490",
        "positionNumber": 2
      }
    ]
  },
  "status": 400,
  "response_body": {
    "detail": "duplicate supplier",
    "error": "duplicate supplier",
    "status": 400,
    "title": "validation failed",
    "type": "/webapp/view/api/errors.html#!/errors/validation",
    "validationErrors": []
  },
  "skipped": false
}
```

### F15. DELETE /articleSupplySource/id/399490 status=200

```json
{
  "ts": "2026-09-04T08:36:42.059485+00:00",
  "method": "DELETE",
  "path": "/articleSupplySource/id/399490",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": null,
  "skipped": false
}
```

### F16. DELETE /articleSupplySource/id/399493 status=200

```json
{
  "ts": "2026-09-04T08:36:42.177846+00:00",
  "method": "DELETE",
  "path": "/articleSupplySource/id/399493",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": null,
  "skipped": false
}
```

### F17. GET /article status=200

```json
{
  "ts": "2026-09-04T08:36:42.319646+00:00",
  "method": "GET",
  "path": "/article",
  "params": {
    "articleNumber-eq": "999.999.001",
    "pageSize": 1000,
    "page": 1
  },
  "request_body": null,
  "status": 200,
  "response_body": {
    "result": [
      {
        "id": "353023",
        "version": "24",
        "active": false,
        "applyCashDiscount": true,
        "articleAlternativeQuantities": [],
        "articleCalculationPrices": [],
        "articleCategoryId": "20378",
        "articleHeight": "0.0035",
        "articleImages": [
          {
            "id": "353025",
            "version": "0",
            "createdDate": 1787655003686,
            "fileName": "110.050.0030-1_471b346b-75ab-4a9b-9098-2fe71e406d6a.jpg",
            "lastModifiedDate": 1787655003686,
            "mainImage": true
          }
        ],
        "articleLength": "2.95",
        "articleNetWeight": "0.15",
        "articleNumber": "999.999.001",
        "articlePrices": [
          {
            "id": "353043",
            "version": "0",
            "createdDate": 1787655003690,
            "currencyId": "265",
            "lastModifiedByUserId": "17470",
            "lastModifiedDate": 1787655003690,
            "price": "33.63",
            "priceScaleType": "SCALE_FROM",
            "priceScaleValue": "0",
            "reductionAdditions": [],
            "salesChannel": "GROSS1",
            "startDate": 1784066400000
          },
          {
            "id": "353044",
            "version": "0",
            "createdDate": 1787655003690,
            "currencyId": "265",
            "lastModifiedByUserId": "17470",
            "lastModifiedDate": 1787655003690,
            "price": "33.63",
            "priceScaleType": "SCALE_FROM",
            "priceScaleValue": "0",
            "reductionAdditions": [],
            "salesChannel": "NET1",
            "startDate": 1784066400000
          }
        ],
        "articleType": "STORABLE",
        "articleWidth": "0.0165",
        "availableForSalesChannels": [],
        "availableInSale": false,
        "averageDeliveryTime": 2,
        "batchNumberRequired": false,
        "billOfMaterialPartDeliveryPossible": false,
        "commissionRate": "100",
        "createdDate": 1787655003685,
        "customAttributes": [
          {
            "attributeDefinitionId": "4293",
            "stringValue": "TPU"
          },
          {
            "attributeDefinitionId": "4262",
            "stringValue": "geriffelt"
          },
          {
            "attributeDefinitionId": "4266",
            "stringValue": "Grau"
          },
          {
            "attributeDefinitionId": "4264",
            "stringValue": "Karton, 12 Folien á 3 Rippen"
          },
          {
            "attributeDefinitionId": "4395",
            "stringValue": "Folie"
          },
          {
            "attributeDefinitionId": "4399",
            "stringValue": "1"
          },
          {
            "attributeDefinitionId": "4401"
          },
          {
            "attributeDefinitionId": "4403"
          },
          {
            "attributeDefinitionId": "4497",
            "stringValue": "NET"
          },
          {
            "attributeDefinitionId": "4500",
            "stringValue": "TACRIP F DIN"
          },
          {
            "attributeDefinitionId": "7444",
            "stringValue": "16,5"
          },
          {
            "attributeDefinitionId": "7447",
            "stringValue": "29,5"
          },
          {
            "attributeDefinitionId": "7449",
            "stringValue": "3,5"
          },
          {
            "attributeDefinitionId": "198520",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "198523",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "198526",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "198529",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "226369",
            "selectedValueId": "226380"
          },
          {
            "attributeDefinitionId": "226383",
            "selectedValueId": "226431"
          },
          {
            "attributeDefinitionId": "7458",
            "booleanValue": true
          },
          {
            "attributeDefinitionId": "7460",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "7462",
            "booleanValue": false
          },
          {
            "attributeDefinitionId": "7464"
          },
          {
            "attributeDefinitionId": "7468",
            "stringValue": "KILOGRAM"
          },
          {
            "attributeDefinitionId": "7470",
            "stringValue": "gid://shopify/Product/15993284886858"
          },
          {
            "attributeDefinitionId": "7472",
            "stringValue": "gid://shopify/ProductVariant/63328582500682"
          }
        ],
        "customerArticleNumbers": [],
        "customsTariffNumberId": "4320",
        "defaultPriceCalculationType": "MARGIN_CALCULATION",
        "defaultStoragePlaces": [],
        "defineIndividualTaskTemplates": false,
        "ean": "4018448095256",
        "lastModifiedDate": 1788510964953,
        "longText": "<p>Die taktile Rippenfolie für taktile Leitsysteme und Richtungsfelder dient zur Ausbildung von Leitstreifen und Richtungsfeldern. Die Rippenstruktur ist taktil erfassbar und unterstützt eine klare Wegeführung auf geeigneten Bodenbelägen. Material: TPU. Oberfläche: geriffelt, Farbe: grau. Abmessungen: 3,5 mm, Breite 16,5 mm. Selbstklebende Ausführung. Verpackungseinheit: Karton, 12 Folien á 3 Rippen.</p>",
        "lowLevelCode": 0,
        "manufacturerId": "178925",
        "marginCalculationPriceType": "PURCHASE_PRICE_PRODUCTION_COST",
        "matchCode": "FLEX 310 M, 1",
        "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
        "packagingUnitBaseArticleId": "353023",
        "primarySupplySourceId": "353019",
        "procurementLeadDays": 10,
        "productionArticle": false,
        "productionBillOfMaterialItems": [],
        "productionConfigurationRule": "ALL_COMPONENTS",
        "purchaseCostCenterId": "7572",
        "quantityConversions": [],
        "salesBillOfMaterialItems": [],
        "salesCostCenterId": "7570",
        "serialNumberRequired": false,
        "shortDescription1": "Taktile Rippenfolie TPU geriffelt grau 3,5 mm, Breite 16,5 mm Karton, 12 Folien á 3 Rippen für taktile Leitsysteme und Richtungsfelder",
        "showOnDeliveryNote": false,
        "supplySources": [
          {
            "id": "353024",
            "version": "4",
            "articleSupplySourceId": "353019",
            "createdDate": 1787655003685,
            "lastModifiedDate": 1788510964953,
            "positionNumber": 1
          }
        ],
        "tags": [],
        "taxRateType": "STANDARD",
        "unitId": "3566",
        "useAvailableForSalesChannels": false,
        "useSalesBillOfMaterialItemPrices": false,
        "useSalesBillOfMaterialItemPricesForPurchase": false,
        "useSalesBillOfMaterialSubitemCosts": false
      }
    ]
  },
  "skipped": false
}
```

### F18. GET /articleSupplySource/id/353019 status=200

```json
{
  "ts": "2026-09-04T08:36:42.392666+00:00",
  "method": "GET",
  "path": "/articleSupplySource/id/353019",
  "params": null,
  "request_body": null,
  "status": 200,
  "response_body": {
    "id": "353019",
    "version": "4",
    "articleNumber": "999.999.001",
    "articlePrices": [
      {
        "id": "353344",
        "version": "0",
        "createdDate": 1787681735231,
        "currencyId": "261",
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1787681735231,
        "price": "48.9",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353345",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Grundrabatt · Dural Preisliste 2026-08 · Profile, Duschrinnen & Zubehoer · Kat. NET · 50%",
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353346",
            "version": "0",
            "createdDate": 1787681735231,
            "lastModifiedDate": 1787681735231,
            "name": "Kundenrabatt · Dural Preisliste 2026-08 · Kat. NET · 15%",
            "type": "REDUCTION_PERCENT",
            "value": "15"
          }
        ],
        "startDate": 1787608800000
      },
      {
        "id": "353020",
        "version": "2",
        "createdDate": 1787655003677,
        "currencyId": "261",
        "endDate": 1787608799000,
        "lastModifiedByUserId": "17470",
        "lastModifiedDate": 1788510963662,
        "price": "48.22",
        "priceScaleType": "SCALE_FROM",
        "priceScaleValue": "0",
        "reductionAdditions": [
          {
            "id": "353021",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "50"
          },
          {
            "id": "353022",
            "version": "0",
            "createdDate": 1787655003677,
            "lastModifiedDate": 1787655003677,
            "type": "REDUCTION_PERCENT",
            "value": "0"
          }
        ],
        "startDate": 1784066400000
      }
    ],
    "createdDate": 1787655003676,
    "customAttributes": [],
    "dropshippingPossible": true,
    "ignoreInDropshippingAutomation": false,
    "lastModifiedDate": 1788510964942,
    "matchCode": "FLEX 310 M, 1",
    "name": "TEST ARTICLE - DO NOT USE FOR REAL DATA",
    "supplierId": "4406",
    "taxRateType": "STANDARD",
    "unitId": "3566"
  },
  "skipped": false
}
```


---
## Follow-up: attach a *different* supplier SS to 999.999.001

before: version=24 primary=353019 refs=[{'id': '353024', 'version': '4', 'articleSupplySourceId': '353019', 'createdDate': 1787655003685, 'lastModifiedDate': 1788510964953, 'positionNumber': 1}]
### POST Lenzhard SS

- outcome: **accepted** status `200`
```json
{
  "id": "399501",
  "version": "0",
  "articleNumber": "DISCOVERY-PROBE-DO-NOT-USE-LENZ",
  "articlePrices": [],
  "createdDate": 1788511016991,
  "customAttributes": [],
  "dropshippingPossible": false,
  "ignoreInDropshippingAutomation": false,
  "lastModifiedDate": 1788511016991,
  "name": "DISCOVERY-PROBE",
  "supplierId": "197093",
  "taxRateType": "STANDARD",
  "unitId": "3566"
}
```

### attach Lenzhard via article PUT

- outcome: **accepted** status `200`
```json
{
  "version": "25",
  "primarySupplySourceId": "353019",
  "supplySources": [
    {
      "id": "353024",
      "version": "4",
      "articleSupplySourceId": "353019",
      "createdDate": 1787655003685,
      "lastModifiedDate": 1788510964953,
      "positionNumber": 1
    },
    {
      "id": "399504",
      "version": "0",
      "articleSupplySourceId": "399501",
      "createdDate": 1788511017516,
      "lastModifiedDate": 1788511017516,
      "positionNumber": 2
    }
  ]
}
```

### restore original supplySources

- outcome: **accepted** status `200`
```json
{
  "version": "26",
  "primarySupplySourceId": "353019",
  "supplySources": [
    {
      "id": "353024",
      "version": "4",
      "articleSupplySourceId": "353019",
      "createdDate": 1787655003685,
      "lastModifiedDate": 1788510964953,
      "positionNumber": 1
    }
  ]
}
```

### DELETE 399501

- outcome: **accepted** status `200`
```json
null
```

after: version=26 primary=353019 refs=[{'id': '353024', 'version': '4', 'articleSupplySourceId': '353019', 'createdDate': 1787655003685, 'lastModifiedDate': 1788510964953, 'positionNumber': 1}]
original SS still `353019` name=`TEST ARTICLE - DO NOT USE FOR REAL DATA`
