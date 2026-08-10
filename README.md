# mgba-switch-netlink

一个独立的 mGBA GBA Link Cable 研发项目。目标是先验证两台 Nintendo Switch 在同一 Wi-Fi 下通过 TCP 完成两人 GBA 有线 Link Cable；不是通用模拟器前端，也不在当前阶段整合 GBAStation。

## 范围

- 仅两人、同一局域网、GBA 有线 Link Cable。
- 不做公网/服务器/匹配、Wireless Adapter、四人联机、GB/GBC、ROM/BIOS/个人存档或 GBAStation UI。
- ROM 必须由设备所有者合法备份；仓库不包含 ROM、BIOS、存档或 Switch 密钥。

## 路线

1. **阶段 0**：固定 mGBA 版本并绘制本地 Link Cable 代码地图。
2. **阶段 1（当前）**：验证桌面同进程双核心/双窗口本地通信基线，并记录 SIO 事件。
3. **阶段 2**：桌面双进程 TCP Link Cable 原型。
4. **阶段 3**：Switch TCP 传输层与最小 Host/Join。
5. **阶段 4**：两台实体 Switch 完成交换、对战、通信进化验收。
6. **阶段 5**：再评估 GBAStation 菜单整合与发布包。

阶段 1 已确认 GBAStation 最新源码使用的 mGBA 0.10.5 的本地联机是一个进程内 `GBASIOLockstep`，不是两个独立进程；因此“桌面双实例”在此阶段严格指 Qt 前端管理的双核心/双窗口。本项目将网络化推迟至阶段 2。

## 当前基线

- GBAStation 最新 `main` 提交 `4d346b0492ed51009999e91adda52d5f6e9b17df` 内置 mGBA 0.10.5；本项目对应官方基线为 `26b7884bc25a5933960f3cdcd98bac1ae14d42e2`。
- 代码入口、日志语义、网络接入边界与验收限制见 [docs/phase-1-code-map.md](docs/phase-1-code-map.md)。
- 调试日志使用 `GBA Serial I/O` 类别的 DEBUG 级别，新增行以 `NETLINK` 开头。

## 下一步门槛

阶段 2 可以开始的前提是：用两份合法自备的 FireRed/LeafGreen 存档，在 Qt 本地多人模式完成一次交换，并保存同一轮通信的 `SIO_START`、`LOCAL_REMOTE_RESPONSE`、`SIO_COMPLETE`、`SIO_IRQ` 日志。仅通过编译不构成游戏或双机验收。
