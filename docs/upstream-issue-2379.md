# Proposed comment for mGBA issue #2379

I have a working desktop proof of concept for two-player GBA Link Cable communication over a direct TCP connection in mGBA 0.10.5.

The implementation adds a GBA SIO network driver and a minimal Qt Host/Join flow. Timing-sensitive behavior stays in the core: START/DATA sequencing, hardware transfer duration, SIOMULTI visibility, Busy completion, serial IRQ delivery, RCNT/GP line state, bounded clock pacing, partial TCP I/O, and disconnect-safe cleanup.

One important design point is separating the persistent TCP connection from each game-level MULTI epoch. Leaving a communication room resets the game-side cable state without closing TCP; a later room entry performs a fresh two-sided MODE handshake. The implementation also handles a final Host START crossing the Join mode transition by returning an absent-slave value, so Host cannot remain blocked at the transfer boundary.

Current validation:

- two independent Qt processes on one macOS computer;
- two separately owned FireRed/LeafGreen games and saves;
- two consecutive enter, trade, and exit flows over one TCP connection;
- deterministic trace replay and automated coverage for thousands of transfers, missing replies, mode close/reopen, and the terminal START/mode-transition race; the TCP peer tool can also inject fragmented writes for manual transport testing.

Cross-machine LAN and physical Switch testing are still pending. The prototype intentionally excludes Wireless Adapter/RFU, four-player, GB/GBC, matchmaking, and public servers.

Repository and architecture notes: https://github.com/senhaoran213/mgba-switch-netlink

Before rebasing and splitting this work onto current master, I would appreciate maintainer guidance on the preferred upstream shape. My proposed series is:

1. core SIO network-driver interface and lifecycle;
2. two-player TCP transport and protocol tests;
3. Qt Host/Join UI;
4. optional development-only trace/replay tooling.

Would this layering fit the direction intended for networked multiplayer link support, or would you prefer a different transport/core boundary?
