"""Application-level coordination between source persistence and projections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .domain import SessionEntry


@dataclass(frozen=True)
class ProjectionMaintenanceResult:
    projection_status: str
    retrieval_status: str
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "projection_status": self.projection_status,
            "retrieval_status": self.retrieval_status,
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class CommitPublicationResult:
    source_status: str
    entry_id: str
    revision: int
    commit_id: str
    maintenance: ProjectionMaintenanceResult

    @classmethod
    def from_entry(cls, entry: SessionEntry, maintenance: ProjectionMaintenanceResult) -> "CommitPublicationResult":
        return cls("committed", entry.entry_id, entry.revision, entry.commit_id, maintenance)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_status": self.source_status,
            "entry_id": self.entry_id,
            "revision": self.revision,
            "commit_id": self.commit_id,
            **self.maintenance.to_dict(),
        }


class ProjectionMaintenance:
    """Best-effort derived maintenance kept outside the source store."""

    def __init__(self, vault: Any):
        self.vault = vault

    def after_source_commit(self, entry: SessionEntry) -> ProjectionMaintenanceResult:
        errors: list[str] = []
        projection_status = "current"
        retrieval_status = "current"
        if not self.vault._best_effort_source_projections(affected_date=self.vault.read_session(entry.session_id)["local_date"]):
            projection_status = "failed"
            errors.append("source projections could not be refreshed")
        try:
            from .retrieval import EvidenceRetriever
            EvidenceRetriever(self.vault).index_entry(entry.entry_id)
        except Exception as exc:
            retrieval_status = "failed"
            errors.append(f"retrieval index: {exc}")
        return ProjectionMaintenanceResult(projection_status, retrieval_status, tuple(errors))

    def rebuild(self) -> dict[str, Any]:
        self.vault.rebuild_all()
        from .retrieval import EvidenceRetriever
        return EvidenceRetriever(self.vault).reindex()
