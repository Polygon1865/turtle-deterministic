from decimal import Decimal

import pytest

from turtlefw.pdf.extract import (
    detect_scale,
    extract_cash_bridge_from_pages,
    extract_from_pages,
    extract_pdf,
    extract_sbc_from_pages,
    parse_number,
)


def _build_pdf(lines: list[str]) -> bytes:
    """Minimal one-page Helvetica PDF (enough for pdfplumber text tests)."""
    escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
    stream_parts = ["BT", "/F1 11 Tf", "72 740 Td"]
    for index, line in enumerate(escaped):
        if index:
            stream_parts.append("0 -18 Td")
        stream_parts.append(f"({line}) Tj")
    stream_parts.append("ET")
    stream = "\n".join(stream_parts).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    return bytes(out)


class TestParseNumber:
    def test_comma_and_decimal(self):
        assert parse_number("1,234.56") == Decimal("1234.56")

    def test_parentheses_negative(self):
        assert parse_number("(1,234)") == Decimal("-1234")

    def test_placeholder(self):
        assert parse_number("—") is None
        assert parse_number("不适用") is None

    def test_scale(self):
        assert parse_number("12", Decimal("1000")) == Decimal("12000")

    def test_detect_scale(self):
        assert detect_scale("单位：人民币千元") == Decimal("1000")
        assert detect_scale("单位：百万元") == Decimal("1000000")


class TestExtract:
    def test_six_items_from_statements(self):
        pages = [
            (
                1,
                "合并利润表\n"
                "营业收入 1,234,567 1,000,000\n"
                "归属于母公司股东的净利润 (123,456) (100,000)",
            ),
            (
                2,
                "合并现金流量表\n"
                "经营活动产生的现金流量净额 234,567\n"
                "购建固定资产、无形资产和其他长期资产支付的现金 100,000",
            ),
            (
                3,
                "合并资产负债表\n"
                "资产总计 9,999,999\n"
                "归属于母公司所有者权益合计 5,000,000",
            ),
        ]
        items = {item["item"]: item for item in extract_from_pages(pages, year=2025)}
        assert set(items) == {
            "revenue",
            "net_income",
            "ocf",
            "capex",
            "equity",
            "total_assets",
        }
        assert items["revenue"]["value"] == "1234567.00"
        assert items["net_income"]["value"] == "-123456.00"
        assert items["ocf"]["value"] == "234567.00"
        assert items["capex"]["value"] == "100000.00"
        assert items["total_assets"]["value"] == "9999999.00"
        assert items["revenue"]["page"] == "1"

    def test_page_unit_is_applied(self):
        pages = [(1, "单位：人民币千元\n合并利润表\n营业收入 1,234 1,000")]
        item = extract_from_pages(pages, year=2025)[0]
        assert item["item"] == "revenue"
        assert item["value"] == "1234000.00"

    def test_working_capital_items_from_balance_sheet(self):
        pages = [
            (
                1,
                "合并资产负债表\n"
                "应收账款 1,100\n"
                "存货 2,100\n"
                "合同负债 3,100\n"
                "预收款项 1,400\n"
                "预付款项 1,500",
            )
        ]
        items = {item["item"]: item for item in extract_from_pages(pages, year=2025)}
        assert items["accounts_receiv"]["value"] == "1100.00"
        assert items["inventory"]["value"] == "2100.00"
        assert items["contract_liab"]["value"] == "3100.00"
        assert items["adv_receipts"]["value"] == "1400.00"
        assert items["prepayments"]["value"] == "1500.00"

    def test_label_and_value_on_next_line(self):
        pages = [(1, "合并资产负债表\n资产总计\n9,999,999")]
        item = {x["item"]: x for x in extract_from_pages(pages, year=2025)}["total_assets"]
        assert item["value"] == "9999999.00"

    def test_real_pdf_roundtrip(self):
        pytest.importorskip("pdfplumber")
        import tempfile
        from pathlib import Path

        path = Path(tempfile.gettempdir()) / "turtle-pdf-extract-test.pdf"
        path.write_bytes(
            _build_pdf(
                [
                    "Consolidated income statement",
                    "Revenue 1,234,567 1,000,000",
                    "Net profit attributable to shareholders (123,456) (100,000)",
                    "Consolidated statement of cash flows",
                    "Net cash generated from operating activities 234,567",
                    "Purchase of property, plant and equipment 100,000",
                    "Consolidated statement of financial position",
                    "Total assets 9,999,999",
                    "Total equity attributable to shareholders 5,000,000",
                ]
            )
        )
        try:
            items = {item["item"]: item for item in extract_pdf(path, year=2025)}
        finally:
            path.unlink(missing_ok=True)
        assert items["revenue"]["value"] == "1234567.00"
        assert items["net_income"]["value"] == "-123456.00"
        assert items["total_assets"]["value"] == "9999999.00"
        assert items["revenue"]["page"] == "1"


class TestCashBridge:
    def test_hk_indirect_bridge_is_scaled(self):
        pages = [
            (
                1,
                "Consolidated Statement of Cash Flows\n"
                "RMB’Million\n"
                "Cash generated from operations 43(a) 347,751 304,705\n"
                "Income tax paid (44,699) (46,184)\n"
                "Net cash flows generated from operating activities 303,052 258,521\n"
                "Purchase of/prepayments for property, plant and equipment (87,482) (62,927)\n"
                "Purchase of/prepayments for intangible assets (25,399) (26,394)",
            ),
            (
                2,
                "43 NOTE TO CONSOLIDATED STATEMENT OF CASH FLOWS\n"
                "RMB’Million\n"
                "Profit for the year 229,801 196,467\n"
                "Depreciation of property, plant and equipment 32,799 27,332\n"
                "Amortisation of intangible assets 33,229 28,881\n"
                "Changes in working capital:\n"
                "Accounts receivable (1,242) (1,048)\n"
                "Deferred revenue 6,143 16,533\n"
                "Cash generated from operations 347,751 304,705",
            ),
        ]
        bridge = extract_cash_bridge_from_pages(pages)
        assert bridge["net_profit"] == "229801000000.00"
        assert bridge["depreciation_amortisation"] == "66028000000.00"
        assert bridge["cash_generated_from_operations"] == "347751000000.00"
        assert bridge["ocf"] == "303052000000.00"
        assert bridge["capex"] == "112881000000.00"

    def test_a_share_direct_cashflow_has_no_indirect_bridge(self):
        pages = [
            (
                1,
                "合并现金流量表\n"
                "销售商品、提供劳务收到的现金 1,000\n"
                "经营活动产生的现金流量净额 300\n"
                "购建固定资产、无形资产和其他长期资产支付的现金 100",
            )
        ]
        assert extract_cash_bridge_from_pages(pages) == {}

    def test_sbc_is_extracted(self):
        pages = [
            (
                1,
                "RMB’Million\n"
                "Equity-settled share-based compensation expenses 25,660 20,702",
            )
        ]
        assert extract_sbc_from_pages(pages) == {
            "sbc": "25660000000.00",
            "page": "1",
        }
