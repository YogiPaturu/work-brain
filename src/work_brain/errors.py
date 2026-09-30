class PersistenceError(RuntimeError):
    """Base error for persistence and projection failures."""


class ValidationError(PersistenceError, ValueError):
    """A durable domain payload violates its contract."""


class IntegrityError(PersistenceError):
    """Existing durable source is inconsistent or conflicting."""


class LockError(PersistenceError):
    """Another process currently owns the vault writer lock."""


class FeatureUnavailable(PersistenceError):
    """A documented application operation is not implemented in this phase."""
