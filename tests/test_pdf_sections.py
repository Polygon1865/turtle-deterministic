from turtlefw.pdf import preprocessor


def test_find_section_pages_scores_matches():
    pages = [
        (1, "目录 管理层讨论与分析"),
        (2, "公司简介"),
        (10, "第三节 管理层讨论与分析 经营情况"),
        (11, "财务报表附注"),
    ]
    result = preprocessor.find_section_pages(
        pages, {"MDA": ["管理层讨论与分析"], "P2": ["公司简介"]}
    )
    assert 10 in result["MDA"]
    assert 2 in result["P2"]


def test_extract_section_context_returns_page_text():
    pages = [(9, "封面"), (10, "管理层讨论与分析正文"), (11, "续页")]
    contexts = preprocessor.extract_section_context(
        pages, {"MDA": [10]}, {"MDA": ["管理层讨论与分析"]}, buffer_pages=0
    )
    assert "管理层讨论与分析正文" in contexts["MDA"]


def test_missing_section_is_empty():
    pages = [(1, "目录"), (2, "公司简介")]
    result = preprocessor.find_section_pages(pages, {"MDA": ["管理层讨论与分析"]})
    assert result["MDA"] == []
