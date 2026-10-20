Run the local Turtle Investment Framework analysis for: $ARGUMENTS

## Hard rules

- Every number in the final report must come from the local CLI (`turtle analyze/pack/report`), never from the LLM.
- The LLM only writes `qualitative.json` (evidence-backed) and optional `narrative.md`; the CLI writes `data_pack.md` and `analysis_report.md`.
- Read `prompts/agent/coordinator.md` first, then execute the phases in order. Use the state file to resume.

## Phases

```powershell
# 0. state
python -m turtlefw.cli state <code> --init

# 1. data pack (Tushare/yfinance)
python -m turtlefw.cli state <code> --phase data
python -m turtlefw.cli pack <code>

# 2. PDF (optional; skip with a warning if unavailable)
#    Find the annual report via WebSearch, then:
python -m turtlefw.cli fetch-report --url "<PDF_URL>" --stock-code <digits> --report-type 年报 --year <FY> --save-dir output/<code>
python -m turtlefw.cli pdf --pdf output/<code>/<file>.pdf --output output/<code>/pdf_sections.json --verbose
python -m turtlefw.cli pdf-footnotes --sections output/<code>/pdf_sections.json --output output/<code>/footnotes.json
python -m turtlefw.cli pdf-numbers --pdf output/<code>/<file>.pdf --year <FY> --output output/<code>/reported_numbers.json
# review reported_numbers.json (value/page/confidence), then:
python -m turtlefw.cli audit <code> --doc output/<code>/reported_numbers.json --threshold 1 --write output/<code>/qualitative.json
python -m turtlefw.cli pack <code> --pdf-numbers output/<code>/reported_numbers.json
python -m turtlefw.cli state <code> --phase report_pdf

# 3. qualitative JSON
python -m turtlefw.cli qualitative <code> --init
# fill output/<code>/qualitative.json per prompts/agent/phase3_qualitative.md
python -m turtlefw.cli verify <code> --write
python -m turtlefw.cli qualitative <code> --check
python -m turtlefw.cli state <code> --phase qualitative

# 4. deterministic report + optional narrative
python -m turtlefw.cli report <code> --pdf-numbers output/<code>/reported_numbers.json --save-snapshot output/<code>/snapshot
# write output/<code>/narrative.md per phase4_report.md, then:
python -m turtlefw.cli narrative <code> --file output/<code>/narrative.md
python -m turtlefw.cli state <code> --phase report

# 5. delivery gate
python -m turtlefw.cli qa <code> --write
```

If `qa` fails, return to the corresponding phase; never bypass it. If PDF or qualitative data is missing, report the unknown items explicitly instead of guessing.

## Deliver

- `output/<code>/analysis_report.md` (final)
- `output/<code>/qualitative.json` + evidence URLs
- `output/<code>/run_state.json`
- one-line conclusion: 买入 / 观察 / 排除 + reason
