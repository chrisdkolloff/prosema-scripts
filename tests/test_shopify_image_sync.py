"""SharePoint → Shopify image sync helpers."""

from __future__ import annotations

from app.microsoft_graph import (
    DriveFileEntry,
    GraphError,
    encode_sharing_url,
    graph_error_user_message,
)
from app.shopify_image_sync import (
    SyncStats,
    build_remote_catalog,
    job_failure_message,
    normalize_image_filename,
    primary_error_detail,
    run_sync_job,
)
from app.shopify_media_alt import media_alt_text, parse_source_filename


def test_encode_sharing_url_is_stable_prefix():
    encoded = encode_sharing_url("https://contoso.sharepoint.com/:f:/s/x/abc")
    assert encoded.startswith("u!")
    assert "/" not in encoded
    assert "+" not in encoded


def test_encode_sharing_url_matches_graph_spec():
    url = (
        "https://prosemaag.sharepoint.com/:f:/s/ProsemaAG/"
        "IgAkoDB4D9_dQIY-jVWEZdBhAR4cZzI-Dd8v6du6OxdvPq0?e=U0XkMu"
    )
    encoded = encode_sharing_url(url)
    assert encoded.startswith("u!")
    assert encoded.count("=") == 0


def test_normalize_macos_duplicate_drawing_name():
    assert normalize_image_filename("010.010.0010-1 2.JPG") == "010.010.0010-2.JPG"


def test_build_remote_catalog_groups_by_article():
    files = [
        DriveFileEntry(name="010.010.0010-1.JPG", drive_id="d", item_id="a", size=1),
        DriveFileEntry(name="010.010.0010-2.JPG", drive_id="d", item_id="b", size=1),
        DriveFileEntry(name="not-a-sku.jpg", drive_id="d", item_id="c", size=1),
    ]
    catalog, ignored = build_remote_catalog(files)
    assert ignored == ["not-a-sku.jpg"]
    bundle = catalog["010.010.0010"]
    assert [item.index for item in bundle.ordered_files] == [1, 2]
    assert bundle.ordered_files[0].kind == "color"
    assert bundle.ordered_files[1].kind == "drawing"


def test_media_alt_roundtrip():
    alt = media_alt_text(
        filename="010.010.0010-1.JPG",
        article_number="010.010.0010",
        kind="color",
    )
    assert parse_source_filename(alt) == "010.010.0010-1.JPG"


def test_graph_error_user_message_includes_api_detail():
    exc = GraphError(
        "SharePoint-Ordner konnte nicht geöffnet werden (403)",
        status_code=403,
        detail={"error": {"code": "accessDenied", "message": "Access denied"}},
    )
    text = graph_error_user_message(exc)
    assert "403" in text
    assert "Access denied" in text


def test_job_failure_message_puts_detail_first():
    result = {
        "error_detail": "SharePoint-Ordner konnte nicht geöffnet werden (403) — Access denied",
        "message": "Vorschau (Ergänzen): 0 hochgeladen, … 1 Fehler.",
    }
    text = job_failure_message(result)
    assert text.startswith("SharePoint-Ordner")
    assert "Vorschau" in text


def test_run_sync_job_includes_error_detail_on_graph_failure(monkeypatch):
    def fake_sync(**_kwargs):
        stats = SyncStats()
        stats.errors = 1
        stats.messages.append("Graph sagt nein (401)")
        return stats

    monkeypatch.setattr("app.shopify_image_sync.run_sharepoint_shopify_sync", fake_sync)
    result = run_sync_job({"sharepoint_url": "https://example.com/x"})
    assert result["error_detail"] == "Graph sagt nein (401)"


def test_primary_error_detail_prefers_fehler_lines():
    stats = SyncStats()
    stats.messages = ["OK x", "FEHLER 010.010.0010: timeout"]
    assert primary_error_detail(stats) == "FEHLER 010.010.0010: timeout"


def test_job_handler_registered():
    from app.jobs import HANDLERS

    assert "shopify_sharepoint_image_sync" in HANDLERS
