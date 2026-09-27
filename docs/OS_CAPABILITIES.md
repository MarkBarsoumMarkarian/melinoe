# Melinoë OS capabilities

Melinoë's application can be installed elsewhere. The operating system exists
to make the following guarantees the default and to expose their state in one
place.

## Project Vault

Controlled and sensitive projects require encryption at rest. Melinoë uses
gocryptfs forward mode rather than implementing cryptography. The encrypted
directory contains encrypted names and file contents; the mounted workspace is
the plaintext view. Passphrases are read interactively and are never passed in
process arguments, stored in the manifest, or accepted by the web API.
The encrypted `gocryptfs.conf` must be backed up separately from the data.

The initial release deliberately does not claim protection from a compromised
running operating system. An unlocked vault is available to the logged-in user.
Backups and recovery-key handling remain the researcher's responsibility.

## Contained execution

The `melinoe isolate` command launches analysis through bubblewrap. The host
filesystem is read-only, only the selected project directory is writable, `/tmp`
is ephemeral, and the network namespace is removed unless the researcher makes
an explicit exception. Each start and finish is written to the project ledger.

This is process containment, not a virtual machine and not a defense against a
kernel compromise.

## Research-state snapshots

A snapshot records canonical hashes for the project manifest and OncoGuard
report, installed package versions, a deterministic random seed, the derived
privacy policy, detected compute hardware, and every declared data object. With
`--hash-data`, Melinoë reads each source file and checks its observed checksum.

## Tamper-evident ledger

Each ledger event includes the preceding event hash and its own canonical
content hash. Verification detects edits, removals in the middle of the chain,
reordering, and corruption. This is not a signature or remote timestamp: an
attacker able to replace the entire project ledger can create a new chain.

## Enforcement boundary

OncoGuard blockers prevent workflow eligibility. Data-sensitivity policy governs
encryption, network, and export defaults. Workflow-lock signing, RO-Crate
packaging, offline knowledge verification, checkpoints, and HPC handoff are
implemented. The cohort-native survival-synthesis workflow is executable and
reference-validated; the other five cancer workflow cards remain design
contracts and do not pretend to execute validated analyses.

## Signed workflow locks

Melinoë stores signing keys as passphrase-encrypted PKCS8 files and uses
Ed25519 signatures. A workflow lock records validation evidence, required
modalities, parameters, resources, random seed, network policy, OCI manifest
digest, SIF checksum, and SBOM checksum. Mutable image tags are insufficient.

## Offline knowledge registry

Knowledge packs record the upstream database version, retrieval timestamp,
source URL, license, and checksum of every file. Packs are verified before
installation and stored under a content-addressed path. Archive path traversal,
symlinks, duplicate members, undeclared files, bad signatures, and checksum
mismatches are rejected.

## Checkpoints and HPC handoff

Checkpoints capture the manifest, audit, and research state without copying raw
assay data. Restoring a checkpoint first preserves the current manifest. HPC
handoffs are Slurm/Apptainer bundles; they do not submit jobs themselves. They
refuse scientific blockers and cryptographic or container-integrity gaps.
