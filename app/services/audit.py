"""Append security-relevant audit events without ever breaking a request."""

import logging

from flask import g

from ..extensions import db
from ..models import AuditEvent
from ..security import client_address_hash

logger = logging.getLogger(__name__)


def record_audit(action, target_type=None, target_id=None, detail=None, actor=None):
    """Persist one audit event. Failures are logged and swallowed."""
    try:
        if actor is None:
            actor = getattr(g, "current_user", None)
        event = AuditEvent(
            action=str(action)[:60],
            actor_id=getattr(actor, "id", None),
            actor_email=getattr(actor, "email", None),
            actor_role=getattr(actor, "role", None),
            target_type=str(target_type)[:40] if target_type else None,
            target_id=str(target_id)[:40] if target_id is not None else None,
            detail=str(detail)[:255] if detail else None,
            ip_hash=client_address_hash(),
        )
        db.session.add(event)
        db.session.commit()
    except Exception:  # noqa: BLE001 - auditing must never break a request
        db.session.rollback()
        logger.exception("Audit event %s could not be recorded.", action)
