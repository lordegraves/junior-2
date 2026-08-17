"""First vertical seam: interpret, validate, then decide."""

from dataclasses import dataclass

from junior.application.interpretation_ports import JobPostingInterpreter
from junior.application.ports import DecisionEngine, FactValidator
from junior.domain.decisions import Decision
from junior.domain.documents import SourceDocument


@dataclass(slots=True)
class InterpretJobPosting:
    interpreter: JobPostingInterpreter
    validator: FactValidator
    decision_engine: DecisionEngine

    def execute(self, document: SourceDocument) -> Decision:
        proposed = self.interpreter.interpret_job_posting(document)
        validated = self.validator.validate(document, proposed)
        return self.decision_engine.decide(validated)
