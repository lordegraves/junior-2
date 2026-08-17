# Junior 2.0 Architecture Skeleton

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
