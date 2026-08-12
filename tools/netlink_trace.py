#!/usr/bin/env python3
"""Shared parser and deterministic validator for mGBA Network Link JSONL traces."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

FRAME_SIZE = 28
PROTOCOL_VERSION = 6
FRAME_TYPES = {
    1: "hello", 2: "welcome", 3: "ready", 4: "start", 5: "data",
    6: "gp", 7: "close", 8: "mode",
}


class TraceError(ValueError):
    pass


def load_trace(path: Path) -> list[dict]:
    events: list[dict] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise TraceError(f"{path}:{line_number}: invalid JSON: {error}") from error
            if event.get("trace_version") != 1:
                raise TraceError(f"{path}:{line_number}: unsupported trace_version")
            event["_line"] = line_number
            events.append(event)
    if not events:
        raise TraceError(f"{path}: empty trace")
    orders = [event.get("order") for event in events]
    if orders != list(range(1, len(events) + 1)):
        raise TraceError(f"{path}: order is not contiguous from 1")
    return events


def frame_bytes(event: dict) -> bytes:
    try:
        frame = bytes.fromhex(event["frame"])
    except (KeyError, ValueError) as error:
        raise TraceError(f"line {event.get('_line')}: invalid frame hex") from error
    if len(frame) != FRAME_SIZE or frame[:4] != b"MGNL" or frame[4] != PROTOCOL_VERSION:
        raise TraceError(f"line {event.get('_line')}: invalid protocol-v{PROTOCOL_VERSION} frame")
    if FRAME_TYPES.get(frame[5]) != event.get("frame_type"):
        raise TraceError(f"line {event.get('_line')}: frame_type disagrees with bytes")
    return frame


@dataclass
class TraceReport:
    role: str
    frames_tx: int = 0
    frames_rx: int = 0
    transfers: int = 0
    irqs: int = 0
    ready: bool = False
    closed: bool = False
    warnings: list[str] = field(default_factory=list)


def validate_trace(events: Iterable[dict]) -> TraceReport:
    events = list(events)
    roles = {event.get("role") for event in events if event.get("role") in {"host", "join"}}
    if len(roles) != 1:
        raise TraceError(f"trace must contain one role, got {sorted(roles)}")
    role = roles.pop()
    report = TraceReport(role=role)
    starts: dict[tuple[int, int], dict] = {}
    replies: set[tuple[int, int]] = set()
    completed: set[tuple[int, int]] = set()
    last_start: dict[int, int] = {}
    handshake = []

    for event in events:
        kind = event.get("event")
        if kind == "connection_state" and event.get("to") == "ready":
            report.ready = True
        elif kind in {"close", "trace_end"}:
            report.closed = True
        elif kind == "sio_complete":
            key = (int(event.get("session", -1)), int(event.get("seq", -1)))
            if key not in starts:
                raise TraceError(f"line {event['_line']}: completion without START session={key[0]} seq={key[1]}")
            if key not in replies:
                raise TraceError(f"line {event['_line']}: completion without DATA session={key[0]} seq={key[1]}")
            if key in completed:
                raise TraceError(f"line {event['_line']}: duplicate completion session={key[0]} seq={key[1]}")
            completed.add(key)
            report.transfers += 1
        elif kind == "sio_irq":
            report.irqs += 1
        elif kind == "frame":
            frame = frame_bytes(event)
            direction = event.get("dir")
            if direction == "tx":
                report.frames_tx += 1
            elif direction == "rx":
                report.frames_rx += 1
            else:
                raise TraceError(f"line {event['_line']}: invalid frame direction")
            frame_type = FRAME_TYPES[frame[5]]
            if frame_type in {"hello", "welcome", "ready"}:
                handshake.append((direction, frame_type))
            if frame_type == "start" and ((role == "host" and direction == "tx") or (role == "join" and direction == "rx")):
                session = int.from_bytes(frame[8:12], "big")
                sequence = int.from_bytes(frame[12:16], "big")
                expected = last_start.get(session, 0) + 1
                if sequence != expected:
                    raise TraceError(f"line {event['_line']}: START sequence {sequence}, expected {expected}")
                if sequence > 1 and (session, sequence - 1) not in replies:
                    raise TraceError(f"line {event['_line']}: START sequence {sequence} precedes DATA for {sequence - 1}")
                starts[(session, sequence)] = event
                last_start[session] = sequence
            elif frame_type == "data" and ((role == "host" and direction == "rx") or (role == "join" and direction == "tx")):
                key = (int.from_bytes(frame[8:12], "big"), int.from_bytes(frame[12:16], "big"))
                if key not in starts:
                    raise TraceError(f"line {event['_line']}: DATA without START session={key[0]} seq={key[1]}")
                if key in replies:
                    raise TraceError(f"line {event['_line']}: duplicate DATA session={key[0]} seq={key[1]}")
                replies.add(key)

    expected_handshake = ([('rx', 'hello'), ('tx', 'welcome'), ('rx', 'ready')]
                          if role == "host" else [('tx', 'hello'), ('rx', 'welcome'), ('tx', 'ready')])
    if handshake[:3] != expected_handshake:
        raise TraceError(f"{role} handshake is {handshake[:3]}, expected {expected_handshake}")
    if not report.ready:
        raise TraceError("connection never reached ready")
    unfinished = sorted(set(starts) - completed)
    if unfinished:
        report.warnings.append(f"unfinished transfers: {unfinished[:10]}")
    missing_replies = sorted(set(starts) - replies)
    if missing_replies:
        report.warnings.append(f"transfers without DATA: {missing_replies[:10]}")
    return report


def compare_wire(left: Iterable[dict], right: Iterable[dict]) -> tuple[int, int]:
    left = list(left)
    right = list(right)
    left_role = next(event["role"] for event in left if event.get("role") in {"host", "join"})
    right_role = next(event["role"] for event in right if event.get("role") in {"host", "join"})
    if left_role == right_role:
        raise TraceError("paired traces must have opposite roles")
    left_tx = [frame_bytes(event) for event in left if event.get("event") == "frame" and event.get("dir") == "tx"]
    right_rx = [frame_bytes(event) for event in right if event.get("event") == "frame" and event.get("dir") == "rx"]
    right_tx = [frame_bytes(event) for event in right if event.get("event") == "frame" and event.get("dir") == "tx"]
    left_rx = [frame_bytes(event) for event in left if event.get("event") == "frame" and event.get("dir") == "rx"]
    for label, sent, received in ((f"{left_role}-> {right_role}", left_tx, right_rx), (f"{right_role}-> {left_role}", right_tx, left_rx)):
        if len(sent) != len(received):
            raise TraceError(f"{label}: sent {len(sent)} frames but received {len(received)}")
        for index, (expected, actual) in enumerate(zip(sent, received), 1):
            if expected != actual:
                raise TraceError(f"{label}: first wire mismatch at frame {index}")
    return len(left_tx) + len(right_tx), len(left_rx) + len(right_rx)
