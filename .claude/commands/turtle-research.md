Generate a validated D1-D6 research.json for a Turtle snapshot using the DSH model.

Snapshot: $ARGUMENTS

Steps:
1. `python -m turtlefw.cli research-context --snapshot <snapshot> --out <snapshot>/research_context.json`
2. Read the context.
3. Write `<snapshot>/research.json` using `{{metric:id}}` / `{{fact:id}}`; never raw numbers.
4. Validate:
   `python -m turtlefw.cli research-audit --file <snapshot>/research.json --metrics <snapshot>/metrics.json --facts <snapshot>/evidence.json --min-claims 6 --min-dimensions 3`
5. Fix and re-run until pass; missing data becomes `unknown`.
6. Do not write the final report. The Python CLI renders the report.
