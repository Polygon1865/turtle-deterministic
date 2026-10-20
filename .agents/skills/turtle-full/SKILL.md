---
name: turtle-full
description: Run the complete Turtle workflow for one stock: deterministic snapshot, DSH D1-D6 research, research audit/provenance, snapshot finalize, report and QA.
---

# Turtle Full Workflow

Use when the user asks for one-command complete analysis with both deterministic numbers and D1-D6 research.

This skill is an **agent workflow**, not a pure CLI command: the DSH model writes `research.json`; the CLI keeps all numbers and snapshots.

## Input

- Stock code: `600887`, `00700.HK`, `AAPL`
- Optional: `--rf`, `--rf-source`, `--currency`, `--research` seed path
- Optional: `--min-claims` (default 6), `--min-dimensions` (default 3)

## Workflow

### 1. Deterministic snapshot

```powershell
$env:TURTLE_OUTPUT_DIR = ".runs"
.\.venv\Scripts\python.exe -m turtlefw.cli run <code> --no-qa [user args]
```

This fetches once and writes:

```text
.runs/<code>/data_pack.md
.runs/<code>/analysis_report.md
.runs/<code>/snapshot/
```

Stop if this fails.

### 2. Research context

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli research-context `
  --snapshot .runs/<code>/snapshot `
  --out .runs/<code>/snapshot/research_context.json
```

Read the context. It includes metrics, facts, governance, coverage, data pack and PDF sections.

### 3. Write research.json

Write `.runs/<code>/snapshot/research.json`:

- D1–D6 claims;
- evidence with URL + verbatim quote (internal data evidence may use a `data:` id and quote);
- params;
- **do not write decisions by default**; the deterministic CLI ignores/rejects them unless the user explicitly asks for `--allow-research-decisions`;
- when explicitly enabled, a decision may only select a context candidate and must carry evidence;
- no raw numbers: `{{metric:id}}` / `{{fact:id}}`;
- missing data = `unknown`.

### 4. Audit quality

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli research-audit `
  --file .runs/<code>/snapshot/research.json `
  --metrics .runs/<code>/snapshot/metrics.json `
  --facts .runs/<code>/snapshot/evidence.json `
  --min-claims <min-claims> --min-dimensions <min-dimensions>
```

If it fails, fix `research.json`; do not weaken thresholds.

### 5. Provenance

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli research-provenance `
  --research .runs/<code>/snapshot/research.json `
  --snapshot .runs/<code>/snapshot `
  --provider dsh --model <model> `
  --out .runs/<code>/snapshot/research_provenance.json
```

### 6. Finalize without refetching

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli finalize `
  --snapshot .runs/<code>/snapshot `
  --research .runs/<code>/snapshot/research.json `
  --out .runs/<code>/snapshot_final `
  --min-claims <min-claims> --min-dimensions <min-dimensions> `
  --strict --html
```

Only add `--allow-research-decisions` when the user explicitly wants research
selections to change G/M/Q/AA/scenario; every such decision must have evidence.
Without the flag, the command fails rather than silently ignoring decisions.

This copies the frozen snapshot, renders the report with research, writes
`research_audit.json`, recomputes metrics/numeric audit and rebuilds the
manifest. It does **not** call the provider.

### 7. QA

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli qa <code> --write --allow-missing-qualitative
```

If QA fails, report the failed rows. Do not claim completion.

## Hard rules

- Deterministic data is fetched once, before research.
- research must not trigger a data refetch.
- Final report must be rendered from the frozen snapshot.
- This workflow is **research-only**: it does **not** run the PDF/qualitative
  Agent pass. Without `qualitative.json`, factor 1A/1B remain “未验证”.
  Use `/turtle-analysis` when full qualitative/PDF coverage is required.
- Do not write report numbers yourself.
- Do not fabricate evidence or decisions.
- If research cannot meet thresholds, stop and report the gap.
