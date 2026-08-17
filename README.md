# Junior 2.0

Junior 2.0 is the planned native-desktop evolution of Junior. Junior 1.x remains
the supported field-test product while 2.0 is built in parallel.

The governing boundary is:

> The model reads. The engine decides. The user remains in control.

This repository currently contains the starting structure and the first safety
check that confirms an extracted statement really appears in its source. It does
not yet contain the finished desktop interface, a working local AI model, job-site
connections, an upgrade process, or an installer.

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m junior
```

## How the code is organized

- `domain`: the basic records Junior understands, such as evidence and decisions.
- `application`: the steps Junior performs to complete a user task.
- `interpretation`: reads job postings and résumés and reports what they state.
- `scoring`: applies fixed, testable rules to produce recommendations.
- `collectors`: finds and retrieves public jobs from company sites.
- `catalog`: loads the versioned starter companies and layers user changes over
  them without altering the shipped list.
- `infrastructure`: connects replaceable technology such as databases and models.
- `desktop`: displays the native interface; it does not decide which jobs qualify.

Each AI-assisted task has a clearly defined input and output. All tasks initially
use one shared local model. If testing later shows that one task needs its own
specialized model, Junior can switch it without rebuilding scoring or the GUI.

Junior 2.0 will migrate the mature collectors and 50-company starter catalog from
Junior 1.x. Known companies use the catalog, while new or changed companies use
discovery to select an existing tested collector. The collectors are migrated
with their tests rather than rewritten.

Planning and design documents:

- [Product requirements](docs/PRODUCT_REQUIREMENTS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [AI interpretation contract](docs/INTERPRETATION_CONTRACT.md)
- [Evaluation and delivery plan](docs/EVALUATION_PLAN.md)
- [Decisions and open questions](docs/DESIGN_DECISIONS.md)
- [Concept-document traceability](docs/PDF_TRACEABILITY.md)
