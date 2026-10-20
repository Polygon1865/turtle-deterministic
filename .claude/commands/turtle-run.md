Run the complete deterministic Turtle workflow for: $ARGUMENTS

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli run $ARGUMENTS
```

This command performs:

```text
state init
→ pack
→ report
→ save snapshot
→ numeric audit
→ QA
```

Rules:

- If a stage fails, report the failing stage and stop; do not bypass it.
- Do not recompute or rewrite numbers in prose.
- If `--research` is provided, it is validated and frozen into the snapshot.
- If `qa` fails, report the failed rows; do not claim completion.
- Output paths use `TURTLE_OUTPUT_DIR` / `output` exactly as the CLI prints.
