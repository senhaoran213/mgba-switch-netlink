# desktop-poc-v1

First public desktop proof of concept for two-player GBA Link Cable communication over a direct TCP connection in mGBA 0.10.5.

## Verified

- Two independent mGBA Qt processes on macOS.
- Host/Join connection over localhost TCP.
- Two separately owned FireRed/LeafGreen game images and save files.
- Two consecutive enter, trade, and room-exit flows over one persistent TCP session.
- Automated protocol and deterministic replay tests.

## Not yet verified

- Two different desktop computers on a LAN.
- Physical Nintendo Switch hardware.
- Pokémon battle or communication evolution.
- Wireless Adapter/RFU, four-player, or GB/GBC communication.

## Build

```sh
cmake -S third_party/mgba-0.10.5 -B build/mgba-qt \
  -DBUILD_QT=ON -DBUILD_SDL=OFF -DBUILD_TEST=OFF
cmake --build build/mgba-qt -j4
```

The macOS application is generated at:

```text
build/mgba-qt/qt/mGBA.app
```

The release archive is an ad-hoc signed Apple Silicon build. macOS may require users to explicitly allow the application on first launch. It is not notarized by Apple.

## Test

```sh
python3 -m unittest discover -s tests -v
```

## Legal and privacy

This release contains no ROM, BIOS, save, or game-guide content. Users must provide legally obtained game and firmware files. The modified mGBA source files remain under MPL-2.0.

## macOS arm64 archive

```text
mgba-switch-netlink-desktop-poc-v1-macos-arm64.zip
SHA-256: 58f59d20bd0d9fecb095ffebb68c291134501f4259b7852ecc6a8e9f93fb46c9
```
