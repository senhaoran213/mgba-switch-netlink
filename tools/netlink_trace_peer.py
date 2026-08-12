#!/usr/bin/env python3
"""Use a captured trace as a deterministic TCP peer for one mGBA instance."""

from __future__ import annotations

import argparse
import secrets
import socket
import sys
from pathlib import Path

from netlink_trace import TraceError, frame_bytes, load_trace, validate_trace


def endpoint(value: str) -> tuple[str, int]:
    host, separator, port = value.rpartition(":")
    if not separator or not host or not port.isdigit() or not 0 < int(port) < 65536:
        raise argparse.ArgumentTypeError("expected HOST:PORT")
    return host, int(port)


def recv_exact(connection: socket.socket, size: int) -> bytes:
    output = bytearray()
    while len(output) < size:
        chunk = connection.recv(size - len(output))
        if not chunk:
            raise TraceError(f"peer closed with {size - len(output)} bytes still expected")
        output.extend(chunk)
    return bytes(output)


def patch_session(frame: bytes, session: int) -> bytes:
    if frame[5] == 1:  # HELLO always carries session zero.
        return frame
    result = bytearray(frame)
    result[8:12] = session.to_bytes(4, "big")
    return bytes(result)


def comparable_frame(frame: bytes) -> bytes:
    """Remove emulator-clock fields that legitimately change on a new run."""
    result = bytearray(frame)
    if result[5] in (2, 4):  # WELCOME link clock and START host gap
        result[20:24] = b"\0\0\0\0"
    return bytes(result)


def run_peer(events: list[dict], connection: socket.socket, fragment: int) -> None:
    report = validate_trace(events)
    wire = [event for event in events if event.get("event") == "frame"]
    session = secrets.randbits(32) or 1 if report.role == "join" else 0
    for index, event in enumerate(wire, 1):
        recorded = frame_bytes(event)
        if event["dir"] == "tx":  # The emulator under test must reproduce the recorded local send.
            actual = recv_exact(connection, len(recorded))
            if actual[5] == 2:  # Host WELCOME selects the live session nonce.
                session = int.from_bytes(actual[8:12], "big")
            expected = patch_session(recorded, session)
            if comparable_frame(actual) != comparable_frame(expected):
                raise TraceError(f"frame {index}: emulator output differs ({event['frame_type']} seq={event['seq']})")
            print(f"EXPECT OK {index}: {event['frame_type']} seq={event['seq']}")
        else:  # Send what the recorded local emulator received from its peer.
            outgoing = patch_session(recorded, session)
            step = fragment or len(outgoing)
            for offset in range(0, len(outgoing), step):
                connection.sendall(outgoing[offset:offset + step])
            print(f"SEND {index}: {event['frame_type']} seq={event['seq']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="trace recorded by the local role to reproduce")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--listen", type=endpoint, metavar="HOST:PORT", help="listen when replaying a local Join trace")
    mode.add_argument("--connect", type=endpoint, metavar="HOST:PORT", help="connect when replaying a local Host trace")
    parser.add_argument("--fragment", type=int, default=0, help="split sent frames into N-byte TCP writes")
    args = parser.parse_args()
    if args.fragment < 0:
        parser.error("--fragment must be non-negative")
    try:
        events = load_trace(args.trace)
        role = validate_trace(events).role
        if args.listen and role != "join":
            raise TraceError("--listen requires a trace whose recorded local role is join")
        if args.connect and role != "host":
            raise TraceError("--connect requires a trace whose recorded local role is host")
        if args.listen:
            with socket.socket() as server:
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind(args.listen)
                server.listen(1)
                print(f"Listening on {args.listen[0]}:{args.listen[1]}...")
                connection, address = server.accept()
                print(f"Accepted {address[0]}:{address[1]}")
                with connection:
                    run_peer(events, connection, args.fragment)
        else:
            with socket.create_connection(args.connect) as connection:
                run_peer(events, connection, args.fragment)
    except (OSError, TraceError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("Replay completed without divergence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
