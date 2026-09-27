# Version 2 analysis protocol

## Working question

Is GPRC5A consistently associated with overall survival across independent PDAC
cohorts, and which tissue compartment contributes its measured expression?

The study does not assume a paradox, a subtype reversal or a functional switch.

## Primary analysis

1. Include one primary tumour per patient with positive overall-survival time
   and an explicit censoring indicator. For TCGA, require the deposited tumour
   type to be explicitly `Pancreas Adenocarcinoma, Ductal Type`; do not treat
   every specimen in the broader PAAD collection as PDAC.
2. Analyse each cohort on its native platform. Do not merge expression matrices
   and do not use cross-platform ComBat.
3. Transform GPRC5A to a within-cohort z score so hazard ratios describe a
   one-standard-deviation increase within that cohort.
4. Fit cohort-specific Cox proportional-hazards models.
5. Check proportional-hazards assumptions and report concordance.
6. Combine log hazard ratios with a random-effects model; report prediction
   intervals and heterogeneity in addition to the pooled estimate.
7. Perform leave-one-cohort-out influence analysis.

## Secondary analyses

- Estimate adjusted associations only where age, stage or grade have adequate
  completeness. Do not pretend covariate-adjusted models are identical across
  cohorts with different metadata.
- In TCGA, test a continuous GPRC5A-by-subtype interaction. Separate
  within-subtype p values are not evidence of interaction.
- Compare paired tumour and adjacent non-tumour expression in GSE62452.
- Compare paired laser-captured cancer and stroma compartments in GSE164665,
  with patient blocking.
- Assess matched CPTAC RNA-protein correlation using explicit patient/sample
  joins. Treat this as measurement concordance, not survival validation.

## Excluded claims

- No alive-versus-dead classification.
- No role-state machine-learning classifier.
- No causal gemcitabine claim without treatment start times and an appropriate
  time-dependent design.
- No claim that absence of coding mutations proves epigenetic regulation.
- No clinical biomarker or therapeutic-response claim.

## Reproducibility requirements

- Every input receives a source URL, byte count and checksum.
- Cohort flow tables list all exclusions.
- Probe-to-gene mappings are explicit and auditable.
- Results are written as plain CSV files and figures as publication-ready PNG
  files.
- Random seeds are fixed wherever sampling is used.
