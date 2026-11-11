from typing import Any

from app.models import AuditLog, User


def audit_entry(
    action: str,
    *,
    user: User | None = None,
    agent: str | None = None,
    entity_type: str | None = None,
    entity_id: Any = None,
    assessment_id: int | None = None,
    details: dict | None = None,
) -> AuditLog:
    """Build an audit row. Add it to the same session as the change it describes,
    so the action and its audit record commit together or not at all."""
    if user is not None:
        actor_type, actor_id = "user", str(user.id)
    elif agent is not None:
        actor_type, actor_id = "agent", agent
    else:
        actor_type, actor_id = "system", None
    return AuditLog(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        assessment_id=assessment_id,
        details=details or {},
    )
