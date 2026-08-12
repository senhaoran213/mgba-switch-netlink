# mgba-switch-netlink

一个独立的 mGBA GBA Link Cable 研发项目。目标是先验证两台 Nintendo Switch 在同一 Wi-Fi 下通过 TCP 完成两人 GBA 有线 Link Cable；不是通用模拟器前端，也不在当前阶段整合 GBAStation。

## 已验证成果

当前桌面原型已经在两个独立 mGBA Qt 进程中完成以下人工验收：

- 两人 GBA Link Cable TCP 直连；
- 使用两份独立、合法自备的 FireRed/LeafGreen 游戏与存档完成交换；
- 同一条 TCP 连接内连续两次进入通信房间、交换并正常退出；
- Host/Join 的动画与操作保持可接受同步；
- 退出游戏内房间不会关闭 Qt 中的 Host/Join 网络连接。

自动测试覆盖协议帧配对、长序列传输、跨模式末轮传输和连续两个游戏内 MULTI epoch。上述结果仅证明 macOS localhost 桌面原型；尚未证明跨两台电脑、两台实体 Switch、对战或通信进化。

项目不提供 ROM、BIOS、存档或其他游戏内容。测试者必须自行合法取得这些文件。

## 范围

- 仅两人、同一局域网、GBA 有线 Link Cable。
- 不做公网/服务器/匹配、Wireless Adapter、四人联机、GB/GBC、ROM/BIOS/个人存档或 GBAStation UI。
- ROM 必须由设备所有者合法备份；仓库不包含 ROM、BIOS、存档或 Switch 密钥。

## 路线

1. **阶段 0**：固定 mGBA 版本并绘制本地 Link Cable 代码地图。
2. **阶段 1（已完成基线）**：验证桌面同进程双核心/双窗口本地通信基线，并记录 SIO 事件。
3. **阶段 2（当前）**：桌面双进程 TCP Link Cable 原型及可重复轨迹回放。
4. **阶段 3**：Switch TCP 传输层与最小 Host/Join。
5. **阶段 4**：两台实体 Switch 完成交换、对战、通信进化验收。
6. **阶段 5**：再评估 GBAStation 菜单整合与发布包。

阶段 1 已确认 GBAStation 最新源码使用的 mGBA 0.10.5 的本地联机是一个进程内 `GBASIOLockstep`，不是两个独立进程；因此“桌面双实例”在此阶段严格指 Qt 前端管理的双核心/双窗口。本项目将网络化推迟至阶段 2。

## 当前基线

- GBAStation 最新 `main` 提交 `4d346b0492ed51009999e91adda52d5f6e9b17df` 内置 mGBA 0.10.5；本项目对应官方基线为 `26b7884bc25a5933960f3cdcd98bac1ae14d42e2`。
- 代码入口、日志语义、网络接入边界与验收限制见 [docs/phase-1-code-map.md](docs/phase-1-code-map.md)。
- 调试日志使用 `GBA Serial I/O` 类别的 DEBUG 级别，新增行以 `NETLINK` 开头。

## 网络轨迹与代码复现

开发版默认不采集轨迹，避免大厅高频 SIO 产生十万行 JSON 格式化并干扰模拟性能。仅在排障时设置 `MGBA_NETLINK_TRACE=1`，Qt 才会在项目根目录的 `netlink-traces/` 建立独立 JSONL；该目录已被 Git 忽略，连接进度窗口会显示完整路径。文件不记录 ROM、BIOS 或存档内容，正式 Switch 发布构建会移除该诊断入口。

普通启动仍会在内存中循环保留最近 512 轮极小的 SIO 锁存诊断，Disconnect/退出时才一次性写出 `diagnostic-*.csv`。它用于对齐 `SIOMLT_SEND` 最近写入、Host START、Join 实际锁存和完成周期；运行中不做文件 I/O，也不改变 Link 调度。

为排查交换完成后的退出黑屏，同一次 Disconnect 还会写出对应的 `diagnostic-*.csv.state.csv`。它只在内存中循环保留最近 256 个状态事件，包括 MULTI load/unload、GP 进入/退出、SIOCNT 写入、ahead hold 进入/退出、pending/discard START，以及当时的 mode、RCNT、SIOCNT 和 `sessionLive`；运行中同样不做文件 I/O。

```sh
MGBA_NETLINK_TRACE=1 build/mgba-qt/qt/mGBA.app/Contents/MacOS/mGBA
```

