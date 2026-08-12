#!/usr/bin/env python3
"""Validate one trace, or replay/compare both sides of a captured session offline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from netlink_trace import TraceError, compare_wire, load_trace, validate_trace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, nargs="+", help="one trace, or a Host and Join trace")
    args = parser.parse_args()
    if len(args.trace) not in (1, 2):
        parser.error("provide one or two trace files")
    try:
        loaded = [load_trace(path) for path in args.trace]
        reports = [validate_trace(events) for events in loaded]
        for path, report in zip(args.trace, reports):
            warning = f"; {', '.join(report.warnings)}" if report.warnings else ""
            print(f"OK {path}: role={report.role} tx={report.frames_tx} rx={report.frames_rx} "
                  f"transfers={report.transfers} irqs={report.irqs}{warning}")
        if len(loaded) == 2:
            sent, received = compare_wire(*loaded)
            print(f"OK paired wire replay: sent={sent} received={received}, every 28-byte frame matches")
    except (OSError, TraceError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
