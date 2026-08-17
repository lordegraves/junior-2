# Junior 2.0 Design Decisions

## Decisions

- Junior 1.x remains supported while Junior 2.0 is developed in parallel.
- Junior 2.0 is a native desktop application backed by shared Python services.
- The model reads; the deterministic engine decides; the user remains in control.
- Model output is structured, evidence-backed, and validated before scoring.
- Missing information remains missing. Uncertainty cannot silently become rejection.
- Company discovery uses bounded evidence gathering and predefined actions;
  Junior executes and validates every proposed collector configuration.
- Weaker hardware may reduce automation but cannot reduce correctness.
- Private user data does not become training data without explicit opt-in.
- Schema design and evidence contracts precede model selection or training.
- Evidence existence and semantic support are separate validation gates.
- Document interpretation and company discovery have separate evaluation programs.
- The three user-facing matching levels are Fast, Balanced, and Detailed.
- The installer recommends the safest level for detected hardware; users may
  change it for future comparisons, with unsafe choices warned or blocked.

## Proposals represented by replaceable boundaries

- A local interpretation model or several task-specific local models.
- A Python-native desktop toolkit.
- SQLite persistence with versioned migrations and reversible 1.x import.
- Separate lightweight assistance for company discovery.
- ONNX Runtime as one inference candidate, not a selected dependency.
- Signed, versioned, rollback-capable model packages distributed separately
  from normal application updates.

## Open questions

- Which native GUI toolkit meets accessibility, packaging, and maintainability needs?
- What CPU-only hardware floor and memory budget must be supported?
- Which local inference runtime and redistributable base model pass evaluation?
- Which original document forms are retained, and for how long?
- What schema represents alternative qualification paths and user corrections?
- Which Junior 1.x services are reused directly versus migrated behind adapters?
- What exact evaluation gates must be met before model or GUI selection?
- What is the canonical normalized schema, including alternative requirements?
- Which fact types require semantic verification, and which verifier is trusted?
- What evidence and corrections may be retained, exported, or donated?
- Which model licenses permit bundling, modification, and redistribution?
- How are model authenticity, rollback, corruption, and interrupted updates handled?
- Which bounded company-discovery actions and network destinations are permitted?
- What are the exact latency, memory, quality, and fallback thresholds per level?
- What measurable improvement over known 1.x failures is required before GUI work?

## Preimplementation questions

Before implementation expands, answer: what facts the scoring engine needs;
how each fact represents missingness and uncertainty; how every claim is traced;
how user corrections become labeled data without exposing private documents;
what hardware floor is supported; which components remain useful with no model;
how untrusted content is isolated; and how a user can inspect, correct, export,
or delete every stored interpretation artifact.
