from turtlefw.facts import ResearchClaim
from turtlefw.research import ResearchDocument, quality
from turtlefw.research_grading import grade_document, grade_evidence, grade_url


def test_grade_url_recognises_primary_and_media_hosts():
    assert grade_url("https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0102/1.pdf") == "A"
    assert grade_url("https://www.cninfo.com.cn/new/disclosure/detail?stockCode=000651") == "A"
    assert grade_url("https://www.reuters.com/business/retail-consumer/x") == "B"
    assert grade_url("https://finance.yahoo.com/quote/06862.HK") == "B"
    assert grade_url("https://example.com/a") == "C"
    assert grade_url("") == "unknown"
    assert grade_url("not a url") == "unknown"


def test_grade_evidence_marks_data_and_pdf():
    assert grade_evidence({"source_type": "data", "url": ""}) == "data"
    assert (
        grade_evidence({"source_type": "pdf", "quote": "营收", "page": 12}) == "A"
    )
    assert grade_evidence({"url": "https://stcn.com/article/1"}) == "B"
    assert grade_evidence({"quote": "无来源"}) == "unknown"


def test_grade_document_counts_and_flags_high_claims_without_external():
    claims = (
        ResearchClaim(
            claim_id="D1.a",
            dimension="D1",
            statement="数据包复述",
            judgment="positive",
            confidence="high",
            evidence_ids=("ev-data",),
        ),
        ResearchClaim(
            claim_id="D1.b",
            dimension="D1",
            statement="有媒体支撑",
            judgment="positive",
            confidence="high",
            evidence_ids=("ev-web",),
        ),
        ResearchClaim(
            claim_id="D2.a",
            dimension="D2",
            statement="低置信判断",
            judgment="neutral",
            confidence="low",
            evidence_ids=("ev-data",),
        ),
    )
    evidence = {
        "ev-data": {"id": "ev-data", "source_type": "data", "quote": "数据包"},
        "ev-web": {
            "id": "ev-web",
            "url": "https://stcn.com/article/1",
            "quote": "证券时报报道",
        },
    }
    grades = grade_document(claims, evidence)
    assert grades.counts == {"data": 1, "B": 1}
    assert grades.external == 1
    assert grades.high_without_external == ("D1.a",)
    assert grades.summary() == "B 1、data 1"


def test_quality_reports_evidence_grades():
    document = ResearchDocument(
        claims=(
            ResearchClaim(
                claim_id="D1.business_model",
                dimension="D1",
                statement="主营为空调",
                judgment="positive",
                confidence="high",
                evidence_ids=("ev1",),
            ),
        ),
        evidence={
            "ev1": {
                "id": "ev1",
                "url": "https://www.cninfo.com.cn/new/disclosure/detail",
                "quote": "公司主营空调",
            }
        },
    )
    result = quality(document)
    assert result["evidence_grades"] == {"A": 1}
    assert result["external_evidence"] == 1
    assert result["high_without_external"] == []
