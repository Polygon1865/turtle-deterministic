---
name: turtle-analysis
description: Run the local deterministic Turtle Investment Framework analysis (data pack, evidence-backed qualitative JSON, report, QA gate) on an A-share or HK stock.
---

# Turtle Analysis Skill

Use when the user asks for a full 龟龟/四因子 analysis, a valuation, or a screening follow-up.

## Entry point

`prompts/agent/coordinator.md` is the authoritative phase specification. The
CLI is the only source of numbers.

## Workflow

1. `turtle state <code> --init`
2. `turtle pack <code>` → `data_pack.md`
3. Optional PDF: `turtle fetch-report` + `turtle pdf` → `pdf_sections.json`
4. `turtle qualitative <code> --init`; fill with evidence; `turtle verify`; `turtle qualitative --check`
5. `turtle report <code> --save-snapshot output/<code>/snapshot`; optional `narrative.md`; `turtle narrative`
6. `turtle qa <code> --write` (must pass)

## Constraints

- Do not invent or recompute numbers; narrative numbers must come from CLI artifacts.
- Every non-`unknown` qualitative judgment needs an http(s) URL plus a verbatim quote.
- If a phase fails, degrade explicitly (e.g. no PDF) and record a warning; never bypass `qa`.
- The final report is `output/<code>/analysis_report.md`.
