"""STATUSKIT — self-hosted status page engine.

Manage components, incidents (with timeline updates), and subscribers, and
compute an overall status + uptime metrics. Standard library only.
"""
from .core import (
    StatusKit,
    Component,
    Incident,
    IncidentUpdate,
    Subscriber,
    ComponentStatus,
    IncidentStatus,
    Impact,
    StatusKitError,
)

TOOL_NAME = "statuskit"
TOOL_VERSION = "1.0.0"

__all__ = [
    "StatusKit",
    "Component",
    "Incident",
    "IncidentUpdate",
    "Subscriber",
    "ComponentStatus",
    "IncidentStatus",
    "Impact",
    "StatusKitError",
    "TOOL_NAME",
    "TOOL_VERSION",
]
