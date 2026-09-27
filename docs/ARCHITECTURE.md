# Architecture

## Product layers

1. **OncoGraph** is the canonical patient–specimen–assay–endpoint data model.
2. **OncoGuard** evaluates deterministic scientific-validity rules against an
   OncoGraph manifest.
3. **Workflow Fabric** will execute version-pinned workflows while preserving
   the manifest and audit state.
4. **Project Vault** encrypts controlled project files and names at rest.
5. **Execution Boundary** gives workflows project-scoped writes, ephemeral
   temporary storage, and a network-denied namespace by default.
6. **Research State** binds manifest, audit, data checksums, packages, hardware,
   policy, and random seed into one portable record.
7. **Evidence Engine** will attach versioned biological and clinical knowledge
   without converting associations into unsupported claims.
8. **Research Capsule** exports the manifest, provenance, audit, research state,
   integrity index, methods, and
   selected results as a portable artifact.
9. **Workbench UI** provides a non-technical local interface over the same API
   used by the command line.
10. **Integrity Plane** signs validated workflow locks, verifies offline
    knowledge packs, creates non-destructive checkpoints, and exports
    validity-gated HPC handoffs.

## Dependency direction

```text
Workbench UI --> Local API --> Application services
                                 |--> OncoGraph
                                 |--> OncoGuard
                                 |--> Privacy policy
                                 |--> System capability probe
                                 |--> Research-state snapshot
                                 |--> Capsule exporter
                                 `--> Workflow Fabric (next)

Command line --> Project Vault / Sandbox / Audit ledger
```

The core has no dependency on the user interface or a particular Linux image.

## Execution model

The workbench runs directly through Python. Commands launched through
`melinoe isolate` already receive filesystem and network containment through
bubblewrap. Production workflows will add immutable containers pinned by digest
inside that boundary. A full offline edition will prefetch those images. The
Melinoë ISO will contain the workbench and runtime, but the same project must
run on an existing Linux host with degraded guarantees reported explicitly.

## Data boundary

The manifest stores linkage and metadata. Large assay files remain external and
are referenced by relative or controlled absolute paths. Research Capsules may
include manifests and small derived artifacts without automatically copying
sensitive or multi-gigabyte source data.

Controlled and sensitive projects are assigned encryption-required policies.
The Project Vault uses gocryptfs for streaming, per-file encryption rather than
loading complete omics or imaging datasets into application memory.

## Integrity and portability

Workflow images are referenced by OCI SHA-256 digest, never mutable tags. A
workflow lock becomes signable only after its maturity is `validated` and at
least one validation-evidence identifier is declared. Offline Ed25519
signatures cover canonical workflow or knowledge-pack metadata; encrypted
private keys never enter the API.

Research Capsules and HPC handoffs contain RO-Crate 1.3 JSON-LD metadata. HPC
handoffs additionally bind the Slurm resource request, workflow signature,
research state, OCI digest, and exact SHA-256 of the staged Apptainer SIF.
Network-denied workflows cannot be exported without an explicit
cluster-approved isolation command.
