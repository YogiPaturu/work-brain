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
    source_warnings: tuple[str, ...] = ()

    @classmethod
    def from_entry(cls, entry: SessionEntry, maintenance: ProjectionMaintenanceResult, source_warnings: tuple[str, ...] = ()) -> "CommitPublicationResult":
        return cls("committed", entry.entry_id, entry.revision, entry.commit_id, maintenance, source_warnings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_status": self.source_status,
            "entry_id": self.entry_id,
            "revision": self.revision,
            "commit_id": self.commit_id,
            "source_warnings": list(self.source_warnings),
            **self.maintenance.to_dict(),
        }


class ProjectionMaintenance:
    """Best-effort derived maintenance kept outside the source store."""

    def __init__(self, vault: Any):
        self.vault = vault

    def after_source_commit(self, entry: SessionEntry) -> ProjectionMaintenanceResult:
        return self.after_source_commits((entry,))

    def after_source_commits(self, entries: tuple[SessionEntry, ...]) -> ProjectionMaintenanceResult:
        """Refresh derived state after one or more durably published entries.

        The caller has already crossed the authoritative source boundary.  A
        projection or retrieval failure is therefore recorded in the result,
        never raised as if the source mutation had failed.  Batch callers use
        one source-projection refresh and one retriever instance while keeping
        each entry's optimistic retrieval publication independent.
        """
        if not entries:
            return ProjectionMaintenanceResult("current", "current")
        errors: list[str] = []
        projection_status = "current"
        retrieval_status = "current"
        local_dates = {self.vault.read_session(entry.session_id)["local_date"] for entry in entries}
        affected_date = next(iter(local_dates)) if len(local_dates) == 1 else None
        if not self.vault._best_effort_source_projections(affected_date=affected_date):
            projection_status = "failed"
            errors.append("source projections could not be refreshed")
        try:
            from .retrieval import EvidenceRetriever, StaleIndexWork
            retriever = EvidenceRetriever(self.vault)
            for entry in entries:
                try:
                    retriever.index_entry(entry.entry_id)
                except StaleIndexWork as exc:
                    if retrieval_status != "failed":
                        retrieval_status = "stale"
                    errors.append(f"retrieval index: {exc}")
                except Exception as exc:
                    retrieval_status = "failed"
                    errors.append(f"retrieval index: {exc}")
        except Exception as exc:
            retrieval_status = "failed"
            errors.append(f"retrieval index: {exc}")
        return ProjectionMaintenanceResult(projection_status, retrieval_status, tuple(errors))

    def rebuild(self) -> dict[str, Any]:
        self.vault.rebuild_all()
        from .retrieval import EvidenceRetriever
        return EvidenceRetriever(self.vault).reindex()
