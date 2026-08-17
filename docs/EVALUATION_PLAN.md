# Junior 2.0 Evaluation and Delivery Plan

## Evidence and datasets

Evaluation uses reviewed, provenance-tracked job postings, resumes, and company
sites. Labels cover section boundaries, required versus preferred qualifications,
alternative paths, compensation, location, employment type, missingness,
ambiguity, conflicts, evidence spans, platform identity, pagination, job detail
depth, and failure modes. Training, tuning, and final evaluation sets remain
separate. Synthetic cases supplement but do not replace representative examples.

Private user data is excluded unless separately and explicitly donated under a
documented consent, deletion, and provenance process.

## Two independent evaluation programs

Document interpretation measures fact accuracy, evidence support, missing-fact
honesty, alternative-path preservation, resume-to-requirement support, calibration,
latency, memory, fallback rate, and downstream decision impact.

Company discovery measures platform identification, correct endpoint selection,
real-job validation, pagination completeness, detail completeness, false acceptance,
bounded-loop behavior, latency, requests, memory, and deterministic fallback.

Results are segmented by matching level and hardware class. Final thresholds are
set from baselines and user-impact analysis; this document does not invent target
percentages before representative evaluation exists.

## Delivery phases

1. Define the normalized document representation and source-version evidence.
2. Define the constrained extraction format and explicit fact states.
3. Implement evidence-existence and semantic-support checking.
4. Build licensed, reviewed, separated training and evaluation data.
5. Run small local-model and deterministic-baseline experiments.
6. Validate resume-to-job qualification matching and alternative paths.
7. Build deterministic company evidence gathering and platform fingerprints.
8. Evaluate bounded model-assisted company discovery and action proposals.
9. Test Fast, Balanced, and Detailed levels on representative hardware.
10. Integrate the complete ingestion-to-audit pipeline.

**Architecture gate:** before native GUI work, the pipeline must materially
outperform documented Junior 1.x failure cases without increasing unjustified
omissions, fabricated facts, unsafe actions, or unacceptable resource use.

11. Build the native accessible desktop interface over shared use cases.
12. Implement backed-up, validated, reversible Junior 1.x migration.
13. Conduct field testing, packaging, signing, update, rollback, and support trials.

Each phase needs explicit inputs, outputs, acceptance evidence, and a stop/go
review. Model or toolkit selection is not a substitute for passing these gates.

## Principal risks

- Small local models may be too inaccurate; mitigate with narrow tasks,
  deterministic fast paths, validation, and fallback.
- Hardware diversity may cause crashes or poor latency; benchmark real target
  classes and enforce memory/time limits.
- Training/evaluation leakage may overstate quality; preserve held-out sets and
  provenance.
- Company sites change and block automation; validate live job records and retain
  typed failure evidence rather than guessing.
- Prompt injection or malformed documents may influence a model; treat all content
  as data and deny model authority.
- Licensing may prevent distribution; review every model, dataset, runtime, and
  toolkit before adoption.
- Migration may damage user trust; use backup, dry-run, validation, rollback, and
  coexistence with 1.x.
- A native GUI can arrive before the core is trustworthy; enforce the architecture
  gate before interface expansion.
