#!/usr/bin/env python3

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from netlink_trace import PROTOCOL_VERSION, TraceError, compare_wire, validate_trace


def frame(frame_type: int, sender_role: int, session: int, sequence: int = 0, value: int = 0) -> bytes:
    output = bytearray(28)
    output[:4] = b"MGNL"
    output[4:8] = bytes((PROTOCOL_VERSION, frame_type, sender_role, 2))
    output[8:12] = session.to_bytes(4, "big")
    output[12:16] = sequence.to_bytes(4, "big")
    output[16:18] = value.to_bytes(2, "big")
    return bytes(output)


def frame_event(role: str, direction: str, raw: bytes, line: int) -> dict:
    names = {
        1: "hello", 2: "welcome", 3: "ready", 4: "start", 5: "data",
        6: "gp", 7: "close", 8: "mode",
    }
    return {"trace_version": 1, "order": line, "_line": line, "event": "frame", "role": role,
            "dir": direction, "frame_type": names[raw[5]], "seq": int.from_bytes(raw[12:16], "big"),
            "frame": raw.hex()}


def pair() -> tuple[list[dict], list[dict]]:
    session = 0x12345678
    hello = frame(1, 1, 0)
    welcome = frame(2, 0, session)
    ready = frame(3, 1, session)
    host_mode = frame(8, 0, session, 0, 1)
    join_mode = frame(8, 1, session, 0, 1)
    start = frame(4, 0, session, 1, 0xB9A0)
    data = frame(5, 1, session, 1, 0x2222)
    host = [frame_event("host", direction, raw, index) for index, (direction, raw) in enumerate(
        (("rx", hello), ("tx", welcome), ("rx", ready), ("tx", host_mode),
         ("rx", join_mode), ("tx", start), ("rx", data)), 1)]
    join = [frame_event("join", direction, raw, index) for index, (direction, raw) in enumerate(
        (("tx", hello), ("rx", welcome), ("tx", ready), ("rx", host_mode),
         ("tx", join_mode), ("rx", start), ("tx", data)), 1)]
    for events, role in ((host, "host"), (join, "join")):
        line = len(events) + 1
        events.append({"trace_version": 1, "order": line, "_line": line, "event": "connection_state", "role": role, "to": "ready"})
        line = len(events) + 1
        events.append({"trace_version": 1, "order": line, "_line": line, "event": "sio_complete", "role": role,
                       "session": session, "seq": 1})
    return host, join


def long_pair(transfers: int) -> tuple[list[dict], list[dict]]:
    session = 0x12345678
    hello = frame(1, 1, 0)
    welcome = frame(2, 0, session)
    ready = frame(3, 1, session)
    host_mode = frame(8, 0, session, 0, 1)
    join_mode = frame(8, 1, session, 0, 1)
    host = [frame_event("host", direction, raw, index) for index, (direction, raw) in enumerate(
        (("rx", hello), ("tx", welcome), ("rx", ready), ("tx", host_mode),
         ("rx", join_mode)), 1)]
    join = [frame_event("join", direction, raw, index) for index, (direction, raw) in enumerate(
        (("tx", hello), ("rx", welcome), ("tx", ready), ("rx", host_mode),
         ("tx", join_mode)), 1)]
    for events, role in ((host, "host"), (join, "join")):
        line = len(events) + 1
        events.append({"trace_version": 1, "order": line, "_line": line,
                       "event": "connection_state", "role": role, "to": "ready"})
    for sequence in range(1, transfers + 1):
        start = frame(4, 0, session, sequence, sequence & 0xFFFF)
        data = frame(5, 1, session, sequence, (sequence * 3) & 0xFFFF)
        for events, role, directions in ((host, "host", ("tx", "rx")),
                                         (join, "join", ("rx", "tx"))):
            for direction, raw in zip(directions, (start, data)):
                line = len(events) + 1
                events.append(frame_event(role, direction, raw, line))
            line = len(events) + 1
            events.append({"trace_version": 1, "order": line, "_line": line,
                           "event": "sio_complete", "role": role,
                           "session": session, "seq": sequence})
    return host, join


