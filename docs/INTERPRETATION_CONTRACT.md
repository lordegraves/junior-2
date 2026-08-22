# What the AI Must Tell Junior

This document defines the information passed from Junior's local AI model to its
fixed scoring rules. It is a safety contract: the model may report what a source
says, but it may not recommend, score, reject, or omit a job.

## Job qualifications

Every qualification records:

- A stable identifier used only inside that interpretation.
- Its type, such as education, experience, skill, certification, work permission,
  security clearance, physical requirement, travel, or schedule.
- The wording from the posting.
- A consistent value Junior can compare later.
- Whether the wording is clear, unclear, conflicting, or unreadable.
- The exact source text and its position in the document.
- The exact version of the source document.
- Confidence between zero and one.

The complete interpretation also records the format version and the model or
interpreter version that produced it. This lets an audit reproduce which rules
and model handled the document.

Confidence never replaces evidence. A highly confident claim with incorrect
evidence is rejected.

Junior divides the relevant source section into numbered passages. The model
selects passage numbers; it does not copy evidence words or calculate character
positions. Junior then supplies the exact source text and positions from those
passages. An unknown passage number rejects the response. This keeps small local
models from accidentally paraphrasing evidence while preserving strict proof.

Junior gives smaller local models a bounded number of passages at a time and
combines the results in source order. This prevents a long qualification section
from causing the model to stop after its first few requirements. Each batch gets
unique internal identifiers before the semantic review.

The second model pass reviews existing identifiers in small batches. It may
correct meaning, but it cannot delete or restructure extracted requirements or
change their evidence. Unknown corrections are ignored. Clear requirement words
such as “must” and “requires” also receive a fixed source-based check so a small
model cannot silently skip them. Ordinary required items are displayed together;
alternative paths appear only when the source explicitly connects complete
qualification routes. An incidental “or” within a degree, clearance name, or skill
does not make unrelated requirements interchangeable. Source headings and clear
words such as “preferred,” “desirable,” “bonus,” and “a plus” determine whether an
item is required or preferred instead of trusting the model's label.

Before either model pass, Junior selects one or more separately bounded
qualification-focused parts of the posting. This keeps requirements that appear
before and after unrelated material without sending benefits, compensation,
company descriptions, application instructions, or equal-employment/legal
material to the model as qualifications. Every selected part retains its exact
position in the complete posting. Fixed checks then remove headings, page metadata, recruiting slogans, and category
claims whose quoted words do not express that category. Exact quotation proves
that words came from the posting; these structural checks help prove that the
words are actually a qualification.

If Ollama answers with malformed JSON, Junior makes one controlled retry that asks
for the same record in the required format. A second unreadable answer fails the
posting safely; it is not silently accepted.

Repeated experience, age-and-license, and language requirements are consolidated
when their meaning is demonstrably equivalent. Location-specific requirements remain visible and
auditable in a separate conditional group; they are not presented as requirements
every applicant must meet. The later scoring adapter must evaluate those conditions
against the job's actual location before making a decision.

## Different ways to qualify

Requirements are organized into groups and paths:

- Every item inside one path must be satisfied.
- Satisfying any one path satisfies the surrounding group.

For example:

```text
Required group
  Path 1: bachelor's degree AND seven years of experience
  OR
  Path 2: master's degree AND five years of experience
```

Junior must not turn that into four separate requirements. Required and preferred
groups also remain separate, even when headings use unusual wording such as
“Key Qualifications,” “Desirable Skills,” or “Bonus Points.”

## Missing and uncertain information

If a posting does not state qualifications, the model reports `not_stated` and an
empty group list. It does not invent likely requirements. Unclear, conflicting,
or unreadable information remains marked that way so the decision engine can send
it to review rather than treating it as a failed qualification.

## Résumé qualifications

Every résumé qualification uses the same categories, consistent values, and exact
evidence rules. Later matching work will compare job requirements with résumé
qualifications. A shared keyword alone is not proof that the applicant satisfies a
requirement.

## Required checks

Junior rejects a model response when:

- A required field is missing.
- An unexpected field is present, including a model-created recommendation.
- A value has the wrong type.
- The format version is unsupported.
- A qualification has no evidence.
- The quoted text or its location does not match the source.
- A stated qualification section contains no groups.
- A missing or unreadable section contains invented groups.

Junior reports these failures using a narrow reason code. The reason identifies
the failed rule, not the source text or raw model response. This provides useful
troubleshooting information without turning diagnostics into a copy of a job
posting or résumé.

Exact quotation alone does not prove semantic accuracy. Junior therefore combines
the separate semantic review with fixed section and category checks. The current
experiment still requires evaluation against varied real postings before these
checks can be treated as production-ready.
