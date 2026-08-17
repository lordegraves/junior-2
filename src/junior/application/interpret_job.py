"""First vertical seam: interpret, validate, then decide."""

from dataclasses import dataclass

from junior.application.ports import DecisionEngine, DocumentInterpreter, FactValidator
from junior.domain.decisions import Decision
from junior.domain.documents import SourceDocument


@dataclass(slots=True)
class InterpretJobPosting:
    interpreter: DocumentInterpreter
    validator: FactValidator
    decision_engine: DecisionEngine

    def execute(self, document: SourceDocument) -> Decision:
        proposed = self.interpreter.interpret(document)
        validated = self.validator.validate(document, proposed)
        return self.decision_engine.decide(validated)
