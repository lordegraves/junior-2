# Junior 2.0 Design Decisions

## Decisions

- Junior 1.x remains supported while Junior 2.0 is developed in parallel.
- Junior 2.0 is a native desktop application whose different entry points all use
  the same Python rules and services.
- The model reads; fixed and testable rules decide; the user remains in control.
- Model output follows a required format, cites its source, and is checked before
  scoring.
- Missing information remains missing. Uncertainty cannot silently become rejection.
- Company discovery receives limited public information and may choose only from
  preapproved actions. Junior performs and checks every proposed setup.
- Weaker hardware may reduce automation but cannot reduce correctness.
- Private user data does not become training data without explicit opt-in.
- Junior's required information format is defined before selecting or teaching a
  model. Developers call this format a schema.
- Junior separately checks that evidence exists and that it supports the claim.
- Reading documents and finding company job systems have separate test programs.
- The three user-facing matching levels are Fast, Balanced, and Detailed.
- The installer recommends the safest level for detected hardware; users may
  change it for future comparisons, with unsafe choices warned or blocked.
- Junior begins with one shared local model. Each task still has a clearly defined
  input and output, so testing can justify moving one task to a specialized model
  without rebuilding the rest of the product.
- The native interface will use PySide6 with Qt Widgets. Before building the full
  interface, a small trial must prove it can be packaged, signed, accessible, and
  responsive on supported computers.
- Junior 2.0 will migrate the mature Junior 1.x collectors with their existing
  tests. It will adapt their inputs and outputs to 2.0 rather than rewrite their
  proven recruiting-platform behavior.
- Junior 2.0 will ship the same version 1 starter catalog of 50 companies. Shipped
  data remains read-only; user additions, overrides, selections, and health history
  are stored separately and take priority only in the user's effective view.

## Proposed details that remain replaceable

- A specialized model for a task, but only if tests prove it is materially better.
- The exact PySide6 packaging method after the small interface trial.
- SQLite for local storage, with safe database upgrades and reversible 1.x import.
- Separate lightweight AI assistance for finding company job systems.
- ONNX Runtime as one possible way to run a model; it is not selected.
- Model packages that are signed, versioned, independently updated, and able to
  return to the previous working version.

## Open questions

- What is the least powerful CPU-only computer Junior must support, and how much
  memory may it use?
- Which local model-running software and distributable model pass Junior's tests?
- Which original documents should Junior keep, and for how long?
- How should Junior record alternative ways to qualify and user corrections?
- Beyond collectors and the starter catalog, which Junior 1.x components can be
  reused safely and which need replacement?
- What exact test results are required before selecting a model or building the GUI?
- Which facts need the extra check that cited words really support the claim, and
  what trusted method performs that check?
- What evidence and corrections may be retained, exported, or donated?
- Which model licenses permit bundling, modification, and redistribution?
- How will Junior verify a model is genuine and recover from damage or a failed update?
- Which company-discovery actions and websites are allowed?
- What are the exact speed, memory, quality, and fallback requirements for each level?
- What measurable improvement over known 1.x failures is required before GUI work?

## Preimplementation questions

Before implementation expands, answer these questions: What facts does scoring
need? How does Junior record missing or uncertain information? How can every claim
be traced to its source? How can corrections improve testing without exposing
private documents? What computers must work? What still works without a model?
How is untrusted content isolated? How can users inspect, correct, export, or
delete everything Junior stores about document interpretation?
