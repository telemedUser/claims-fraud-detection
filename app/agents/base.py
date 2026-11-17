from abc import ABC, abstractmethod

from app.models import AgentResult, Claim, DocumentInfo, Finding

SEVERITY_POINTS = {"low": 10, "medium": 25, "high": 45}


class Agent(ABC):
    name: str = "agent"

    @abstractmethod
    async def analyze(self, claim: Claim, documents: list[DocumentInfo]) -> AgentResult: ...

    def result(self, findings: list[Finding]) -> AgentResult:
        score = min(100.0, float(sum(SEVERITY_POINTS[f.severity] for f in findings)))
        return AgentResult(agent=self.name, score=score, findings=findings)
