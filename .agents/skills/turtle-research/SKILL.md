---
name: turtle-research
description: Generate a validated D1-D6 research.json for an existing Turtle snapshot using the DSH model, then run the project research gates. Does not write the final report or numbers.
---

# Turtle Research Skill

Use when the user asks for deep research, D1-D6 qualitative analysis, industry/moat/management/MD&A research, or a v2-style report that needs a `research.json`.

The DSH model writes only `research.json`. Python writes the final report and all numbers.

## Workflow

1. Identify the snapshot directory, usually `output/<code>/snapshot` or `.runs/<code>/snapshot`.
2. Export context:

```powershell
python -m turtlefw.cli research-context --snapshot <snapshot> --out <snapshot>/research_context.json
```

3. Read `research_context.json`. It contains:
   - `metrics`: computed metric ids and displays;
   - `facts`: PDF/SEC evidence rows with ids;
   - `pdf_sections`: P2/P3/P4/P6/P13/MDA/SUB text;
   - `data_pack`: rendered data pack.
4. Write `research.json` using the schema below.
5. Validate:

```powershell
python -m turtlefw.cli research-audit `
  --file <snapshot>/research.json `
  --metrics <snapshot>/metrics.json `
  --facts <snapshot>/evidence.json `
  --min-claims 6 --min-dimensions 3
```

6. Fix only `research.json` and re-run until it passes, or mark gaps as `unknown`.
7. Continue with:

```powershell
python -m turtlefw.cli report <code> --snapshot <snapshot> --research <snapshot>/research.json
```

8. Run QA.

## Hard rules

- Never write a raw number in `claim.statement`, `param.value` or `decision.reason`.
  Use `{{metric:<id>}}` or `{{fact:<id>}}`.
- Non-unknown claims require evidence with URL + quote.
- Decisions may only select from provided candidates.
- If data is missing, use `judgment: "unknown"` and list the gap.
- Do not write `analysis_report.md` or any numeric table.
- Do not calculate R/GG/II/floor/price; the Python engine does that.

## research.json schema

```json
{
  "evidence": [
    {
      "id": "ev1",
      "url": "https://example.com/report",
      "quote": "verbatim source text",
      "source_type": "web",
      "page": ""
    }
  ],
  "claims": [
    {
      "claim_id": "D2.1",
      "dimension": "D2",
      "statement": "护城河来自品牌与渠道，R={{metric:r}}",
      "judgment": "positive",
      "confidence": "high",
      "evidence_ids": ["ev1"],
      "unknowns": []
    }
  ],
  "params": [
    {
      "param_id": "thesis.core",
      "label": "核心论点",
      "value": "R={{metric:r}}；护城河稳定",
      "dimension": "D2",
      "evidence_ids": ["ev1"],
      "confidence": "medium"
    }
  ],
  "decisions": [
    {
      "decision_id": "g",
      "metric_id": "g",
      "selected": "1.15",
      "candidates": ["0.85", "1.15", "1.50"],
      "reason": "Capex/D&A 处于中等区间",
      "evidence_ids": ["ev1"]
    }
  ]
}
```

## D1-D6 coverage

- D1 business model / unit economics / capital intensity / cyclicality
- D2 industry map / entry barriers / CR4 / moat / competitors / monitoring KPIs
- D3 external environment / policy / cycle / structural risk
- D4 management / governance / capital allocation / related-party
- D5 MD&A / guidance credibility / operating drivers
- D6 ownership / parent / subsidiaries / minority / pledge/repurchase if available

Prefer fewer, high-evidence claims over many unverifiable claims.
