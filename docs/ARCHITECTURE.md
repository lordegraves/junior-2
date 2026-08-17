# Junior 2.0 Architecture

Junior 2.0 is a native desktop application built on shared Python code. The
desktop interface, command-line tools, and scheduled scans all use the same rules.
This prevents the same job from receiving different treatment depending on how
the scan was started.

```text
Native desktop interface
        |
Shared tasks and rules
        |
        +-- find companies and collect public jobs
        +-- read job postings and résumés
        +-- confirm that extracted facts have evidence
        +-- score jobs using fixed rules
        +-- save data, audits, applications, and diagnostics
```

## Keeping responsibilities separate

The code is arranged in layers so technology can change without changing Junior's
rules:

1. `domain` defines the information Junior understands without knowing how the
   GUI, model, database, or job sites work.
2. `application` defines the user tasks and what outside services those tasks need.
3. `interpretation`, `scoring`, `collectors`, and `infrastructure` provide those
   services without taking ownership of product rules.
4. `desktop` displays information and accepts user actions. It does not score jobs.
5. `bootstrap` is the single assembly point that selects the actual database,
   model, and other replaceable technology when Junior starts.

Anything reported by a model must pass evidence checks before the scoring rules
can use it. The model cannot score jobs, save a company source, browse wherever it
wants, or create a final recommendation.

## First working path

The initial slice deliberately performs only this flow:

```text
source document -> proposed fact -> confirm exact evidence -> safe review
```

This small path establishes the safety boundary before selecting the final AI
software, model, database layout, or job-collector migration plan.

## Responsibility boundaries

The interpretation service reads job postings and résumés. It turns different
wording into consistent facts—for example, treating “work from home” and “remote”
as the same workplace arrangement. This is called normalization. It may identify
requirements, alternative ways to qualify, compensation, location, employment
type, and other stated facts. It must preserve uncertainty and point to the text
supporting each fact. It cannot fill in missing information, score, recommend, or
omit a job.

The decision engine uses fixed rules that give the same answer for the same facts.
This is what “deterministic” means. It owns preferences, exclusions, scoring,
ranking, recommendations, omissions, and audit explanations. Junior may omit a
job only when evidence proves it violates a user setting. Unclear, conflicting,
unreadable, or missing information cannot become a rejection.

Company discovery follows the same rule. The model may examine limited public
information and choose from a list of actions Junior already knows how to perform.
Regular code performs and verifies the action. The model cannot browse freely,
run commands, create new executable collectors, or declare that a source works.

## How Junior records extracted facts

Before choosing a model, we must define the exact record format the model must
produce. Developers call this a schema. Every fact records what it means, its
consistent value, which version of the document it came from, exactly where the
supporting text appears, the model's confidence, and one of these states:

- `stated`: the document clearly says it.
- `not_stated`: the document does not provide it.
- `ambiguous`: the wording has more than one reasonable meaning.
- `conflicting`: different parts of the document disagree.
- `unreadable`: Junior could not reliably read the relevant material.
- `not_applicable`: the fact does not apply to this document or job.

Résumé matches follow the same rule. Junior must show both the job requirement
and the résumé text that supports the match. If a posting offers different ways
to qualify, Junior keeps those choices separate instead of incorrectly requiring
the applicant to satisfy all of them.

The first detailed contract covers job and résumé qualifications. Requirements
are stored as groups containing one or more acceptable paths. Every item in a path
must be satisfied, while satisfying any one path satisfies the group. This keeps
“bachelor's plus seven years, or master's plus five years” as two real choices.
The model-facing format rejects extra fields, including recommendations the model
has no authority to make. See [What the AI Must Tell Junior](INTERPRETATION_CONTRACT.md).

## Two evidence checks

Every extracted fact passes two separate checks before scoring:

1. Evidence exists: the quoted text or document area is real and comes from the
   correct version of the source.
2. Evidence supports the claim: the cited words actually mean what Junior says
   they mean. Developers call this semantic validation.

The second check may eventually use another carefully tested model. Even then,
it only verifies meaning; it cannot make the job decision. A failed check sends
the fact to a safer non-AI method or to the user for review.

## How Junior finds a company's job system

Junior gives discovery a limited bundle of safe public information: URLs,
redirects, page details, links, scripts, structured page data, network results,
and clues left by known recruiting platforms. It may propose an action from a
preapproved list, such as following an official careers link, checking a known
public job endpoint, testing how later result pages are loaded, or requesting one
more limited bundle of information.

Junior—not the model—performs the action. It confirms that the results are real
jobs, that full job details can be read, and that all result pages are reached.
Limits on attempts, web requests, time, and memory prevent endless searching.
Direct recognition of a known recruiting platform remains the fastest method.

## Reusing Junior 1.x collectors and companies

Junior 2.0 reuses the mature Junior 1.x collector behavior instead of rebuilding
every recruiting-platform connection. Each collector and its existing tests move
into the 2.0 collector area. A small common interface converts its results into
2.0 job records. Connections to 1.x web pages, database records, settings, or
global state are removed during migration, but source-specific behavior remains.

The same 50-company starter catalog ships as a versioned, read-only data file.
User additions, corrections, selections, and source-health results are stored
separately. When Junior shows the effective catalog, local changes take priority
without modifying the shipped file. An update can therefore add a new catalog
version without erasing user-owned choices.

The full path is: use a known catalog entry when available; otherwise discover
the recruiting platform; select a migrated collector; collect public jobs; and
confirm real jobs, complete details, and every results page before saving it.

## Resource and fallback behavior

Document reading and company discovery are separate tasks. They may share a model,
use different models, or work without a model. Junior limits memory use and reads
large documents or sites in smaller pieces. If a model is unavailable, takes too
long, uses too many resources, or fails a check, Junior uses its fixed parsing
rules or asks the user. Less capable hardware may mean less automation, but never
weaker evidence or safety rules.

## Model routing boundary

Job-posting reading, résumé reading, and company discovery each have a clearly
defined input, output, instruction set, and test suite. An internal model router—
a small switchboard—chooses which installed model handles each task. Initially,
all tasks use one shared local model, and Junior loads only what it currently needs.

Junior manages this assignment internally. If testing proves that a specialized
model is meaningfully better, one task can move to it without changing the rest of
the product. Common document handling stays in one place so we do not maintain
multiple copies of the same code.

## Security, privacy, and persistence

Junior treats everything it downloads as untrusted. Text on a web page or résumé
cannot grant permission, reveal secrets, or make Junior run a tool. Junior can
contact only approved destinations, validates every model response against the
required format, removes private information from logs, and places only explicitly
safe information in diagnostic packages.

Junior will define how long it keeps original documents, extracted facts, user
corrections, model versions, and decision history. Database upgrades are versioned
and all-or-nothing so a failed change does not leave half-updated data. Importing
from Junior 1.x is backed up, checked, and reversible. Upgrading never depends on
deleting the working 1.x data.
