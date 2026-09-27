# Melinoë

Melinoë is a local-first, multimodal cancer-research environment. It connects
patients, specimens, assays, endpoints, and analysis splits in one explicit
project graph, then audits that graph for threats to scientific validity before
a workflow is allowed to run.

This repository is the clean successor to the original MelinoëOS ISO prototype.
The operating-system image is now a delivery target rather than the scientific
contribution.

**Release:** 0.4.0 public research-software release candidate.

## What works today

- A typed OncoGraph project manifest covering clinical, transcriptomic,
  genomic, proteomic, single-cell, spatial, and pathology data.
- Deterministic OncoGuard checks for broken linkage, patient leakage, reused
  files, endpoint integrity, platform mixing, batch confounding, small test
  cohorts, and direct-identifier risk.
- A local API and interactive dashboard.
- A deliberately flawed multimodal demo project that exercises the guardrails.
- Export of a Research Capsule containing the manifest, audit, provenance, and
  human-readable summary.
- Project Vault orchestration backed by a signed, pinned encrypted filesystem
  engine; passphrases never enter command history or API requests.
- Network-denied workflow execution with project-scoped write access.
- Hardware-aware execution profiles and reproducible research-state snapshots.
- A tamper-evident, hash-chained local activity ledger.
- Encrypted Ed25519 signing keys and immutable workflow locks that require
  validation evidence plus OCI and SIF digests.
- Signed, versioned offline knowledge packs with per-file integrity checks.
- Atomic control-plane checkpoints with non-destructive manifest rollback.
- Validity-gated Slurm/Apptainer handoff bundles and RO-Crate 1.3 metadata.
- An executable cohort-native survival-synthesis workflow validated against a
  five-cohort, 481-patient PDAC reference study with 23 frozen result checks.

## Quick start

```bash
uv sync --extra dev
uv run melinoe serve
```

Open `http://127.0.0.1:8787`. The bundled demo loads automatically.

For a one-command local launch, run `./scripts/run.sh`. If port 8787 is used by
another application, pass a different port, for example `./scripts/run.sh 8788`.
The complete quality gate is `./scripts/verify.sh`.

Run the scientific audit or export a capsule from the command line:

```bash
uv run melinoe audit examples/multimodal_demo/project.json
uv run melinoe capsule examples/multimodal_demo/project.json --output demo-capsule.zip
uv run melinoe snapshot examples/multimodal_demo/project.json --output research-state.json
```

Install the verified Project Vault engine, then create and unlock a vault:

```bash
./scripts/install-vault-engine.sh
uv run melinoe vault create /path/to/project.vault
uv run melinoe vault open /path/to/project.vault
uv run melinoe vault close /path/to/project.vault
```

Run a command with no network and no write access outside its project directory:

```bash
uv run melinoe isolate /path/to/project -- Rscript analysis.R
```

Every isolated run appends to `.melinoe/ledger.jsonl`. Verify it with
`uv run melinoe ledger verify /path/to/project/.melinoe/ledger.jsonl`.

Create an offline signing identity and verify a signed workflow lock:

```bash
uv run melinoe keys create --private signing.pem --public signing.pub
uv run melinoe workflow-lock sign workflow-lock.json --key signing.pem
uv run melinoe workflow-lock verify signed-workflow-lock.json
```

The `knowledge`, `checkpoint`, and `hpc-handoff` commands build and verify
offline database packs, restore control-plane state, and create portable Slurm
execution bundles. Run `uv run melinoe COMMAND --help` for their explicit
inputs. HPC handoffs refuse to build when OncoGuard has blockers, the workflow
signature fails, the SIF checksum is absent, or a network-denied workflow lacks
a cluster-approved isolation command.

Inspect and reproduce the first gold-study validation:

```bash
uv run melinoe workflow list
uv run melinoe workflow run bulk-transcriptomics cohort-table.csv --output results
uv run melinoe workflow benchmark bulk-transcriptomics \
  --workspace melinoe-benchmark \
  --cache /path/to/reference-cache
```

Omit `--cache` and add `--allow-downloads` to retrieve the checksum-pinned
public inputs. Downloads are opt-in; the runner is offline by default. See
`docs/VALIDATED_WORKFLOWS.md` for the full scientific contract and result
boundaries.

Run the test suite:

```bash
uv run pytest
```

Build the dashboard after changing frontend code:

```bash
cd ui
pnpm install
pnpm build
```

## Current boundary

Melinoë is research software. It is not a medical device, diagnostic system,
or substitute for statistical, pathological, or clinical review. A passing
OncoGuard audit means that the implemented checks did not identify a known
problem; it is not proof that an analysis is valid.

The scientific constitution and version-one scope are in `docs/`.

## Citation and license

Citation metadata are provided in `CITATION.cff`. Melinoë is released under
the MIT License. The validated workflow is research software and its reference
benchmark is computational validation, not clinical validation.