class NetlinkTraceTests(unittest.TestCase):
    def test_valid_pair_replays_exact_wire(self) -> None:
        host, join = pair()
        self.assertEqual(validate_trace(host).transfers, 1)
        self.assertEqual(validate_trace(join).transfers, 1)
        self.assertEqual(compare_wire(host, join), (7, 7))

    def test_two_player_transfer_has_no_completion_ack(self) -> None:
        host, join = pair()
        self.assertEqual([event["frame_type"] for event in host if event["event"] == "frame"],
                         ["hello", "welcome", "ready", "mode", "mode", "start", "data"])
        self.assertEqual([event["frame_type"] for event in join if event["event"] == "frame"],
                         ["hello", "welcome", "ready", "mode", "mode", "start", "data"])

    def test_wire_mismatch_is_reported(self) -> None:
        host, join = pair()
        damaged = bytearray.fromhex(join[3]["frame"])
        damaged[16] ^= 1
        join[3]["frame"] = damaged.hex()
        with self.assertRaisesRegex(TraceError, "wire mismatch"):
            compare_wire(host, join)

    def test_completion_without_start_is_rejected(self) -> None:
        host, _ = pair()
        host = [event for event in host
                if not (event.get("event") == "frame"
                        and event.get("frame_type") in {"start", "data"})]
        for line, event in enumerate(host, 1):
            event["order"] = event["_line"] = line
        with self.assertRaisesRegex(TraceError, "completion without START"):
            validate_trace(host)

    def test_completion_without_data_is_rejected(self) -> None:
        host, _ = pair()
        host = [event for event in host
                if not (event.get("event") == "frame" and event.get("frame_type") == "data")]
        for line, event in enumerate(host, 1):
            event["order"] = event["_line"] = line
        with self.assertRaisesRegex(TraceError, "completion without DATA"):
            validate_trace(host)

    def test_protocol_v5_is_rejected(self) -> None:
        host, _ = pair()
        damaged = bytearray.fromhex(host[0]["frame"])
        damaged[4] = 5
        host[0]["frame"] = damaged.hex()
        with self.assertRaisesRegex(TraceError, "protocol-v6"):
            validate_trace(host)

    def test_mode_epoch_can_close_and_reopen_without_resetting_tcp(self) -> None:
        host, join = pair()
        session = 0x12345678
        for events, role, directions in ((host, "host", ("tx", "rx")),
                                         (join, "join", ("rx", "tx"))):
            for direction, active in zip(directions, (0, 0)):
                sender = 0 if ((role == "host" and direction == "tx")
                               or (role == "join" and direction == "rx")) else 1
                raw = frame(8, sender, session, 1, active)
                line = len(events) + 1
                events.append(frame_event(role, direction, raw, line))
            for direction, sender, active in ((directions[0], 0, 1), (directions[1], 1, 1)):
                raw = frame(8, sender, session, 1, active)
                line = len(events) + 1
                events.append(frame_event(role, direction, raw, line))
        self.assertEqual(compare_wire(host, join), (11, 11))

    def test_crossed_start_gets_terminal_absent_slave_data(self) -> None:
        host, join = pair()
        session = 0x12345678
        start = frame(4, 0, session, 2, 0xB9A0)
        inactive = frame(8, 1, session, 1, 0)
        terminal = frame(5, 1, session, 2, 0xFFFF)
        for events, role, wire in (
                (host, "host", (("tx", start), ("rx", inactive), ("rx", terminal))),
                (join, "join", (("rx", start), ("tx", inactive), ("tx", terminal)))):
            for direction, raw in wire:
                line = len(events) + 1
                events.append(frame_event(role, direction, raw, line))
        line = len(host) + 1
        host.append({"trace_version": 1, "order": line, "_line": line,
                     "event": "sio_complete", "role": "host", "session": session, "seq": 2})
        self.assertEqual(validate_trace(host).transfers, 2)
        self.assertEqual(validate_trace(join).transfers, 1)
        self.assertEqual(compare_wire(host, join), (10, 10))

    def test_thousands_of_two_player_transfers_keep_one_reply_per_start(self) -> None:
        host, join = long_pair(4096)
        self.assertEqual(validate_trace(host).transfers, 4096)
        self.assertEqual(validate_trace(join).transfers, 4096)
        self.assertEqual(compare_wire(host, join), (8197, 8197))


if __name__ == "__main__":
    unittest.main()
