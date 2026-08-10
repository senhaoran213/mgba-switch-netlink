# 阶段 1：mGBA 本地 Link Cable 代码地图与观测

## 已验证的上游事实

GBAStation 最新 `main`（`4d346b0492ed51009999e91adda52d5f6e9b17df`）内置 mGBA 0.10.5；对应官方标签提交为 `26b7884bc25a5933960f3cdcd98bac1ae14d42e2`。其 README 同时声明支持“同一台电脑上的本地 Link Cable”，并把“网络化多人 Link Cable”列为计划功能。故当前没有可直接复用的 mGBA TCP 联机实现。

Qt 前端使用一个 `QGBA::MultiplayerController` 管理多个 `CoreController`；GBA 分支创建一个 `GBASIOLockstep`，每个核心附加一个 `GBASIOLockstepNode`。这意味着阶段 1 的基线是同进程的双核心/双窗口，而非 OS 级双进程。

## 数据与控制路径

```text
GBA 游戏写 SIOMLT_SEND / SIOCNT
  -> src/gba/io.c: GBAIOWrite
  -> src/gba/sio.c: GBASIOWriteRegister / GBASIOWriteSIOCNT
  -> GBASIOLockstepNodeMultiWriteRegister
  -> src/gba/sio/lockstep.c: _masterUpdate / _slaveUpdate
  -> GBASIOLockstep: wait / signal / shared transfer state
  -> _finishTransfer
  -> GBARaiseIRQ(..., GBA_IRQ_SIO, ...)
```

|职责|入口|
|---|---|
|Qt 本地多人装配|`src/platform/qt/MultiplayerController.cpp`|
|将外设驱动接到 GBA 核心|`src/gba/core.c` 的 `mPERIPH_GBA_LINK_PORT`|
|SIO 寄存器与完成 IRQ|`src/gba/sio.c`|
|跨核心本地协调、事件投递、ACK|`src/gba/sio/lockstep.c`|
|SIO 寄存器 IO 分派|`src/gba/io.c`|

## 新增观测点

仅在 `GBA_SIO` 的 DEBUG 级别增加以下稳定前缀，未改变时序、数据或传输决策：

|日志|含义|
|---|---|
|`NETLINK SIO_START`|时钟主机发起 SIO 传输；记录 player、mode、连接数与 SIOCNT。|
|`NETLINK LOCAL_REMOTE_RESPONSE`|次节点进入 `TRANSFER_STARTED` 并写入自己的发送数据。|
|`NETLINK SIO_COMPLETE`|数据写回 `SIOMULTI0..3`，并记录 IRQ 请求位。|
|`NETLINK SIO_IRQ`|实际调用 `GBARaiseIRQ(GBA_IRQ_SIO)` 前。|

预期同一轮两人 MULTI 传输最小证据：

```text
NETLINK SIO_START player=0 mode=MULTI connected=1 ...
NETLINK LOCAL_REMOTE_RESPONSE player=1 data=....
NETLINK SIO_COMPLETE player=0 mode=MULTI ... irq=1
NETLINK SIO_IRQ player=0
```

## 网络接入结论（阶段 2）

网络层应实现一个新的 `GBASIODriver`，保留 `GBASIOWriteSIOCNT`、`_finishTransfer` 和 `GBARaiseIRQ` 的硬件语义。它应把 lockstep 状态迁移边界序列化为有序 TCP 帧：`ATTACH`、`TRANSFER_START`、`TRANSFER_DATA`、`TRANSFER_FINISH`、`DETACH`，并携带协议版本、会话 ID、player ID、仿真周期时间戳、模式和 MULTI/Normal 数据。不要把 TCP 放进 Qt 窗口层，也不要在 `io.c` 直接发送网络包。

风险：TCP 的可靠有序性足够匹配事件队列，但不解决仿真时钟同步；阶段 2 必须明确 host 为时钟主机、限制两人、对超时/断线中止传输，并先证明单机 localhost 的双进程同步。Switch 端已有 `mgba-util/socket.h` 的 `__SWITCH__` 初始化与标准 TCP socket 包装，属于阶段 3 的传输适配基础，不是网络 Link Cable 实现。

## 运行与验收

1. 构建 Qt 桌面前端，并在其日志设置中开启 `GBA Serial I/O` 的 DEBUG。
2. 通过同一个 Qt 应用的本地 Multiplayer 流程装载两份用户合法备份的 FireRed/LeafGreen；不要启动两个独立 mGBA 进程并期待它们自动相连。
3. 进入游戏通信房间，完成一次交换；保存两侧窗口和上述六类日志。
4. 通过条件：房间稳定、一次交换完成、日志中有发起/次节点响应/完成/IRQ。没有合法 ROM 或人工 UI 操作时，本项目只能提供编译与静态代码证据，不能宣称该验收已经完成。
