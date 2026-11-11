"""C1: layout fixtures for the PDF statement extractor.

These pages are hand-written imitations of the layouts seen in the 2025 annual
reports: labels wrapped over two lines, a value sandwiched between the two
halves of a label, a balance sheet continuing on the next page, a calendar year
sitting where a value is expected, and bank-specific equity wording. They keep
the regression covered without shipping the PDFs themselves.
"""

from __future__ import annotations

from turtlefw.pdf.extract import extract_from_pages


def _items(pages: list[tuple[int, str]]) -> dict[str, str]:
    return {row["item"]: row["value"] for row in extract_from_pages(pages, year=2025)}


def test_wrapped_capex_label_takes_following_value() -> None:
    items = _items(
        [
            (
                1,
                "合并现金流量表\n"
                "购建固定资产、无形资产和其他长期资\n"
                "产支付的现金 3,127,594,916.41 2,000,000,000.00\n"
                "经营活动产生的现金流量净额 5,000,000,000.00\n",
            )
        ]
    )

    assert items["capex"] == "3127594916.41"
    assert items["ocf"] == "5000000000.00"


def test_wrapped_equity_label_with_value_between_halves() -> None:
    items = _items(
        [
            (
                1,
                "合并资产负债表\n"
                "归属于母公司所有者权\n"
                "253,959,253,909.07 242,011,315,120.60\n"
                "益合计\n"
                "资产总计 500,000,000,000.00\n",
            )
        ]
    )

    assert items["equity"] == "253959253909.07"


def test_balance_label_stitched_across_page_break() -> None:
    items = _items(
        [
            (1, "合并资产负债表\n归属于母公司所有者权益\n"),
            (
                2,
                "（或股东权益）合计 244,637,811,032.00 200,000,000,000.00\n"
                "资产总计 500,000,000,000.00\n",
            ),
        ]
    )

    assert items["equity"] == "244637811032.00"
    assert items["total_assets"] == "500000000000.00"


def test_calendar_year_is_not_a_statement_value() -> None:
    items = _items(
        [
            (
                1,
                "合并资产负债表\n"
                "归属于母公司所有者权益合计\n"
                "2025年12月31日\n"
                "资产总计 10,000,000,000.00\n",
            )
        ]
    )

    assert "equity" not in items


def test_bank_equity_alias() -> None:
    items = _items(
        [
            (
                1,
                "合并资产负债表\n"
                "归属于本行股东权益合计 3,000,000,000,000.00 2,800,000,000,000.00\n"
                "资产总计 20,000,000,000,000.00\n",
            )
        ]
    )

    assert items["equity"] == "3000000000000.00"


def test_other_statement_title_closes_balance_page() -> None:
    items = _items(
        [
            (
                1,
                "合并利润表\n"
                "归属于母公司所有者权益合计 100,000,000.00 90,000,000.00\n"
                "营业收入 50,000,000.00 40,000,000.00\n",
            )
        ]
    )

    assert "equity" not in items
    assert items["revenue"] == "50000000.00"
