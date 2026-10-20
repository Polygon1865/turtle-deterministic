Run the complete Turtle workflow for: $ARGUMENTS

This command combines deterministic numbers and D1-D6 research. All numbers must come from the CLI; the model only writes `research.json`.

Steps:

1. Create the deterministic snapshot without final QA:

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli run $ARGUMENTS --no-qa
```

If the user passed `--rf`, `--rf-source`, `--currency`, `--pdf-numbers`, `--evidence`, `--footnotes` or `--pdf-sections`, preserve those options on the `run` command.

2. Export research context from the snapshot:

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli research-context `
  --snapshot .runs/<code>/snapshot `
  --out .runs/<code>/snapshot/research_context.json
```

Use `output/<code>/snapshot` instead of `.runs/<code>/snapshot` when `TURTLE_OUTPUT_DIR` is not set.

3. Read the context and write `.runs/<code>/snapshot/research.json`:
   - D1–D6 claims with evidence;
   - params;
   - decisions only from candidates;
   - no raw numbers; only `{{metric:id}}` / `{{fact:id}}`;
   - missing data becomes `unknown`.

4. Audit and record provenance:

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli research-audit `
  --file .runs/<code>/snapshot/research.json `
  --metrics .runs/<code>/snapshot/metrics.json `
  --facts .runs/<code>/snapshot/evidence.json `
  --min-claims 6 --min-dimensions 3

.\.venv\Scripts\python.exe -m turtlefw.cli research-provenance `
  --research .runs/<code>/snapshot/research.json `
  --snapshot .runs/<code>/snapshot `
  --provider claude-code --model <current-model> `
  --out .runs/<code>/snapshot/research_provenance.json
```

5. Finalize from the frozen snapshot without refetching:

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli finalize `
  --snapshot .runs/<code>/snapshot `
  --research .runs/<code>/snapshot/research.json `
  --out .runs/<code>/snapshot_final `
  --min-claims 6 --min-dimensions 3 `
  --strict --html
```

6. Run QA:

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli qa <code> --write --allow-missing-qualitative
```

Rules:

- This workflow is **research-only**: it does not run the PDF/qualitative Agent
  pass. Without `qualitative.json`, factor 1A/1B remain “未验证”.
  Use `/turtle-analysis` when full qualitative/PDF coverage is required.
- Do not recompute or rewrite report numbers.
- Do not bypass research-audit, finalize, or QA.
- If research cannot meet the thresholds, stop and report the gap.
- Do not fabricate evidence, decisions, or parent/segment data.
