"""Core engine for STATUSKIT.

A self-hosted status page: components with health states, incidents that carry
a chronological timeline of updates, and subscribers. The engine computes the
overall page status and per-component uptime, and renders a JSON snapshot.

Pure standard library, no network, deterministic given inputs.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional


class StatusKitError(Exception):
    """Raised on invalid input or illegal state transitions."""


# Component health, ordered worst-last so we can rank for overall status.
class ComponentStatus:
    OPERATIONAL = "operational"
    DEGRADED = "degraded_performance"
    PARTIAL = "partial_outage"
    MAJOR = "major_outage"
    MAINTENANCE = "under_maintenance"

    ALL = [OPERATIONAL, DEGRADED, PARTIAL, MAJOR, MAINTENANCE]
    # Severity rank for overall rollup (maintenance ranks low, informational).
    RANK = {
        OPERATIONAL: 0,
        MAINTENANCE: 1,
        DEGRADED: 2,
        PARTIAL: 3,
        MAJOR: 4,
    }


class IncidentStatus:
    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"
    MONITORING = "monitoring"
    RESOLVED = "resolved"

    OPEN = [INVESTIGATING, IDENTIFIED, MONITORING]
    ALL = OPEN + [RESOLVED]


class Impact:
    NONE = "none"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"

    ALL = [NONE, MINOR, MAJOR, CRITICAL]
    RANK = {NONE: 0, MINOR: 1, MAJOR: 2, CRITICAL: 3}


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_ts(ts: str) -> datetime:
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError as exc:
        raise StatusKitError(f"invalid timestamp: {ts!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class Component:
    id: str
    name: str
    status: str = ComponentStatus.OPERATIONAL
    group: Optional[str] = None


@dataclass
class IncidentUpdate:
    status: str
    body: str
    at: str = field(default_factory=_now)


@dataclass
class Incident:
    id: str
    title: str
    impact: str
    components: List[str] = field(default_factory=list)
    updates: List[IncidentUpdate] = field(default_factory=list)
    created_at: str = field(default_factory=_now)

    @property
    def status(self) -> str:
        if not self.updates:
            return IncidentStatus.INVESTIGATING
        return self.updates[-1].status

    @property
    def resolved(self) -> bool:
        return self.status == IncidentStatus.RESOLVED

    @property
    def resolved_at(self) -> Optional[str]:
        for upd in reversed(self.updates):
            if upd.status == IncidentStatus.RESOLVED:
                return upd.at
        return None

    def duration_seconds(self) -> Optional[int]:
        if not self.resolved:
            return None
        start = _parse_ts(self.created_at)
        end = _parse_ts(self.resolved_at)
        return max(0, int((end - start).total_seconds()))


@dataclass
class Subscriber:
    email: str
    components: List[str] = field(default_factory=list)  # empty == all
    confirmed_at: str = field(default_factory=_now)


class StatusKit:
    """In-memory status page state with JSON load/save."""

    def __init__(self, name: str = "Status Page"):
        self.name = name
        self.components: Dict[str, Component] = {}
        self.incidents: Dict[str, Incident] = {}
        self.subscribers: Dict[str, Subscriber] = {}

    # -- components ---------------------------------------------------------
    def add_component(self, cid: str, name: str, group: Optional[str] = None,
                      status: str = ComponentStatus.OPERATIONAL) -> Component:
        if cid in self.components:
            raise StatusKitError(f"component already exists: {cid}")
        if status not in ComponentStatus.ALL:
            raise StatusKitError(f"invalid component status: {status}")
        comp = Component(id=cid, name=name, status=status, group=group)
        self.components[cid] = comp
        return comp

    def set_component_status(self, cid: str, status: str) -> Component:
        if cid not in self.components:
            raise StatusKitError(f"unknown component: {cid}")
        if status not in ComponentStatus.ALL:
            raise StatusKitError(f"invalid component status: {status}")
        self.components[cid].status = status
        return self.components[cid]

    # -- incidents ----------------------------------------------------------
    def open_incident(self, iid: str, title: str, impact: str,
                      components: Optional[List[str]] = None,
                      body: str = "We are investigating.") -> Incident:
        if iid in self.incidents:
            raise StatusKitError(f"incident already exists: {iid}")
        if impact not in Impact.ALL:
            raise StatusKitError(f"invalid impact: {impact}")
        components = components or []
        for cid in components:
            if cid not in self.components:
                raise StatusKitError(f"unknown component: {cid}")
        inc = Incident(id=iid, title=title, impact=impact, components=list(components))
        inc.updates.append(IncidentUpdate(status=IncidentStatus.INVESTIGATING, body=body))
        self.incidents[iid] = inc
        return inc

    def update_incident(self, iid: str, status: str, body: str) -> Incident:
        if iid not in self.incidents:
            raise StatusKitError(f"unknown incident: {iid}")
        if status not in IncidentStatus.ALL:
            raise StatusKitError(f"invalid incident status: {status}")
        inc = self.incidents[iid]
        if inc.resolved:
            raise StatusKitError(f"incident already resolved: {iid}")
        inc.updates.append(IncidentUpdate(status=status, body=body))
        return inc

    def active_incidents(self) -> List[Incident]:
        return [i for i in self.incidents.values() if not i.resolved]

    # -- subscribers --------------------------------------------------------
    def subscribe(self, email: str, components: Optional[List[str]] = None) -> Subscriber:
        email = email.strip().lower()
        if not _EMAIL_RE.match(email):
            raise StatusKitError(f"invalid email: {email}")
        components = components or []
        for cid in components:
            if cid not in self.components:
                raise StatusKitError(f"unknown component: {cid}")
        sub = Subscriber(email=email, components=list(components))
        self.subscribers[email] = sub
        return sub

    def notify_targets(self, iid: str) -> List[str]:
        """Return subscriber emails that should be notified for an incident.

        A subscriber with no component filter gets everything; otherwise only
        if the incident touches one of their components.
        """
        if iid not in self.incidents:
            raise StatusKitError(f"unknown incident: {iid}")
        affected = set(self.incidents[iid].components)
        out = []
        for sub in self.subscribers.values():
            if not sub.components or (affected & set(sub.components)):
                out.append(sub.email)
        return sorted(out)

    # -- rollups ------------------------------------------------------------
    def overall_status(self) -> str:
        if not self.components:
            return ComponentStatus.OPERATIONAL
        worst = max(self.components.values(),
                    key=lambda c: ComponentStatus.RANK[c.status])
        return worst.status

    def uptime(self, window_seconds: int = 30 * 24 * 3600) -> Dict[str, float]:
        """Per-component uptime percentage over the trailing window.

        Downtime is the time a component was named in a resolved incident with
        major/critical impact, clamped to the window. Open incidents count
        downtime up to now.
        """
        if window_seconds <= 0:
            raise StatusKitError("window_seconds must be positive")
        now = datetime.now(timezone.utc)
        window_start = now.timestamp() - window_seconds
        down: Dict[str, float] = {cid: 0.0 for cid in self.components}
        for inc in self.incidents.values():
            if Impact.RANK[inc.impact] < Impact.RANK[Impact.MAJOR]:
                continue
            start = _parse_ts(inc.created_at).timestamp()
            end = (_parse_ts(inc.resolved_at).timestamp()
                   if inc.resolved else now.timestamp())
            start = max(start, window_start)
            end = min(end, now.timestamp())
            seconds = max(0.0, end - start)
            for cid in inc.components:
                if cid in down:
                    down[cid] += seconds
        result = {}
        for cid in self.components:
            pct = 100.0 * (1.0 - min(down[cid], window_seconds) / window_seconds)
            result[cid] = round(pct, 4)
        return result

    # -- serialization ------------------------------------------------------
    def snapshot(self) -> dict:
        return {
            "name": self.name,
            "generated_at": _now(),
            "overall_status": self.overall_status(),
            "components": [asdict(c) for c in self.components.values()],
            "incidents": [self._incident_dict(i) for i in self.incidents.values()],
            "active_incident_count": len(self.active_incidents()),
            "subscriber_count": len(self.subscribers),
            "uptime_30d": self.uptime(),
        }

    def _incident_dict(self, inc: Incident) -> dict:
        d = asdict(inc)
        d["status"] = inc.status
        d["resolved"] = inc.resolved
        d["resolved_at"] = inc.resolved_at
        d["duration_seconds"] = inc.duration_seconds()
        return d

    def to_json(self) -> str:
        return json.dumps(self.snapshot(), indent=2, sort_keys=True)

    # -- loading ------------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict) -> "StatusKit":
        if not isinstance(data, dict):
            raise StatusKitError("config root must be an object")
        kit = cls(name=data.get("name", "Status Page"))
        for c in data.get("components", []):
            kit.add_component(
                cid=c["id"], name=c.get("name", c["id"]),
                group=c.get("group"),
                status=c.get("status", ComponentStatus.OPERATIONAL),
            )
        for inc in data.get("incidents", []):
            obj = kit.open_incident(
                iid=inc["id"], title=inc.get("title", inc["id"]),
                impact=inc.get("impact", Impact.MINOR),
                components=inc.get("components", []),
                body=inc.get("body", "We are investigating."),
            )
            # Replace the auto first update if explicit updates are provided.
            updates = inc.get("updates")
            if updates:
                obj.updates = []
                for u in updates:
                    if u["status"] not in IncidentStatus.ALL:
                        raise StatusKitError(f"invalid incident status: {u['status']}")
                    obj.updates.append(IncidentUpdate(
                        status=u["status"], body=u.get("body", ""),
                        at=u.get("at", _now()),
                    ))
            if "created_at" in inc:
                obj.created_at = inc["created_at"]
        for s in data.get("subscribers", []):
            kit.subscribe(email=s["email"], components=s.get("components", []))
        return kit

    @classmethod
    def from_json_file(cls, path: str) -> "StatusKit":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))
