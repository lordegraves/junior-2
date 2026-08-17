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

Checking whether the quoted words truly support the model's meaning is a separate
future check. Exact quote validation is implemented first; passing it does not yet
prove semantic accuracy.
