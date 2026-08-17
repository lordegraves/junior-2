# Junior 2.0 Evaluation and Delivery Plan

## Evidence and datasets

Testing uses job postings, résumés, and company sites that people have reviewed
and whose origins and usage rights are recorded. Reviewers mark the correct
sections, required and preferred qualifications, alternative ways to qualify,
compensation, location, employment type, missing or unclear facts, conflicts,
supporting text, recruiting platform, later result pages, job-detail completeness,
and known failures. Examples used to teach the model are kept separate from the
final exam. Created examples can fill gaps but cannot replace realistic material.

Private user data is excluded unless separately and explicitly donated under a
documented consent and deletion process that records where the material came from
and how Junior is allowed to use it.

## Two independent evaluation programs

Document testing measures whether facts are correct, evidence truly supports them,
missing information stays missing, alternative qualifications remain separate,
and résumé matches are justified. It also measures whether confidence matches
actual accuracy, how long work takes, memory use, how often Junior falls back to
another method, and how errors affect the final recommendation.

Company testing measures whether Junior finds the right recruiting platform and
public job address, confirms real jobs, reaches every results page, and retrieves
complete details. It also counts incorrect approvals, repeated attempts, time,
web requests, memory use, and success when Junior must use non-AI rules instead.

Results are reported separately for each matching level and type of computer.
Passing scores will be based on real baseline results and user impact. We will not
invent reassuring percentages before representative testing exists.

## Delivery phases

1. Define how Junior records consistent facts and their exact sources.
2. Define the limited output format and the states for clear or uncertain facts.
3. Check that supporting text exists and actually means what Junior claims.
4. Build legally usable, reviewed, separate teaching and testing material.
5. Compare small local models with Junior's existing non-AI rules.
6. Test résumé-to-job matching, including different ways to qualify.
7. Migrate the Junior 1.x collectors and starter catalog with their existing tests.
   Add 2.0 contract and catalog-layering tests, plus fixed rules for gathering
   company clues and recognizing platforms.
8. Test model-assisted discovery with limited information and safe actions.
9. Test Fast, Balanced, and Detailed levels on representative hardware.
10. Connect the complete path from reading a source through explaining the result.

**Required checkpoint before building the full GUI:** the core system must clearly
improve on documented Junior 1.x failures without causing more unjustified
omissions, invented facts, unsafe actions, or unacceptable resource use.

11. Build the accessible native desktop interface on the shared application rules.
12. Build a backed-up, checked, and reversible import from Junior 1.x.
13. Field-test installation, signed releases, updates, rollback, and support.

Each phase states what it starts with, what it must produce, and how success will
be proven before work continues. Choosing impressive technology does not replace
passing these checks.

## Principal risks

- Small local models may be too inaccurate. Give them narrow jobs, check every
  result, keep a fast non-AI path, and provide a safe fallback.
- Different computers may cause crashes or long waits. Test representative
  machines and enforce memory and time limits.
- A model may appear better if it has already seen the final test examples. Keep
  the final exam separate and record where every example came from.
- Company sites change and may block automated access. Confirm live jobs and record
  exactly what failed instead of guessing.
- A page may contain hidden instructions intended to manipulate an AI model. Treat
  all page and document content as untrusted data and give the model no authority.
- Licensing may prevent distribution. Review every model, set of examples,
  model-running component, and GUI toolkit before adoption.
- Importing data may damage user trust if anything is lost. Use backups, a practice
  run, checks, rollback, and continued access to 1.x.
- A native GUI can arrive before the core is trustworthy; enforce the architecture
  gate before interface expansion.
