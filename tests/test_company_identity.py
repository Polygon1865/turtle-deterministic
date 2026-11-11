from __future__ import annotations

from turtlefw.research import load_payload, unsupported_industry_terms


def _document(statement: str, *, quote: str = "公司披露的业务描述") -> object:
    return load_payload(
        {
            "evidence": [
                {
                    "id": "ev1",
                    "url": "https://example.com/a",
                    "quote": quote,
                }
            ],
            "claims": [
                {
                    "claim_id": "D1.1",
                    "dimension": "D1",
                    "statement": statement,
                    "judgment": "neutral",
                    "confidence": "high",
                    "evidence_ids": ["ev1"],
                }
            ],
        }
    )


def test_industry_claim_without_profile_is_flagged() -> None:
    document = _document("公司以物业管理及相关服务为主业，营收同比 {{metric:revenue.yoy}}")
    problems = unsupported_industry_terms(document, company_text="海底捞；餐饮 / Restaurants")
    assert problems == ["D1.1:物业"]


def test_industry_claim_supported_by_profile_passes() -> None:
    document = _document("公司以火锅餐饮连锁为主业")
    assert unsupported_industry_terms(document, company_text="海底捞；餐饮 / Restaurants") == []


def test_industry_claim_supported_by_its_own_evidence_passes() -> None:
    document = _document("公司以物业管理及相关服务为主业", quote="公司主营物业管理服务")
    assert unsupported_industry_terms(document, company_text="某公司") == []


def test_unknown_claims_are_not_checked() -> None:
    document = load_payload(
        {
            "claims": [
                {
                    "claim_id": "D1.9",
                    "dimension": "D1",
                    "statement": "缺少分部数据，无法确认物业管理收入占比",
                    "judgment": "unknown",
                    "confidence": "low",
                    "unknowns": ["分部数据"],
                }
            ]
        }
    )
    assert unsupported_industry_terms(document, company_text="海底捞") == []


def test_multiple_industries_are_reported_once_each() -> None:
    document = _document("公司以物业管理和半导体设备为主业")
    problems = unsupported_industry_terms(document, company_text="海底捞；餐饮")
    assert problems == ["D1.1:物业", "D1.1:半导体"]


def test_provider_phrasing_is_an_identity_assertion() -> None:
    document = _document("公司是领先的物业管理服务提供商，规模居前。")
    assert unsupported_industry_terms(document, company_text="海底捞；餐饮") == ["D1.1:物业"]


def test_industry_mention_as_a_driver_is_not_an_assertion() -> None:
    document = _document("地产销售下行压制家电需求，公司订单随之走弱。")
    assert unsupported_industry_terms(document, company_text="格力电器；家用电器") == []


def test_operation_nouns_are_not_industries() -> None:
    document = _document("供应链管理与租赁安排带来成本优势，调味品采购亦受益。")
    assert unsupported_industry_terms(document, company_text="某制造企业") == []
