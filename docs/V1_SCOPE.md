# Version 1 scope

Melinoë 1.0 is one coherent multimodal release, developed through internal
integration gates rather than a sequence of unrelated miniature products.

## Supported data families

- Clinical and survival tables
- Bulk RNA and microRNA expression
- Single-cell RNA and spatial expression objects
- Somatic variants and copy-number calls
- Proteomic abundance matrices
- Digital pathology whole-slide images or derived tiles/features
- Cross-modal patient-linked studies

## Gold reference studies

Version 1 will ship five end-to-end, publicly reproducible studies:

1. Cohort-native bulk-transcriptomic survival synthesis — **reference validated**
2. Single-cell tumour-microenvironment characterization
3. Somatic alteration and expression integration
4. Pathology image classification with patient-locked evaluation
5. Multimodal clinical, molecular, and imaging integration

Each study must include a small test fixture, a documented public-data route,
expected outputs, a methods template, and at least one intentionally invalid
variant that OncoGuard must reject.

## Definition of done

- At least 25 documented OncoGuard rules with unit and integration tests
- Patient-level linkage and split enforcement across every modality
- Version-pinned workflow environments and checksummed inputs
- Local non-technical dashboard plus command-line interface
- Research Capsule import/export and provenance validation
- Offline execution for all bundled examples
- Reproducibility checks on at least three independent machines
- Failure-injection benchmark with published expected results
- Usability run by external researchers without developer intervention

## Explicit exclusions

- Clinical diagnosis or treatment recommendation
- Autonomous interpretation of identifiable patient records
- Reinventing raw read alignment or variant calling when validated community
  workflows already exist
- Claiming external or clinical validation from internal resampling
