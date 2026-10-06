"""Read-only resolution of natural-language workspace and project context."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from .domain import normalize_alias
from .errors import ValidationError
from .fsutil import read_json


MAX_CONTEXT_CANDIDATES = 5
MAX_SUPPORTING_ENTRIES = 3


class ContextResolver:
    """Resolve existing workspace/project identities without catalog mutation."""

    def __init__(self, vault: Any, *, search_evidence: Callable[..., Any] | None = None):
        self.vault = vault
        if search_evidence is None:
            from .retrieval import EvidenceRetriever

            search_evidence = EvidenceRetriever(vault).search
        self.search_evidence = search_evidence

    def resolve_context(
        self,
        *,
        workspace_hint: str | None = None,
        project_hint: str | None = None,
        limit: int = MAX_CONTEXT_CANDIDATES,
    ) -> dict[str, Any]:
        workspace_hint = self._optional_hint(workspace_hint, "workspace_hint")
        project_hint = self._optional_hint(project_hint, "project_hint")
        if workspace_hint is None and project_hint is None:
            raise ValidationError("at least one of workspace_hint or project_hint is required")
        if not isinstance(limit, int) or not 1 <= limit <= MAX_CONTEXT_CANDIDATES:
            raise ValidationError(f"limit must be between 1 and {MAX_CONTEXT_CANDIDATES}")

        result: dict[str, Any] = {}
        workspace_id: str | None = None
        if workspace_hint is not None:
            candidates = self._exact_candidates("workspace", workspace_hint, limit)
            status = "resolved" if len(candidates) == 1 else "ambiguous" if candidates else "unresolved"
            if status == "resolved":
                workspace_id = candidates[0]["entity_id"]
            result["workspace"] = {"input": workspace_hint, "status": status, "candidates": candidates}

        if project_hint is not None:
            exact = self._scope_exact_projects(
                self._exact_candidates("project", project_hint, limit), workspace_id, limit,
            )
            if len(exact) == 1:
                result["project"] = {"input": project_hint, "status": "resolved", "candidates": exact}
            elif exact:
                historical = self._historical_projects(
                    project_hint, workspace_id=workspace_id, limit=limit,
                )
                result["project"] = {
                    "input": project_hint,
                    "status": "ambiguous",
                    "candidates": exact,
                    "historical_candidates": historical["candidates"],
                    "historical_status": historical.get("historical_status", "ok"),
                }
                if historical.get("degraded_components"):
                    result["project"]["degraded_components"] = historical["degraded_components"]
            else:
                result["project"] = self._historical_projects(
                    project_hint, workspace_id=workspace_id, limit=limit,
                )
        return result

    @staticmethod
    def _optional_hint(value: str | None, field: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{field} must be a non-empty string when supplied")
        return value.strip()

    def _source_entity(self, entity_id: str, kind: str) -> dict[str, Any] | None:
        path = self.vault.root / "catalog/entities" / f"{entity_id}.json"
        if not path.exists():
            return None
        value = read_json(path)
        if value.get("entity_id") != entity_id or value.get("kind") != kind:
            return None
        canonical_name = value.get("canonical_name")
        if not isinstance(canonical_name, str) or not canonical_name:
            return None
        return value

    def _exact_candidates(self, kind: str, hint: str, limit: int) -> list[dict[str, Any]]:
        normalized = normalize_alias(hint)
        rows: list[Any] = []
        try:
            conn = self.vault._database().connect()
        except Exception:
            conn = None
        if conn is not None:
            try:
                rows = conn.execute(
                    "SELECT DISTINCT e.entity_id, e.canonical_name "
                    "FROM entities e JOIN entity_aliases ea ON ea.entity_id = e.entity_id "
                    "WHERE e.kind = ? AND ea.alias_norm = ?",
                    (kind, normalized),
                ).fetchall()
            except Exception:
                rows = []
            finally:
                conn.close()

        candidates: list[dict[str, Any]] = []
        for row in rows:
            source = self._source_entity(row["entity_id"], kind)
            if source is None:
                continue
            candidates.append({
                "entity_id": source["entity_id"],
                "canonical_name": source["canonical_name"],
                "matched_by": "canonical" if normalize_alias(source["canonical_name"]) == normalized else "alias",
            })
        if not candidates:
            # A missing or stale derived entity projection must not make an
            # existing authoritative identity impossible to resolve. This is
            # only a bounded read fallback; it never repairs or mutates the
            # source catalog.
            for path in sorted((self.vault.root / "catalog/entities").glob("*.json")):
                source = read_json(path)
                if source.get("kind") != kind:
                    continue
                names = [source.get("canonical_name", ""), *source.get("aliases", [])]
                if any(isinstance(name, str) and normalize_alias(name) == normalized for name in names):
                    candidates.append({
                        "entity_id": source["entity_id"],
                        "canonical_name": source["canonical_name"],
                        "matched_by": "canonical" if normalize_alias(source["canonical_name"]) == normalized else "alias",
                    })
        candidates.sort(key=lambda item: (normalize_alias(item["canonical_name"]), item["entity_id"]))
        return candidates[:limit]

    def _scope_exact_projects(
        self,
        candidates: list[dict[str, Any]],
        workspace_id: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        if workspace_id is None or len(candidates) <= 1:
            return candidates
        candidate_ids = {item["entity_id"] for item in candidates}
        try:
            conn = self.vault._database().connect()
            try:
                rows = conn.execute(
                    "SELECT DISTINCT project_entity_id FROM ("
                    "SELECT project_entity_id FROM retrieval_entries WHERE workspace_entity_id = ? "
                    "UNION SELECT project_entity_id FROM entries WHERE workspace_entity_id = ?"
                    ") WHERE project_entity_id IS NOT NULL",
                    (workspace_id, workspace_id),
                ).fetchall()
            finally:
                conn.close()
        except Exception:
            return candidates
        scoped = candidate_ids & {row["project_entity_id"] for row in rows}
        if len(scoped) == 1:
            return [item for item in candidates if item["entity_id"] in scoped]
        return candidates[:limit]

    def _historical_projects(
        self,
        project_hint: str,
        *,
        workspace_id: str | None,
        limit: int,
    ) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        if workspace_id is not None:
            filters["workspaces"] = [workspace_id]
        try:
            result = self.search_evidence(
                query=project_hint,
                filters=filters,
                page_size=min(MAX_CONTEXT_CANDIDATES * MAX_SUPPORTING_ENTRIES, 20),
                cursor=None,
            )
        except Exception as exc:
            return {
                "input": project_hint,
                "status": "unresolved",
                "candidates": [],
                "historical_status": "unavailable",
                "historical_error": str(exc),
            }

        if not isinstance(result, Mapping):
            return {"input": project_hint, "status": "unresolved", "candidates": [], "historical_status": "unavailable"}
        cards = result.get("cards", [])
        if not isinstance(cards, list):
            cards = []
        grouped: dict[str, dict[str, Any]] = {}
        for position, card in enumerate(cards, start=1):
            if not isinstance(card, Mapping):
                continue
            project = card.get("project")
            if not isinstance(project, Mapping) or not isinstance(project.get("entity_id"), str):
                continue
            entity_id = project["entity_id"]
            source = self._source_entity(entity_id, "project")
            if source is None:
                continue
            item = grouped.setdefault(entity_id, {
                "entity_id": entity_id,
                "canonical_name": source["canonical_name"],
                "matched_by": "historical_evidence",
                "evidence_match_count": 0,
                "best_result_position": position,
                "supporting_entries": [],
            })
            item["evidence_match_count"] += 1
            item["best_result_position"] = min(item["best_result_position"], position)
            ref = card.get("ref")
            if isinstance(ref, Mapping) and len(item["supporting_entries"]) < MAX_SUPPORTING_ENTRIES:
                entry_id, revision = ref.get("entry_id"), ref.get("revision")
                if isinstance(entry_id, str) and isinstance(revision, int):
                    item["supporting_entries"].append({
                        "entry_id": entry_id,
                        "revision": revision,
                        "title": card.get("title", ""),
                    })
        candidates = sorted(
            grouped.values(),
            key=lambda item: (
                -item["evidence_match_count"], item["best_result_position"],
                normalize_alias(item["canonical_name"]), item["entity_id"],
            ),
        )[:limit]
        response: dict[str, Any] = {
            "input": project_hint,
            "status": "candidates" if candidates else "unresolved",
            "candidates": candidates,
            "historical_status": str(result.get("status", "ok")),
        }
        if result.get("degraded_components"):
            response["degraded_components"] = list(result["degraded_components"])
        if result.get("incomplete"):
            response["incomplete"] = True
        return response
