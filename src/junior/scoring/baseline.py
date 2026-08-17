"""Safe placeholder policy demonstrating that uncertainty becomes review."""

from collections.abc import Sequence

from junior.domain.decisions import Decision, Recommendation
from junior.domain.facts import ExtractedFact, FactState


class ConservativeDecisionEngine:
    """Keep incomplete interpretation reviewable until explicit policy exists."""

    def decide(self, facts: Sequence[ExtractedFact]) -> Decision:
        uncertain = any(
            fact.state
            in {
                FactState.NOT_STATED,
                FactState.AMBIGUOUS,
                FactState.CONFLICTING,
                FactState.UNREADABLE,
            }
            for fact in facts
        )
        reason = (
            "One or more relevant facts are unresolved."
            if uncertain
            else "Validated facts require deterministic profile evaluation."
        )
        return Decision(Recommendation.NEEDS_REVIEW, (reason,))
