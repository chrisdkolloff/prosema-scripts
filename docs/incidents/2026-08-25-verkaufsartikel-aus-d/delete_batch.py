"""One-off: delete junk sales articles created from empty column W.

Only articles created after the 2026-08-25 20:20 import AND listed in
junk-sales-articles.txt are deleted. Aborts on the first unexpected API error.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.weclapp.client import WeclappClient, WeclappError
from scripts.weclapp.config import load_config

ZURICH = ZoneInfo("Europe/Zurich")
CUTOFF = datetime(2026, 8, 25, 20, 20, 0, tzinfo=ZURICH)
CUTOFF_MS = int(CUTOFF.timestamp() * 1000)
DIR = Path(__file__).resolve().parent
JUNK_FILE = DIR / "junk-sales-articles.txt"
LOG_FILE = DIR / "deletion-log.jsonl"
ALREADY_DELETED = {"03002000"}


def load_junk_numbers() -> list[str]:
    numbers: list[str] = []
    for line in JUNK_FILE.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        numbers.append(text)
    return numbers


def load_done() -> set[str]:
    done = set(ALREADY_DELETED)
    if not LOG_FILE.is_file():
        return done
    for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("status") in {"deleted", "already_gone"}:
            done.add(row["article_number"])
    return done


def log(row: dict) -> None:
    row = dict(row)
    row.setdefault("at", datetime.now(ZURICH).isoformat())
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()


def main() -> int:
    junk = set(load_junk_numbers())
    done = load_done()
    client = WeclappClient(load_config())

    created: list[dict] = []
    for article in client.iter_pages(
        "article",
        params={
            "createdDate-gt": CUTOFF_MS,
            "properties": "id,articleNumber,createdDate,name",
        },
    ):
        created.append(article)

    extras = [
        a for a in created if str(a.get("articleNumber") or "") not in junk
    ]
    targets = [
        a
        for a in created
        if str(a.get("articleNumber") or "") in junk
        and str(a.get("articleNumber") or "") not in done
    ]
    print(
        f"created after cutoff={len(created)} extras={len(extras)} "
        f"to_delete={len(targets)} already_done={len(done)}"
    )
    if extras:
        print("REFUSING: articles in import window not on junk list:")
        for a in extras[:20]:
            print(" ", a.get("articleNumber"), a.get("id"), a.get("name"))
        return 2

    for i, article in enumerate(targets, start=1):
        number = str(article.get("articleNumber") or "")
        article_id = str(article.get("id") or "")
        if not number or not article_id:
            print("UNEXPECTED: missing number or id", article)
            return 3
        try:
            client.request("DELETE", f"/article/id/{article_id}")
        except WeclappError as exc:
            if exc.status_code == 404:
                log(
                    {
                        "article_number": number,
                        "id": article_id,
                        "status": "already_gone",
                    }
                )
                print(f"{i}/{len(targets)} {number} already gone")
                continue
            log(
                {
                    "article_number": number,
                    "id": article_id,
                    "status": "error",
                    "http": exc.status_code,
                    "detail": str(exc.detail),
                }
            )
            print(f"ABORT {number} id={article_id} HTTP {exc.status_code} {exc.detail}")
            return 4
        log(
            {
                "article_number": number,
                "id": article_id,
                "status": "deleted",
                "createdDate": article.get("createdDate"),
            }
        )
        if i == 1 or i % 50 == 0 or i == len(targets):
            print(f"{i}/{len(targets)} deleted {number}")
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
