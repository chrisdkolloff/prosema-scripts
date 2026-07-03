# Article Number Generator

Small Python tool for generating article numbers in an Excel workbook for a Swiss logistics workflow.

The day-to-day user should use the German instructions in `ANLEITUNG.md`.

## What It Does

`scripts/artikelnummern.py` reads `input.xlsx`, assigns missing article numbers, and writes `output_mit_artikelnummern.xlsx`.

Article numbers use this format:

```text
MMM.SSS.NNNN
```

- `MMM`: Hauptgruppe from Excel column F
- `SSS`: Unterartikelgruppe from Excel column G
- `NNNN`: running number counted separately per `MMM.SSS` group

The script is idempotent: existing valid article numbers are preserved and are never issued again.

## File Tree

```text
.
├── ANLEITUNG.md
├── README.md
├── beispiel/
│   └── input.xlsx
├── requirements.txt
├── run.command
├── scripts/
│   └── artikelnummern.py
└── setup.command
```

Generated local files:

```text
.venv/
input.xlsx
output_mit_artikelnummern.xlsx
```

## Developer Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

To run manually:

```bash
python3 scripts/artikelnummern.py
```

For the non-technical local workflow, double-click `setup.command` once, then double-click `run.command` each time.

## GitHub Setup

Recommended: create a private repository.

If you have the GitHub CLI:

```bash
gh repo create prosema-artikelnummern --private --source=. --remote=origin --push
```

Manual GitHub path:

1. Create a new private repository on github.com.
2. Then run:

```bash
git remote add origin git@github.com:YOUR-USER/prosema-artikelnummern.git
git branch -M main
git push -u origin main
```
