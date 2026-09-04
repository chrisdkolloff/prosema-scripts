from app.transform.live_fetch import LiveFetchResult, fetch_live_articles, group_prefix
from app.transform.scope import ScopeCandidate
from tests.test_transform_apply import CatalogFake, _article


def test_group_prefix_only_when_shared():
    assert group_prefix(["020.010.0010", "020.020.0020"]) == "020"
    assert group_prefix(["020.010.0010", "050.010.0010"]) is None
    assert group_prefix(["Winkel-1"]) is None


def test_id_in_short_page_marks_missing_gone_without_per_id_get():
    present = _article("1", "999.999.001", "Alte Folie")
    missing = _article("2", "999.999.002", "Alte Folie")
    client = CatalogFake([present, missing])
    client.omit_from_list.add("2")
    result = fetch_live_articles(
        client,
        [
            ScopeCandidate("999.999.001", "1"),
            ScopeCandidate("999.999.002", "2"),
        ],
    )
    assert isinstance(result, LiveFetchResult)
    assert set(result.articles) == {"1"}
    assert result.gone_ids == {"2"}
    assert "/article/id/2" not in client.get_calls
