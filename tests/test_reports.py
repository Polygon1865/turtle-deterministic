from turtlefw.data.reports import build_filename, validate_url


class TestValidateUrl:
    def test_official_a_share_domain(self):
        ok, _ = validate_url("http://static.cninfo.com.cn/finalpage/2026-04-30/1225259562.PDF")
        assert ok

    def test_hkex_domain(self):
        ok, _ = validate_url(
            "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0409/2026040901231.pdf"
        )
        assert ok

    def test_non_allowlisted_domain_rejected(self):
        ok, reason = validate_url(
            "http://rdfile.dzh.com.cn/new/dzh/tb_gg/2026/4/30/x.pdf"
        )
        assert not ok
        assert "Invalid URL" in reason

    def test_non_pdf_rejected(self):
        ok, _ = validate_url("https://stockn.xueqiu.com/report.html")
        assert not ok


def test_filename_uses_digits_and_year():
    assert build_filename("SH600887", "年报", "2025") == "600887_2025_年报.pdf"
    assert build_filename("00700.HK", "年报", 2025) == "00700_2025_年报.pdf"
