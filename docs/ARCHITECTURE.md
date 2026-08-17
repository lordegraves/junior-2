# Junior 2.0 Architecture

Junior 2.0 is built as a native presentation layer over shared Python services.
The desktop interface, CLI, scheduled operation, and packaging must compose the
same application use cases rather than implementing separate product rules.

```text
Native desktop UI
        |
Application use cases
        |
        +-- bounded collectors and company discovery
        +-- internal document interpretation
        +-- evidence validation
        +-- deterministic scoring and policy
        +-- persistence, audit, tracker, and diagnostics
```

## Dependency direction

Dependencies point inward:

1. `domain` imports no application, GUI, model, storage, or collector code.
2. `application` depends on domain types and defines replaceable ports.
3. `interpretation`, `scoring`, `collectors`, and `infrastructure` implement or
   support those ports.
4. `desktop` calls application use cases and owns presentation only.
5. `bootstrap` is the only place allowed to choose concrete adapters.

Interpretation output must pass evidence validation before deterministic policy
can consume it. A model cannot call the scoring engine, persist a collector,
issue arbitrary network requests, or create a final recommendation.

## First vertical slice

The initial slice deliberately performs only this flow:

```text
source document -> proposed fact -> exact evidence validation -> safe review
```

It establishes the boundary we need before selecting a GUI toolkit, inference
runtime, model, database schema, or collector migration strategy.

## Responsibility boundaries

The interpretation service extracts normalized facts from job postings and
resumes. It may identify sections, requirements, alternative qualification
paths, compensation, location, employment type, and other stated facts. It
must preserve uncertainty and cite evidence; it must not infer absent facts,
score a job, recommend an action, or omit a job.

The deterministic engine owns user preferences, hard exclusions, scoring,
ranking, recommendations, omissions, and audit explanations. An omission is
allowed only when evidence proves a configured exclusion. Ambiguous,
conflicting, unreadable, or absent information must not become rejection.

Company discovery is similarly bounded. It gathers public evidence, proposes
only predefined typed actions, and leaves network execution and acceptance to
deterministic code. A model cannot browse freely, run arbitrary code, create a
collector, or declare success.

## Normalized evidence model

Schema design precedes model selection. Every extracted fact must include its
kind, normalized value, source-document identity and version, exact supporting
span or equivalent locator, confidence, and one of these explicit states:

- `stated`
- `not_stated`
- `ambiguous`
- `conflicting`
- `unreadable`
- `not_applicable`

Resume evidence uses the same discipline so a claimed match can be traced to
both the job requirement and the user's resume. Alternative requirement paths
must remain alternatives rather than being flattened into one impossible list.

## Two-stage evidence validation

Interpretation output passes two independent gates before scoring:

1. Evidence existence: the cited text or document region exists and is tied to
   the correct source version.
2. Semantic support: the cited evidence actually supports the normalized fact.

The second gate may eventually use a separately evaluated verifier, but its
result remains structured evidence rather than a decision. Failed validation
routes the fact to review or fallback behavior.

## Company discovery loop

Discovery receives a bounded evidence packet containing safe public URLs,
redirects, page metadata, links, scripts, structured data, network observations,
and known-platform fingerprints. It returns a proposal from a predefined action
catalog such as follow an official careers link, inspect a known public endpoint,
test a pagination pattern, or request another bounded evidence packet.

Junior executes the action, validates actual job records and depth/pagination,
and either accepts the source or returns typed failure evidence. Iteration,
request, time, and memory limits prevent an unbounded agent loop. Direct
deterministic platform detection remains the fast path.

## Resource and fallback behavior

Interpretation and company discovery are separate services and may use different
models or no model. Work is queued and memory-bounded; large documents and sites
are processed in chunks. If a model is unavailable, times out, exceeds limits,
or fails validation, Junior falls back to deterministic parsing or user review.
Lower capability may reduce automation, never evidence requirements or safety.

## Security, privacy, and persistence

All downloaded material is untrusted input. Prompts, HTML, documents, and model
output cannot grant authority, access secrets, or invoke tools. Network access is
allowlisted and bounded, outputs are schema-validated, logs are redacted, and
diagnostics contain only deliberately safe fields.

Original documents, normalized facts, user corrections, model/runtime versions,
and decision traces require explicit retention rules. Persistence uses versioned,
transactional migrations. Import from Junior 1.x is staged, backed up, validated,
and reversible; it never deletes the working 1.x data as an upgrade mechanism.
