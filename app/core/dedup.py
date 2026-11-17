"""Deduplicate findings by correlation key. Pure and order independent.

Requirements 4.6, 5.4, 12.5.
"""
from __future__ import annotations

from collections.abc import Iterable

from app.core.finding import SEVERITY_RANK, STATUS_RANK, Finding


def _winner_key(f: Finding) -> tuple:
    # Highest (status, severity) wins; ties fall back to the smallest stable ids.
    return (
        -STATUS_RANK[f.status],
        -SEVERITY_RANK[f.severity],
        f.check_id,
        f.use_case_id,
        str(f.finding_id),
    )


def dedup_findings(findings: Iterable[Finding]) -> list[Finding]:
    """Collapse findings sharing a correlation_key into one.

    The winner keeps its own fields; contributing_checks, contributing_sources
    and contributing_use_case_ids become the sorted union over the group.
    Output is sorted by correlation_key.
    """
    groups: dict[str, list[Finding]] = {}
    for f in findings:
        groups.setdefault(f.correlation_key, []).append(f)

    result: list[Finding] = []
    for key in sorted(groups):
        group = groups[key]
        winner = min(group, key=_winner_key)
        result.append(
            winner.model_copy(
                update={
                    "contributing_checks": sorted({c for g in group for c in g.contributing_checks}),
                    "contributing_sources": sorted({s for g in group for s in g.contributing_sources}),
                    "contributing_use_case_ids": sorted(
                        {u for g in group for u in g.contributing_use_case_ids}
                    ),
                }
            )
        )
    return result
