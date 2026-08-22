# Junior 2.0

Junior 2.0 is the planned native-desktop evolution of Junior. Junior 1.x remains
the supported field-test product while 2.0 is built in parallel.

The governing boundary is:

> The model reads. The engine decides. The user remains in control.

This repository currently contains the starting structure, evidence checks, and a
native qualification-review experiment. It can display reviewed examples or ask
a separately installed Ollama model to read a pasted job posting. Model output
must pass Junior's strict record format and exact-quote checks before it appears.
The Junior 1.x scoring engine is not connected. This is not yet the finished
desktop application and does not contain migrated job-site connections, an
upgrade process, or an installer.

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m junior
```

Running `python -m junior` opens the native review experiment. Use the input picker
to paste a complete job posting or inspect reviewed examples. The current local
model trial expects Ollama at `http://127.0.0.1:11434` and defaults to
`qwen2.5:3b`. Ollama and the model are development prerequisites and are not
bundled with Junior. Start Ollama and install that model with:

```powershell
ollama pull qwen2.5:3b
```

The model only proposes qualifications and points to numbered source passages.
Junior supplies the exact evidence text and positions, validates the completed
record against the posting, and either displays it or rejects it. The model never
has to reproduce evidence wording. No recommendation or omission is produced.
Long sections are handled in small batches. Junior preserves evidence-verified
extraction when an optional semantic-review batch fails, and fixed source rules
recover clear “must” requirements. Junior can read several separately bounded
qualification sections from one posting, so an earlier requirement is not lost
when another qualifications heading appears later. It skips benefits,
compensation, company descriptions, application instructions, and legal material
between or after those sections. A second fixed check rejects headings, location metadata, recruiting
messages, and category claims that their quoted words do not support. Source
headings preserve required versus preferred qualifications, and separate
pick-one paths are accepted only when the posting explicitly describes complete
alternatives. Equivalent repeated requirements are shown once. If the local model
returns malformed JSON, Junior retries once with stricter format instructions.

### Importing an RC6 evaluation sample

After a successful RC6 scan, open **Reports** and select **Download all collected
postings** for that run. In Junior 2.0, select **Import RC6 raw scan** and choose
the downloaded ZIP. Junior reads that copied public-posting export; it does not
open or modify the RC6 database.

Junior selects up to 20 complete, nonduplicate postings with a repeatable mix of
clearance or work-authorization language, alternative qualification paths,
preferred sections, qualification headings, and general postings. Imported jobs
appear in the Input picker. The sample exists only in memory for the current
session and contains no profile, résumé, credential, or application data.

### Inspecting résumé extraction

Select **Import resume** in the test GUI to load a local PDF, DOCX, or plain-text
résumé. Junior displays the complete extracted text and sends it only to the
configured loopback Ollama model. **Interpret resume** shows only qualifications
that pass the résumé contract and exact-evidence validation. This experiment does
not persist the résumé. After both a résumé and job are validated, **Run shadow
match** performs a conservative, evidence-backed comparison and labels unresolved
items for review. It does not score, recommend, or omit the job.

Select **Run evaluation sample** to interpret every imported posting sequentially
without blocking the interface. Junior shows progress, labels successful rows
**Evidence verified**, retains results and safe failure reasons in memory, and lets
you activate a successful row
to inspect its exact evidence. **Stop after current posting** finishes the active
local-model request and then stops before the next posting. This batch runner is an
evaluation tool; its current one-at-a-time model speed is not the intended
large-scan production design.

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
