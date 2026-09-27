# Release procedure

## 0.4.0 release gate

1. Run `./scripts/verify.sh` on a clean checkout.
2. Run the public gold-study benchmark and confirm `23/23` checks pass.
3. Inspect the dashboard evidence panel and generated figures.
4. Confirm no credentials, signing keys, direct identifiers, absolute home
   paths, raw controlled data, or unlocked vault contents are tracked.
5. Confirm `LICENSE`, `CITATION.cff`, `CHANGELOG.md`, and the scientific claim
   boundary match the release.
6. Create a signed Git tag `v0.4.0` only after the release commit is final.
7. Upload the wheel, source archive, and their SHA-256 checksums to the release.
8. Archive the exact tag in a DOI-issuing repository if a citable research
   release is desired.

Publishing the code does not make the software clinically validated. Release
notes must describe the five remaining workflow cards as design contracts.
