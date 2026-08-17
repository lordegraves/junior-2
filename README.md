# Junior 2.0

Junior 2.0 is the planned native-desktop evolution of Junior. Junior 1.x remains
the supported field-test product while 2.0 is built in parallel.

The governing boundary is:

> The model reads. The engine decides. The user remains in control.

This repository currently contains the architectural skeleton and the first
evidence-validation seam. It does not yet contain a production GUI, local
model, collector implementation, database migration, or installer.

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m junior
```

## Package boundaries

- `domain`: stable evidence, fact, profile, and decision types.
- `application`: use cases and interfaces required by those use cases.
- `interpretation`: internal document interpretation behind a constrained port.
- `scoring`: deterministic policy and recommendation behavior.
- `collectors`: bounded collection and company-discovery contracts.
- `infrastructure`: replaceable database, networking, and model adapters.
- `desktop`: native presentation code; it must not own product rules.

See [architecture](docs/ARCHITECTURE.md) and
[decisions](docs/DESIGN_DECISIONS.md).
