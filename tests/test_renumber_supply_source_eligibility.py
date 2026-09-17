"""Renumber eligibility: supply source warning vs manual alias hard block."""

from __future__ import annotations

from app.article_renumber_eligibility import (
    RenumberPrefetch,
    evaluate_eligibility,
    has_manual_alias,
    has_live_supply_source_alias,
)


def test_manual_alias_is_hard_block_supply_source_alias_is_not():
    ctx = RenumberPrefetch(
        manual_alias_weclapp_ids={"wc-manual"},
        live_supply_source_alias_weclapp_ids={"wc-ss"},
    )
    assert has_manual_alias(weclapp_id="wc-manual", article_number="1.2.3", ctx=ctx)
    assert not has_manual_alias(weclapp_id="wc-ss", article_number="1.2.3", ctx=ctx)
    assert has_live_supply_source_alias(weclapp_id="wc-ss", article_number="1.2.3", ctx=ctx)


def test_evaluate_eligibility_ok_with_live_supply_source_no_db():
    ctx = RenumberPrefetch(
        category_id_to_pair={"cat": ("110", "020")},
        tools_haupt={"110": "Test"},
        tools_unter={("110", "020"): "Dest"},
        stock_article_ids=set(),
        movement_article_ids=set(),
        document_article_ids=set(),
    )
    article = {
        "articleNumber": "110.010.0001",
        "articleCategoryId": "cat",
        "supplySources": [{"articleSupplySourceId": "ss-1"}],
        "primarySupplySourceId": "ss-1",
    }
    result = evaluate_eligibility(
        article=article,
        weclapp_id="wc-1",
        ctx=ctx,
        db=None,
    )
    assert result.ok
    assert result.checks["no_alias_row"] is True
    assert result.supply_source_warning == ()
