"""Command line interface for STATUSKIT.

Subcommands:
  status     <config>            print overall + per-component status
  uptime     <config>            per-component uptime %
  incidents  <config>            list incidents and timelines
  subscribers <config>           list subscribers
  notify     <config> <inc-id>   resolve which subscribers to notify
  check      <config>            health gate: non-zero exit if not operational

Exit codes: 0 ok, 1 findings (non-operational / active incidents on `check`),
2 usage/error.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import TOOL_NAME, TOOL_VERSION
from .core import StatusKit, StatusKitError, ComponentStatus


def _emit(payload: dict, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    # table
    for line in _as_table(payload):
        print(line)


def _as_table(payload: dict) -> List[str]:
    rows: List[str] = []
    kind = payload.get("_kind")
    if kind == "status":
        rows.append(f"overall: {payload['overall_status']}")
        for c in payload["components"]:
            grp = f" [{c['group']}]" if c.get("group") else ""
            rows.append(f"  {c['id']:<16} {c['status']}{grp}")
    elif kind == "uptime":
        for cid, pct in sorted(payload["uptime"].items()):
            rows.append(f"  {cid:<16} {pct:>8.4f}%")
    elif kind == "incidents":
        if not payload["incidents"]:
            rows.append("no incidents")
        for inc in payload["incidents"]:
            state = "RESOLVED" if inc["resolved"] else inc["status"].upper()
            rows.append(f"[{state}] {inc['id']} ({inc['impact']}) {inc['title']}")
            for u in inc["updates"]:
                rows.append(f"    {u['at']}  {u['status']}: {u['body']}")
    elif kind == "subscribers":
        for s in payload["subscribers"]:
            scope = ",".join(s["components"]) if s["components"] else "ALL"
            rows.append(f"  {s['email']:<32} -> {scope}")
    elif kind == "notify":
        rows.append(f"incident {payload['incident']} -> {len(payload['targets'])} target(s)")
        for t in payload["targets"]:
            rows.append(f"  {t}")
    elif kind == "check":
        rows.append(f"overall: {payload['overall_status']}")
        rows.append(f"active incidents: {payload['active_incident_count']}")
        rows.append("OK" if payload["ok"] else "FAIL")
    return rows


def _load(path: str) -> StatusKit:
    return StatusKit.from_json_file(path)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=TOOL_NAME, description="Self-hosted status page engine.")
    p.add_argument("--version", action="version",
                   version=f"{TOOL_NAME} {TOOL_VERSION}")
    p.add_argument("--format", choices=["table", "json"], default="table")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("status", "uptime", "incidents", "subscribers", "check"):
        sp = sub.add_parser(name, help=f"{name} report")
        sp.add_argument("config", help="path to status page JSON config")

    sp = sub.add_parser("notify", help="resolve subscriber notify targets")
    sp.add_argument("config")
    sp.add_argument("incident", help="incident id")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        kit = _load(args.config)
    except (OSError, ValueError, StatusKitError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        if args.cmd == "status":
            snap = kit.snapshot()
            payload = {"_kind": "status",
                       "overall_status": snap["overall_status"],
                       "components": snap["components"]}
            _emit(payload, args.format)
            return 0 if snap["overall_status"] == ComponentStatus.OPERATIONAL else 1

        if args.cmd == "uptime":
            payload = {"_kind": "uptime", "uptime": kit.uptime()}
            _emit(payload, args.format)
            return 0

        if args.cmd == "incidents":
            snap = kit.snapshot()
            payload = {"_kind": "incidents", "incidents": snap["incidents"]}
            _emit(payload, args.format)
            return 1 if kit.active_incidents() else 0

        if args.cmd == "subscribers":
            from dataclasses import asdict
            payload = {"_kind": "subscribers",
                       "subscribers": [asdict(s) for s in kit.subscribers.values()]}
            _emit(payload, args.format)
            return 0

        if args.cmd == "notify":
            targets = kit.notify_targets(args.incident)
            payload = {"_kind": "notify", "incident": args.incident,
                       "targets": targets}
            _emit(payload, args.format)
            return 0

        if args.cmd == "check":
            snap = kit.snapshot()
            ok = (snap["overall_status"] == ComponentStatus.OPERATIONAL
                  and snap["active_incident_count"] == 0)
            payload = {"_kind": "check",
                       "overall_status": snap["overall_status"],
                       "active_incident_count": snap["active_incident_count"],
                       "ok": ok}
            _emit(payload, args.format)
            return 0 if ok else 1
    except StatusKitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
