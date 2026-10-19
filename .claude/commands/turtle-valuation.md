Run a deterministic DCF/DDM/PE Band/PEG/PS valuation snapshot for: $ARGUMENTS

```powershell
python -m turtlefw.cli valuation $ARGUMENTS --rf <Rf%> --rf-source "<source>"
```

Rules:

- Read the output as **model output**, not a recommendation; assumptions (WACC, ERP, terminal growth, method weights) are printed.
- Do not change or re-compute the model values in prose; if you discuss them, quote them.
- For a full turtle analysis, run the `/turtle-analysis` command instead; this command only produces the valuation snapshot.
