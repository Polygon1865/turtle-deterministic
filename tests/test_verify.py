from turtlefw.qualitative import Evidence, Judgment, Qualitative
from turtlefw.verify import (
    check_qualitative,
    downgrade,
    failing_modules,
    normalize,
    quote_score,
)


def test_exact_quote_scores_one():
    assert quote_score("公司实现营业收入 100 亿元", "公司实现营业收入") == 1.0


def test_whitespace_and_width_normalized():
    assert normalize("Ａ　Ｂ\nC") == "ABC"


def test_fuzzy_quote_above_threshold():
    page = "报告期内公司实现营业收入一百亿元，同比增长百分之十。"
    quote = "报告期内公司实现营业收入一百亿元"
    assert quote_score(page, quote) >= 0.9


def test_missing_quote_scores_zero():
    assert quote_score("完全无关的页面内容", "营业总收入") == 0.0


def build_qualitative(judgment="positive", quote="营业收入一百亿元"):
    return Qualitative(
        items={
            "moat": Judgment(
                module="moat",
                judgment=judgment,
                confidence="high",
                evidence=(Evidence("https://x.test/a", quote, "document", "p.1"),),
            )
        }
    )


def test_check_ok():
    checks = check_qualitative(
        build_qualitative(), fetch=lambda url: "公司实现营业收入一百亿元，同比增长。"
    )
    assert checks[0].status == "ok"
    assert failing_modules(checks) == set()


def test_check_quote_missing():
    checks = check_qualitative(build_qualitative(), fetch=lambda url: "无关内容")
    assert checks[0].status == "quote_missing"
    assert failing_modules(checks) == {"moat"}


def test_check_unreachable():
    def boom(url):
        raise RuntimeError("timeout")

    checks = check_qualitative(build_qualitative(), fetch=boom)
    assert checks[0].status == "unreachable"


def test_downgrade_marks_unknown():
    payload = {
        "modules": {
            "moat": {
                "judgment": "positive",
                "confidence": "high",
                "evidence": [],
                "notes": "",
            }
        }
    }
    result = downgrade(payload, {"moat"})
    assert result["modules"]["moat"]["judgment"] == "unknown"
    assert "事实校验" in result["modules"]["moat"]["notes"]
    assert payload["modules"]["moat"]["judgment"] == "positive"
