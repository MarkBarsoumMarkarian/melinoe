# Melinoë scientific constitution

These rules are product requirements. Interface convenience cannot override
them.

## 1. The unit of reasoning is the research question

Melinoë starts with a biological or clinical research objective, not a tool.
Every workflow must declare its estimand or prediction target, eligible cohort,
unit of analysis, endpoint, and validation plan.

## 2. Patient identity is structural

Files and samples are not independent merely because they have different names.
Every specimen and assay must resolve to a patient or to an explicitly declared
non-patient experimental unit. Splits are enforced at the patient level.

## 3. Assay context cannot be erased

Platform, batch, specimen type, processing history, and measurement scale are
first-class data. Harmonization may model these differences; it may not pretend
they never existed.

## 4. Exploration and confirmation are different states

Discovery, internal validation, locked testing, and independent external
replication are represented separately. Reusing a locked test cohort changes
its status and must be recorded.

## 5. A workflow may refuse to run

Blockers such as patient leakage, broken linkage, ambiguous endpoints, or an
unavailable locked test set are not dismissible warnings. Overrides require a
written justification in the provenance record.

## 6. Provenance is part of the result

Every exported result records inputs, checksums where available, software and
container versions, parameters, seeds, rule findings, overrides, and execution
timestamps.

## 7. Claims cannot outrun evidence

Melinoë distinguishes technical replication, internal validation, external
validation, biological support, and clinical utility. Reports must state which
level was actually reached.

## 8. Privacy is local by default

No patient data leave the workstation without an explicit export action.
Direct identifiers are rejected from ordinary research manifests. Controlled
data and derived shareable artifacts remain visibly separated.

## 9. Deterministic rules govern scientific safety

An assistant may explain, suggest, or draft. It may not silently change data,
waive a blocker, invent a citation, or replace a deterministic validation rule.

## 10. Passing is not proof

OncoGuard reduces preventable errors. It does not certify truth, clinical
validity, regulatory compliance, or fitness for patient care.
