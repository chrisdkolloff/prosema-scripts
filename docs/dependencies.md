# Dependencies

Runtime dependencies are declared with open ranges in `pyproject.toml`.
Exact versions for install (local and Azure App Service) live in `requirements.txt`.

## `requirements.txt` is generated

Do **not** hand-edit `requirements.txt`. Regenerate it with [pip-tools](https://pip-tools.readthedocs.io/) on **Python 3.12**:

```bash
python3.12 -m pip install pip-tools
pip-compile --strip-extras --output-file requirements.txt pyproject.toml
```

Then ensure the file ends with a lone `.` line so `pip install -r requirements.txt` still installs this project (the pins above already satisfy its dependencies).

Do not pass `--generate-hashes` — Oryx builds are less predictable with hashes.

`pip-compile` without `--upgrade` keeps existing pins. Use `--upgrade` (or `--upgrade-package NAME`) only when you intend to bump versions.

## Desktop / legacy packages

Former desktop and Streamlit dependencies (`customtkinter`, `streamlit`, `pandas`) were removed from the project. They are not declared as extras and must not be installed in production.
