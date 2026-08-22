# Junior 2.0 Product Requirements

## Status and vision

This is a future-product concept, not a statement of implemented behavior.
Junior 2.0 is a native desktop application. A local AI model reads job postings
and résumés and turns varied wording into consistent facts. A separate rules-based
engine uses those facts to score jobs. The AI does not make the decision.

> The model reads. The engine decides. The user remains in control.

For company additions, Junior gathers public clues and lets the model choose from
a limited set of safe next steps. Junior performs the step and confirms that it
found real jobs, complete job details, and every results page. The AI works behind
the scenes rather than acting as a chatbot.

## Goals

- Interpret varied job-posting and resume language without inventing facts.
- Preserve stated, missing, ambiguous, conflicting, and unreadable information.
- Give the scoring engine consistent facts supported by exact source text.
- Use fixed, testable rules for recommendations, omissions, and ranking so the
  same facts produce the same answer and the result can be explained.
- Make company addition substantially more reliable without making users hunt
  for recruiting-platform URLs.
- Operate locally across a realistic range of consumer hardware.
- Provide a native, accessible workflow with understandable fallback behavior.

## Non-goals

- A system that applies to jobs on its own or acts as a general assistant.
- Model-authored recommendations, omissions, compensation estimates, or facts.
- Letting a model visit any site it chooses, run code, or invent job-site settings.
- Cloud processing as a hidden requirement.
- Training on private user material by default.

## Native experience

Users install and launch one desktop application, complete guided setup, import
or edit a profile, select companies, scan, and review results without a browser,
terminal, Python, or YAML. The interface must expose evidence and uncertainty in
plain language, work by keyboard and with screen readers, remain responsive while
the model works, and let users correct, export, or delete their information.

The first native experiment displays reviewed qualification examples or reads a
pasted posting through a separately installed local model. Selecting a requirement
highlights its evidence. Alternative paths, missing qualifications, rejected
claims, and the not-yet-connected engine state are visible without exposing raw
model output by default. This is a durable starting point, not the completed
application.

For live pasted postings, the experiment performs extraction and semantic review
as separate steps. Semantic review uses headings and surrounding wording to check
what a qualification means and whether it is required, preferred, or unclear. Its
corrected output must pass the contract and exact-evidence checks again before the
interface displays it.

During evaluation, Junior can read a copied RC6 raw-scan ZIP downloaded by the
user from RC6 Reports. It selects a small, varied set of complete public postings
without accessing or changing the RC6 database. Profiles, résumés, credentials,
applications, and RC6 decisions are outside this import boundary.

## Matching levels and provisional hardware targets

All levels use the same workflow and fixed decision rules. A level changes how
deeply and quickly Junior reads documents, not its safety or evidence standards.

| Level | Behavior | Initial target |
|---|---|---|
| Fast | Primarily fixed non-AI reading rules with the lightest assistance | 4 GB RAM, 128 GB storage, modern Windows 11 device |
| Balanced | Local AI interpretation plus fixed decision rules | 16 GB RAM, 256 GB SSD, modern Intel i5, AMD Ryzen 5, or Apple M-series |
| Detailed | Larger/deeper local interpretation | Windows/Linux: 32 GB RAM and 512 GB SSD; Apple: 24–32 GB unified memory and 512 GB SSD |

These are evaluation targets, not final minimum requirements. The installer
detects hardware and recommends the safest level. The user can change the level
for future comparisons; Junior warns about or blocks a selection that cannot run
safely. Existing audited decisions are not silently rewritten.

## Graceful fallback

If a model is missing, incompatible, short on memory, too slow, damaged, or unable
to pass a safety check, Junior must not crash or invent a result. It can use its
fixed non-AI reading rules, process fewer items at once, wait, or ask the user to
review the item. It explains what was reduced and what the user can do next.

## Model installation and updates

Each model package identifies its version, license, supported computers, and
contents. Junior verifies that the download is authentic and unchanged, checks
available disk space, can resume an interrupted download, tests the installed
model, and can return to the previous working version. The application and model
may update separately. Offline installation must be considered for restricted
environments.

## Privacy, licensing, and security

Résumé and profile content stays on the user's computer by default. Usage reporting
and donating examples for future training are separate choices that are off unless
the user clearly agrees. Training material must have known origins and permission
for use, and unnecessary personal information must be removed. Every model and
software component must allow Junior's intended use and distribution. Instructions
hidden in job pages or documents cannot override Junior's rules.

## Migration from Junior 1.x

Junior 1.x remains usable during development. Before importing, Junior lists and
backs up profiles, résumés, companies, history, applications, settings, and saved
credential references. It reports anything it cannot import and checks the result.
The original installation remains recoverable, so users can try 2.0 without giving
up 1.x.

## Starter companies and existing collectors

Junior 2.0 ships the same version 1 catalog of 50 companies used by Junior 1.x.
The shipped list is a read-only starting point, not a claim that these are the
only or best employers. Users choose what to scan and can add or correct companies
without changing the shipped file.

The mature Junior 1.x collectors are moved into 2.0 with their tests and proven
site-specific behavior. Junior adapts them to the new common job format instead of
rewriting them. Known catalog entries go directly to their tested collector. New
or changed companies use discovery to identify which tested collector should run.

## Readiness criteria

Before release, Junior needs a proven information format, repeatable and verifiable
model packages, independent quality and security testing, results from supported
hardware, understandable decision histories, accessible desktop workflows, safe
upgrade and rollback, diagnostics without private content, license review, and
field testing on representative computers and company job systems.