为避免开发采集改变模拟时序，轨迹使用 1 MiB 文件缓冲、每 4096 条或关键状态才刷新，并且只有真正发生 TCP 半包时才记录 `tcp_chunk`。Host 到达硬件传输边界后会冻结模拟时间，以最长 1 ms、可被 socket 数据提前唤醒的小段等待远端结果；不能在等待期间继续推进游戏时间，否则《火红/叶绿》会先于远端响应触发通信超时。

Host 写入 SIOCNT START 时必须同时重置 `linkTime` 和其 `lastCycle` 原点。START 可能发生在两个 transport callback 之间；只清 `linkTime` 会把 START 前的空闲周期计入本轮，导致 Host 早于两人 MULTI 所需的 6075 周期清 Busy/发 IRQ。

MULTI 传输开始后，Host 字必须立即出现在双方的 `SIOMULTI0`，未接收及缺席槽保持 `FFFF`；本地字和完成状态仍在硬件传输周期结束时提交。不能把四个接收寄存器全部推迟到完成 IRQ 前才写回，因为游戏可以在 Busy 期间轮询这些寄存器。

Join 收到 START 时若已经越过 Host 发布的开始边界，只扣除该边界而不能把 `linkTime` 全部清零。保留的超额周期会继续计入本轮完成和后续领先量，使三帧 ahead limiter 真正约束累计漂移；否则每轮丢弃少量超前，长会话中 Join 会领先数十帧并呈现“多次按键后突然执行”的快跑/冻结。

当前两人线协议为 `MGNL` v6：传输使用 `START → DATA`，不增加额外完成确认往返；新增 `MODE` 只同步一次游戏内 MULTI epoch 的进入/退出，TCP Host/Join 本身不断开。Join 在自己的硬件周期结束后独立提交，Host 收到 DATA 且到达本地硬件边界后提交；Host 下一轮 START 若提前到达 Join，只允许缓存一轮并在当前轮完成后消费。MULTI 的 RCNT 线路阶段分别保持 Host 活跃/空闲 `2/3`、Join 活跃/空闲 `6/7`。退房时双方清 Busy、pending、时钟、限速和 Cable Ready；再次进入时必须交换新的 active MODE 才恢复 Ready。若最后一轮 START 与 Join 离开 MULTI 交叉，Join 返回该序号的 `DATA=FFFF` 模拟缺席从机并让 Host 正常完成 IRQ，不能静默丢弃后让 Host 永久等待。

Join 的 ahead limiter 只允许在 `SIO_MULTI` 的活跃传输流中等待。离开 MULTI 会结束当前 clock epoch、取消未完成轮次并清除 `sessionLive`；TCP 连接可以继续保留，但退出交换房间后的 GP/Normal 阶段不能继续等待一条不会再出现的 START。再次进入 MULTI 时从新的零点建立时钟流。

《火红/叶绿》退房时会先在仍显示为 MULTI 的短暂窗口中清除 SIOCNT 串口 IRQ（Host 写 `2000`，Join 读回 `201C`），随后才真正切换模式。ahead limiter 因此要求 IRQ enable 保持为 1，并在每轮完成后放行一帧模拟时间；否则 Join 会在执行清 IRQ 的约一万周期退房代码前进入 1 ms socket hold，把退出过程拖慢数秒，严重时表现为黑屏且只有 Disconnect 才能恢复。

先用一份轨迹复现协议状态机，或同时传入 Host/Join 两份轨迹逐帧核对 TCP 线上数据：

```sh
python3 tools/netlink_trace_replay.py /path/to/netlink-host.jsonl
python3 tools/netlink_trace_replay.py /path/to/netlink-host.jsonl /path/to/netlink-join.jsonl
```

再用记录充当确定性 TCP 对端，只启动一个 mGBA 实例即可复现当时的收发顺序。回放 Host 记录时，让工具连接正在监听的 mGBA Host；回放 Join 记录时，让工具监听、再让 mGBA Join 连接它：

```sh
python3 tools/netlink_trace_peer.py host.jsonl --connect 127.0.0.1:8765
python3 tools/netlink_trace_peer.py join.jsonl --listen 127.0.0.1:8765
```

`--fragment N` 可以故意把每个 28 字节协议帧切成 N 字节 TCP 写入，用于稳定复现半包问题。回放会保留捕获的帧顺序和数据，同时动态替换新连接的 session nonce；第一处差异会直接报告帧类型和序号。

## 下一步门槛

进入 Switch 阶段前还需要在两台桌面电脑的同一局域网内重复上述连续两次交换验收，并验证断线、重连、窗口暂停和网络抖动。仅通过编译或 localhost 测试不构成双机/实体 Switch 验收。

核心设计见 [Network Link Architecture](docs/network-link-architecture.md)。桌面原型发布说明见 [desktop-poc-v1](docs/releases/desktop-poc-v1.md)。
