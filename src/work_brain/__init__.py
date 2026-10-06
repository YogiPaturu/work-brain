"""Public Work Brain API with lazy exports for a lightweight hook process."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "IntegrityError": (".errors", "IntegrityError"),
    "PersistenceError": (".errors", "PersistenceError"),
    "ValidationError": (".errors", "ValidationError"),
    "FeatureUnavailable": (".errors", "FeatureUnavailable"),
    "Vault": (".vault", "Vault"),
    "new_uuid7": (".ids", "new_uuid7"),
    "validate_uuid7": (".ids", "validate_uuid7"),
    "CommitDraftValidator": (".commit", "CommitDraftValidator"),
    "CommitResolver": (".commit", "CommitResolver"),
    "InstructionResource": (".instructions", "InstructionResource"),
    "LoadedInstructions": (".instructions", "LoadedInstructions"),
    "SkillLoader": (".instructions", "SkillLoader"),
    "ModelResponse": (".model", "ModelResponse"),
    "ScriptedModel": (".model", "ScriptedModel"),
    "ContextPlanner": (".orchestrator", "ContextPlanner"),
    "PromptRoute": (".routing", "PromptRoute"),
    "RuntimeState": (".orchestrator", "RuntimeState"),
    "SessionOrchestrator": (".orchestrator", "SessionOrchestrator"),
    "normalize_routing_text": (".routing", "normalize_routing_text"),
    "route_prompt": (".routing", "route_prompt"),
    "select_workflow": (".routing", "select_workflow"),
    "ToolDefinition": (".tools", "ToolDefinition"),
    "ToolRegistry": (".tools", "ToolRegistry"),
    "ToolResult": (".tools", "ToolResult"),
    "ContextResolver": (".context_resolver", "ContextResolver"),
    "CommunicationProfile": (".profiles", "CommunicationProfile"),
    "CommunicationProfileStore": (".profiles", "CommunicationProfileStore"),
    "profiles_document": (".profiles", "profiles_document"),
    "resolve_profiles_path": (".profiles", "resolve_profiles_path"),
    "CaptureEvent": (".capture", "CaptureEvent"),
    "HarnessCaptureService": (".capture", "HarnessCaptureService"),
    "normalize_capture_event": (".capture", "normalize_capture_event"),
    "HarnessSetup": (".setup", "HarnessSetup"),
    "EvidenceRetriever": (".retrieval", "EvidenceRetriever"),
    "EvidenceRef": (".retrieval", "EvidenceRef"),
    "FastEmbedEmbeddingProvider": (".retrieval", "FastEmbedEmbeddingProvider"),
    "LocalHashEmbeddingProvider": (".retrieval", "LocalHashEmbeddingProvider"),
    "CommitPublicationResult": (".services", "CommitPublicationResult"),
    "ProjectionMaintenance": (".services", "ProjectionMaintenance"),
    "ProjectionMaintenanceResult": (".services", "ProjectionMaintenanceResult"),
    "ExperienceCard": (".experiences", "ExperienceCard"),
    "ExperienceService": (".experiences", "ExperienceService"),
    "CareerCandidateMarkStore": (".career", "CareerCandidateMarkStore"),
    "CareerService": (".career", "CareerService"),
    "InterviewQuestion": (".career", "InterviewQuestion"),
    "MarkdownQuestionBankProvider": (".career", "MarkdownQuestionBankProvider"),
    "QuestionBank": (".career", "QuestionBank"),
    "QuestionFilters": (".career", "QuestionFilters"),
    "QuestionRef": (".career", "QuestionRef"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
