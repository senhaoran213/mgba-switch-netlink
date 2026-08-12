# mGBA Network Link Architecture

## Status

This project implements a two-player GBA Link Cable transport over a direct TCP connection in mGBA 0.10.5. It is intentionally limited to GBA multiplayer cable mode. It does not implement a public server, matchmaking, Wireless Adapter/RFU, four-player sessions, or GB/GBC linking.

The verified desktop baseline is two independent Qt processes on one macOS computer. Two separately owned FireRed/LeafGreen game images and saves completed two consecutive enter, trade, and exit flows without disconnecting the TCP session between rooms. Cross-machine LAN and physical Nintendo Switch validation remain pending.

## Layering

The Qt frontend owns Host/Join commands, address input, status reporting, and disconnect. The GBA core owns every timing-sensitive operation:

```text
Qt Host/Join UI
  -> persistent TCP session
  -> MGNL framed transport
  -> GBASIONetlink driver
  -> SIOCNT / RCNT / SIOMULTI registers
  -> GBA serial IRQ
```

Local same-process multiplayer is not reused. Each process runs one GBA core with one network SIO driver.

## TCP session and game epoch

A persistent TCP session is separate from a game-level multiplayer epoch. Entering and leaving a Cable Club room changes the GBA serial mode even though the user has not disconnected the network menu.

`MODE active/inactive` frames synchronize that lifecycle:

- both peers must be in a fresh MULTI epoch before Cable Ready is asserted;
- leaving MULTI clears Busy, pending START, transfer state, link clock, pacing state, and Cable Ready;
- the TCP socket and monotonically increasing transport sequence remain alive;
- returning to MULTI establishes a new game epoch without reconnecting TCP.

If a final Host START crosses the Join transition out of MULTI, Join returns `DATA=FFFF`. This models an absent slave for that terminal clock and lets Host clear Busy and deliver its serial IRQ instead of waiting forever.

## Transfer contract

The two-player wire transfer is:

```text
Host START(sequence, host word, start clock, SIOCNT)
Join DATA(sequence, join word)
```

Join completes after its local hardware transfer duration. Host completes only when both the local hardware boundary and matching DATA have arrived. The master's word becomes visible in `SIOMULTI0` during the active transfer; unavailable slots remain `FFFF`.

The protocol uses fixed 28-byte frames, a per-connection Host nonce, strict role/session/sequence validation, a bounded transmit FIFO, partial-send cursors, and receive accumulation for fragmented TCP reads.

## Clock pacing

TCP wall time must not become uncontrolled emulated time. Host pauses at the hardware completion boundary while waiting for DATA, using short socket-readable waits. Join preserves excess emulated cycles across transfers so long sessions cannot silently accumulate clock lead.

After the first completed transfer, an ahead limiter keeps Join within a small distance of the Host transfer stream. It is active only during a live MULTI epoch with serial IRQ enabled. Every completed transfer gives the game one frame of grace before the limiter can engage, allowing room-exit code to clear IRQ and change serial mode without being slowed to one emulated cycle per socket wait.

## RCNT and GP lines

In MULTI mode, RCNT line phases identify Host/Join and active/idle cable state. General-Purpose RCNT state is exchanged separately, input pins are merged with cable pull-up/cross-wire behavior, and an SI falling edge can raise the serial IRQ. NORMAL32 is intentionally not attached because it belongs to a different peripheral path.

## Diagnostics without timing distortion

High-frequency synchronous logging can change emulator performance and protocol timing. Default diagnostics therefore use fixed-size in-memory rings and write CSV only during disconnect or destruction. Full JSONL tracing is opt-in through `MGBA_NETLINK_TRACE=1`, buffered, and intended only for development.

The replay tools validate captured frame order and can substitute a deterministic TCP peer. Tests cover thousands of sequential transfers, protocol mismatch, missing DATA, wire mismatch, game-epoch close/reopen, and a START crossing the Join mode transition.

## Validation boundary

Passing automated tests proves protocol invariants, not game compatibility. Manual acceptance must be reported separately for localhost desktop, cross-machine LAN, and physical Switch hardware. No game files, BIOS files, or saves belong in this repository or its releases.
