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

## Proposals represented by replaceable boundaries

- A local interpretation model or several task-specific local models.
- A Python-native desktop toolkit.
- SQLite persistence with versioned migrations and reversible 1.x import.
- Separate lightweight assistance for company discovery.

## Open questions

- Which native GUI toolkit meets accessibility, packaging, and maintainability needs?
- What CPU-only hardware floor and memory budget must be supported?
- Which local inference runtime and redistributable base model pass evaluation?
- Which original document forms are retained, and for how long?
- What schema represents alternative qualification paths and user corrections?
- Which Junior 1.x services are reused directly versus migrated behind adapters?
- What exact evaluation gates must be met before model or GUI selection?
