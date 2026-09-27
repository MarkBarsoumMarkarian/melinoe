# Validated workflows

## Cohort-native survival synthesis 1.0.0

This is Melinoë's first executable gold-study workflow. It asks whether a
molecular feature has a transportable association with time-to-event outcome
across independent cancer cohorts without forcing incompatible assay platforms
onto one numeric scale.

### Scientific contract

- One eligible primary tumour per patient.
- Positive follow-up time and an explicit event/censoring indicator.
- Expression standardized within each cohort.
- Cohort-specific Cox proportional-hazards models with Efron ties.
- Proportional-hazards diagnostics and concordance reported per cohort.
- Random-effects synthesis with REML, Hartung-Knapp inference, heterogeneity,
  and a prediction interval.
- Leave-one-cohort-out sensitivity analysis.
- No cross-platform ComBat or pooled expression matrix.
- A subgroup difference requires an interaction test, not two separate
  significance tests.
- Target expression, prognostic transportability, and clinical utility remain
  separate claims.

### Executed reference benchmark

The frozen benchmark is the corrected PDAC/GPRC5A v2 analysis:

- TCGA-PAAD, CPTAC-PAAD, GSE85916, GSE57495, and GSE62452.
- 481 eligible patients and 304 observed deaths.
- Pooled hazard ratio per within-cohort SD: 1.162.
- 95% confidence interval: 0.942 to 1.434.
- 95% prediction interval: 0.800 to 1.689.
- I-squared: 28.15%.
- Five survival cohorts plus paired tumour/adjacent, laser-captured
  cancer/stroma, and matched RNA/protein evidence.

The validation receipt checks 23 frozen quantities, including an exact replay
through the generic user-data engine, and hashes every generated table and
figure. A changed upstream parser, cohort definition, result, or output file is
therefore visible. Checked-in evidence is under
`validation/gold_studies/pdac_gprc5a_v2/`.

Only aggregate validation evidence is published. Row-level source and derived
records are consumed locally during the benchmark replay and then excluded
from the release tree.

### Public inputs

- NCBI GEO: GSE85916, GSE57495, GSE62452, and GSE164665.
- cBioPortal Datahub revision
  `0cc9138746c08b304f8dac92c31983e0ef44af1d` for TCGA-PAAD and CPTAC-PAAD.
- Every downloaded source is checked against the frozen MD5 recorded by the
  workflow; a checksum mismatch aborts execution.

### Reproduction

Run the reusable engine on a CSV containing `cohort`, `patient_id`, `time`,
`event`, and `expression`. Time must be positive, event must be 0/1, every
patient must occur once per cohort, and every cohort must contain at least 20
patients and 10 events:

```bash
uv run melinoe workflow run bulk-transcriptomics cohort-table.csv \
  --output cohort-results
```

Re-run the frozen public benchmark:

```bash
uv run melinoe workflow benchmark bulk-transcriptomics \
  --workspace validation-run \
  --cache /path/to/public-data-cache
```

To fetch missing public inputs explicitly:

```bash
uv run melinoe workflow benchmark bulk-transcriptomics \
  --workspace validation-run \
  --allow-downloads
```

Independently verify an existing result directory:

```bash
uv run melinoe workflow verify-results bulk-transcriptomics \
  validation-run/results
```

### Claim boundary

This is a computational reference validation of a workflow implementation. It
is not clinical validation of GPRC5A, proof of therapeutic benefit, or evidence
that any new user's analysis is correct. The reference result itself is
inconclusive for a transportable stand-alone survival association.
