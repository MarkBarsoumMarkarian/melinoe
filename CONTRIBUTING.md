# Contributing

Contributions are welcome when they preserve Melinoe's scientific-validity
contract.

## Development setup

```bash
uv sync --extra dev
cd ui && pnpm install && cd ..
./scripts/verify.sh
```

## Required for a change

- Add or update tests for every behavior change.
- Keep patient-level linkage and split boundaries explicit.
- Do not label internal resampling as external validation.
- Do not add a workflow as `validated` without an executable public benchmark,
  frozen expected results, failure injection, and a documented claim boundary.
- Never commit identifiable patient data, credentials, signing keys, unlocked
  vault contents, or raw controlled-access data.
- Run `./scripts/verify.sh` before requesting review.

Bug reports should include the Melinoe version, operating system, command or
screen involved, expected behavior, observed behavior, and a minimal
deidentified reproduction when possible.
