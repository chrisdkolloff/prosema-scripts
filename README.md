# Article Number Generator

Small Python tool for generating article numbers in an Excel workbook for a Swiss logistics workflow.

The day-to-day user should use the German instructions in `ANLEITUNG.md`.

## What It Does

`scripts/artikelnummern.py` reads an Excel workbook, assigns missing article numbers, and writes the result to an output file.

`scripts/replace_legacy_names.py` maps legacy Hauptgruppe/Untergruppe names to new labels.

Both scripts share the same job interface (`JOB_SPEC` + `run_job`) and are available from the desktop GUI.

Article numbers use this format:

```text
MMM.SSS.NNNN
```

- `MMM`: Hauptgruppe (resolved from name via Gruppenschlüssel)
- `SSS`: Unterartikelgruppe (resolved from name via Gruppenschlüssel)
- `NNNN`: running number counted separately per `MMM.SSS` group

The script is idempotent: existing valid article numbers are preserved and are never issued again.

## File Tree

```text
.
├── ANLEITUNG.md
├── README.md
├── beispiel/
│   └── input.xlsx
├── data/
│   └── gruppen.xlsx
├── gui/
│   ├── app.py
│   ├── job_spec.py
│   ├── registry.py
│   ├── runner.py
│   └── widgets.py
├── gui.command
├── requirements.txt
├── run.command
├── scripts/
│   ├── artikelnummern.py
│   └── replace_legacy_names.py
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

To run the GUI:

```bash
python -m gui
```

Or double-click `gui.command` on macOS.

To run scripts from the CLI:

```bash
python3 scripts/artikelnummern.py input.xlsx -o output_mit_artikelnummern.xlsx
python3 scripts/replace_legacy_names.py input.xlsx -o output_mit_neuen_namen.xlsx
```

For the non-technical local workflow, double-click `setup.command` once, then double-click `gui.command` each time.

## Adding a New Script to the GUI

1. Implement the business logic in `scripts/your_script.py`.
2. Add `run_job(params) -> RunResult` and `JOB_SPEC = _build_job_spec()` using types from `gui/job_spec.py`.
3. Register the job in `gui/registry.py`:

```python
from scripts.your_script import JOB_SPEC as your_script

JOBS = [artikelnummern, legacy_names, your_script]
```

The GUI builds the form and CLI flags automatically from `JOB_SPEC.fields`. No changes to `gui/app.py` are required.

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
