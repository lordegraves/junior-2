# Junior 2.0 Product Requirements

## Status and vision

This is a future-product concept, not a statement of implemented behavior.
Junior 2.0 is a fully native desktop application in which local interpretation
normalizes job postings and resumes for a deterministic scoring engine.

> The model reads. The engine decides. The user remains in control.

For company additions, Junior gathers evidence, proposes a bounded action,
executes it through controlled code, and validates real jobs and pagination.
AI remains an internal implementation detail rather than a chatbot workflow.

## Goals

- Interpret varied job-posting and resume language without inventing facts.
- Preserve stated, missing, ambiguous, conflicting, and unreadable information.
- Give the scoring engine normalized, evidence-backed inputs.
- Keep recommendations, omissions, ranking, and policy deterministic and auditable.
- Make company addition substantially more reliable without making users hunt
  for recruiting-platform URLs.
- Operate locally across a realistic range of consumer hardware.
- Provide a native, accessible workflow with understandable fallback behavior.

## Non-goals

- An autonomous job-application agent or general-purpose assistant.
- Model-authored recommendations, omissions, compensation estimates, or facts.
- Arbitrary model-generated network requests, code, or collector configurations.
- Cloud processing as a hidden requirement.
- Training on private user material by default.

## Native experience

Users install and launch one desktop application, complete guided setup, import
or edit a profile, select companies, scan, and review results without a browser,
terminal, Python, or YAML. The interface must expose evidence and uncertainty in
plain language, support keyboard and assistive technology, remain responsive
during model work, and offer correction, export, deletion, and diagnostic paths.

## Matching levels and provisional hardware targets

All levels use the same workflow and deterministic decision engine. A level
changes interpretation depth and speed, not policy or evidence standards.

| Level | Behavior | Initial target |
|---|---|---|
| Fast | Primarily deterministic extraction with the lightest assistance | 4 GB RAM, 128 GB storage, modern Windows 11 device |
| Balanced | Local interpretation plus deterministic rules | 16 GB RAM, 256 GB SSD, modern Intel i5, AMD Ryzen 5, or Apple M-series |
| Detailed | Larger/deeper local interpretation | Windows/Linux: 32 GB RAM and 512 GB SSD; Apple: 24–32 GB unified memory and 512 GB SSD |

These are evaluation targets, not final minimum requirements. The installer
detects hardware and recommends the safest level. The user can change the level
for future comparisons; Junior warns about or blocks a selection that cannot run
safely. Existing audited decisions are not silently rewritten.

## Graceful fallback

A missing model, unsupported instruction set, memory pressure, timeout, corrupt
package, or failed validation must produce a clear fallback—not a crash or a
fabricated result. Junior may use deterministic parsing, reduce batch size, defer
work, or ask for review. It must say what capability was reduced and how to fix it.

## Model installation and updates

Models are versioned components with manifest, license, compatibility, checksum,
signature, disk-space check, resumable installation, health check, rollback, and
removal. Application and model updates may be independent. An interrupted update
must preserve the last working version, and offline/manual installation must be
considered for restricted environments.

## Privacy, licensing, and security

Resume and profile content stays local by default. Telemetry and data donation
are separate, explicit opt-ins; deletion and export are understandable. Training
data must be licensed, consented, provenance-tracked, and stripped of unnecessary
personal data. Model, dataset, runtime, and GUI licenses must permit the intended
use and distribution. Job pages, resumes, and embedded instructions are untrusted
data and cannot override Junior's rules or gain tool authority.

## Migration from Junior 1.x

Junior 1.x remains usable during development. Migration inventories and backs up
profiles, resumes, companies, history, applications, settings, and credentials or
credential references; imports supported data through versioned adapters; reports
anything unsupported; validates the result; and leaves the original installation
recoverable. Users may evaluate 2.0 without surrendering 1.x.

## Readiness criteria

Release requires validated schemas, reproducible model packages, independent
quality and security evaluation, supported-hardware results, deterministic audit
traces, accessible native workflows, safe migration and rollback, diagnostics
without private content, licensing review, and field testing on representative
machines and company platforms.
