"""Vendor labels must tell the truth about where the numbers came from."""

from __future__ import annotations

from turtlefw.report.format import data_source_label
from turtlefw.types import Market


def test_tushare_label_for_a_share_and_hk():
    assert data_source_label(Market.SH) == "Tushare Pro"
    assert data_source_label(Market.SZ) == "Tushare Pro"
    assert data_source_label(Market.HK) == "Tushare Pro"


def test_us_label_names_sec_and_yfinance():
    label = data_source_label(Market.US)
    assert "SEC" in label
    assert "yfinance" in label
    assert "Tushare" not in label


def test_labels_are_stable_strings():
    # Snapshot hashes cover rendered output; the label must not depend on state.
    assert data_source_label(Market.US) == data_source_label(Market.US)
