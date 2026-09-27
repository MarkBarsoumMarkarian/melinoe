from __future__ import annotations

from collections.abc import Callable

from melinoe.core.audit import AuditReport, Finding, summarize
from melinoe.core.models import ProjectManifest
from melinoe.rules.builtin import BUILTIN_RULES

Rule = Callable[[ProjectManifest], list[Finding]]


class OncoGuard:
    """Run deterministic scientific-validity rules against a project manifest."""

    def __init__(self, rules: list[tuple[str, Rule]] | None = None) -> None:
        self.rules = rules or BUILTIN_RULES

    def audit(self, manifest: ProjectManifest) -> AuditReport:
        findings: list[Finding] = []
        executed: list[str] = []
        for code, rule in self.rules:
            findings.extend(rule(manifest))
            executed.append(code)
        severity_order = {"blocker": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        findings.sort(key=lambda finding: (severity_order[finding.severity.value], finding.code))
        return AuditReport(
            project_id=manifest.project_id,
            summary=summarize(manifest, findings),
            findings=findings,
            rule_codes_executed=executed,
        )
