import json

from turtlefw import golden


def write_qualitative(tmp_path, code, moat="positive"):
    base = tmp_path / code
    base.mkdir(exist_ok=True)
    payload = {
        "modules": {
            "moat": {
                "judgment": moat,
                "confidence": "high",
                "evidence": [],
                "notes": "",
            }
        }
    }
    (base / "qualitative.json").write_text(json.dumps(payload), encoding="utf-8")


def test_template_roundtrip(tmp_path):
    path = golden.write_template(tmp_path / "golden.csv", ["600887.SH"])
    labels = golden.read_labels(path)
    assert len(labels) == 0  # blank rows are skipped
    rows = (tmp_path / "golden.csv").read_text(encoding="utf-8-sig").splitlines()
    assert len(rows) == 7  # header + 6 modules


def test_score_agreement(tmp_path):
    write_qualitative(tmp_path, "600887.SH", moat="positive")
    path = tmp_path / "golden.csv"
    path.write_text(
        "code,module,human_judgment,notes\n"
        "600887.SH,moat,positive,\n"
        "600887.SH,management,unknown,\n",
        encoding="utf-8-sig",
    )
    result = golden.score(golden.read_labels(path), root=tmp_path)
    assert result["total"] == 2
    assert result["matched"] == 2  # management absent -> unknown matches
    assert result["agreement"] == 1.0


def test_missing_file_reported(tmp_path):
    path = tmp_path / "golden.csv"
    path.write_text(
        "code,module,human_judgment,notes\n999999.SH,moat,positive,\n",
        encoding="utf-8-sig",
    )
    result = golden.score(golden.read_labels(path), root=tmp_path)
    assert result["total"] == 0
    assert result["missing"] == ["999999.SH"]
