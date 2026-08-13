# GBAStation adaptation plan

## Objective

Integrate the verified two-player TCP GBA Link Cable core into GBAStation while keeping the product scope to two Nintendo Switch consoles on the same Wi-Fi network.

## Source of truth

- Maintained core fork: `https://github.com/senhaoran213/mgba`
- Verified branch: `netlink`
- Desktop integration and replay tools: this repository
- Target frontend: the current GBAStation source and its bundled mGBA revision

The mGBA fork is maintained independently. Upstream acceptance is not a dependency for GBAStation delivery.

## Integration boundaries

Move only the platform-neutral and Switch-relevant pieces:

1. `GBASIONetlink` driver and protocol state;
2. socket primitives required by the driver;
3. GBA SIO/RCNT registration hooks;
4. a GBAStation-facing Host/Join/Disconnect interface;
5. minimal connection status and error reporting.

Do not move the Qt menu implementation into GBAStation. Do not add public servers, matchmaking, Wireless Adapter/RFU, four-player sessions, GB/GBC support, ROMs, BIOS files, saves, or HOME-menu packaging during the first integration slice.

## Required order

1. Record the exact GBAStation commit, bundled mGBA commit, libnx/devkitPro versions, and current build commands.
2. Compare the GBAStation mGBA fork against `senhaoran213/mgba:netlink` at the SIO, socket, build-system, and frontend boundaries.
3. Port the core with a compile-only adapter first; preserve desktop protocol v6 compatibility.
4. Add a minimal GBAStation Host/Join/Disconnect surface without redesigning the rest of the UI.
5. Validate two desktop/LAN peers if GBAStation has a runnable desktop target; otherwise validate one GBAStation peer against the desktop deterministic peer tool.
6. Build the NRO and test two physical Switch consoles: enter, trade, exit, re-enter, trade again without reconnecting TCP.

## Acceptance

- Two players only, direct TCP, same Wi-Fi.
- Both consoles can enter the Cable Club and complete a trade.
- Both can exit and re-enter for a second trade while the TCP connection remains active.
- Host and Join controls remain responsive.
- Disconnect and reconnect recover without restarting the emulator.
- No game files or personal saves are included in source or release artifacts.
