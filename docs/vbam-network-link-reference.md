# VBA-M 网络 Link Cable：设计参考

本文只总结可借鉴的设计，不复制 VBA-M 代码，也不改变 mGBA 0.10.5 的实现。目标仍是：两台 Switch、同一 Wi-Fi、两人 GBA 有线 Link Cable。

## 结论

VBA-M 是当前最值得参考的开源实现：它已有 `LINK_CABLE_SOCKET`，用 Host/Client TCP 交换真实 GBA Link Cable 传输数据。mGBA 0.10.5 只有同一进程内的 `GBASIOLockstep`；它的 SIO 寄存器与完成 IRQ 语义应保留，但其共享内存同步不能跨设备直接使用。

不要把 VBA-M 的 C++/SFML 代码直接移植或复制到本项目。两者核心架构不同，且 VBA-M 使用 GPL 许可证；这里仅借鉴协议边界、状态机和异常处理思路。

## 两种模型

```text
mGBA 0.10.5（当前本地基线）
核心 0 ─┐
        ├─ 同一进程共享 GBASIOLockstep ─ wait/signal ─ 完成 SIO IRQ
核心 1 ─┘

VBA-M Socket Link（参考模型）
Host 模拟器 ─ TCP ─ Join 模拟器
  收集本机/远端 Link 数据 → 决定本轮结果 → 回传 → 各自完成 SIO IRQ
```

## 最值得借鉴的四项设计

### 1. 网络层是 Link Driver，不是前端功能

VBA-M 将 `LINK_CABLE_SOCKET` 放在 GBA Link 驱动分派中，并由传输开始/更新函数驱动网络收发。这说明 Host/Join UI 只负责创建连接；SIO 的发起、数据交换、完成和 IRQ 仍必须留在模拟器核心路径。

对 mGBA 的映射：新增两人专用的 `GBASIODriver`/transport，而不是在 Qt 或 GBAStation 页面里直接读写 TCP。

### 2. Host 是唯一传输协调者

一次 GBA MULTI 传输中，Host（player 0）发起；Join 回传自己的 `SIOMLT_SEND` 数据；Host 汇总本轮数据并广播最终结果。这样能避免两端同时决定结果。

对 mGBA 的映射：

```text
Host: TRANSFER_STARTING → 发送 START
Join: 收到 START → 发送 DATA
Host: 收齐 DATA → 发送 FINISH
两端: 写 SIOMULTI0..3 → 清 Busy → GBA_IRQ_SIO
```

首版只支持 player 0 Host、player 1 Join；不加入迁移 Host、四人、RFU 或公网匹配。

### 3. 报文必须有确定边界，收发必须有期限

VBA-M 的 Socket Link 使用小型长度明确的数据帧，并在接收前轮询 socket；连接建立可非阻塞，已建立的帧交换有受限等待。它还处理半包、超时、错误和对端断开，避免让模拟线程无限卡在 `recv()`。

对 mGBA 的首版协议要求：

|帧|最小字段|作用|
|---|---|---|
|`HELLO`|协议版本、会话 ID、角色|拒绝不兼容连接。|
|`START`|序号、模式、Host 模拟周期、SIOCNT|标记一轮 Link Cable 开始。|
|`DATA`|序号、Join 的发送字|响应本轮传输。|
|`FINISH`|序号、四个接收字、完成周期|两端以同一结果结束本轮。|
|`CLOSE`|原因码|退出或异常后停止传输。|

每一帧都要检查长度、版本、序号和会话 ID；TCP 虽然有序可靠，但不能替代帧边界和超时。

### 4. 断线必须延后到安全点清理

VBA-M 的经验是：Socket 收发函数发现断线时，不应立即销毁当前 Link Driver；先记录“需要关闭”，再在下一次模拟步骤的安全点统一关闭。否则正在执行的传输代码可能继续访问已经释放的 socket 或 driver。

对 mGBA 的映射：transport 仅设置 `closing/error` 状态；在下一次 SIO/帧调度安全点中断未完成传输、取消定时事件、恢复未连接的 SIOCNT 状态，并通知 UI。

## mGBA 0.10.5 的具体接入边界

保留以下现有硬件语义：

- `GBASIOWriteSIOCNT`：识别游戏何时发起传输。
- `GBASIOLockstepNodeMultiWriteRegister`：当前本机 MULTI 发起点，可作为事件对照基线。
- `_finishTransfer`：写回 `SIOMULTI0..3`、清 `Busy`、设置 player ID 的位置。
- `GBARaiseIRQ(..., GBA_IRQ_SIO, ...)`：游戏感知到传输完成的最终信号。

不要网络化的内容：`GBASIOLockstep` 的进程内指针、共享数组、`wait/signal` 和 Qt 多窗口对象。它们仅服务同一进程的多个核心。

## 阶段 2 的最小验收顺序

1. 两个桌面进程通过 localhost 建立 Host/Join。
2. 日志验证 `START → DATA → FINISH → SIO_IRQ` 的序号在两端一致。
3. 两份用户合法备份的 FireRed/LeafGreen 完成一次交换。
4. 断开 Join 后 Host 不崩溃、不继续等待旧传输。
5. 再把同一 transport 抽象移到 Switch；Switch 不改变协议，只替换 socket 适配和 Host/Join UI。

## 当前桌面原型（实现记录）

实现位于 mGBA 0.10.5 的 `include/mgba/internal/gba/sio/netlink.h` 与 `src/gba/sio/netlink.c`：

- `GBASIONetlink` 是独立的两人 `SIO_MULTI` driver；不会触碰本地多窗口 `GBASIOLockstep`，也不注册 `SIO_NORMAL_32`。在《火红/叶绿》中，后者会参与 Wireless Adapter 探测；把有线 TCP driver 绑上去会让游戏错误地认为无线适配器存在。
- TCP 使用固定 28 字节、协议版本 3 的 `MGNL` 帧，并按 `HELLO`、`START`、`DATA`、`FINISH`、`CLOSE` 处理。协议版本、会话 ID、角色及传输序号会在核心层检查。
- Host 监听后由 Join 的 `HELLO` 建立会话。借鉴 VBA-M，`START` 发送的是 Host 自上轮结束后的 `linkTime` 间隔；Join 先将自己的间隔追到这个值才读取本机 `SIOMLT_SEND` 并发送 `DATA`。双方再以 `GBASIOCyclesPerTransfer` 的两人传输长度完成本轮；Join 本地完成，Host 收齐 `DATA` 后完成并发送 `FINISH` 通知。
- socket 已连接后的收发为非阻塞，核心每 512 个模拟周期轮询；不在每次轮询中睡眠，避免高频通信菜单降到数 fps。收发错误只置 `closing`，下一次 SIO 调度关闭 socket，避免在正在处理的传输中释放 driver。

Qt 入口在菜单 **File → Network Link Cable...**：Host 默认端口 `8765`，Join 输入 `host:port`（本机测试为 `127.0.0.1:8765`）。Qt 会默认给单窗口挂本地 lockstep；启动 Network Link 时会自动解除该单窗口 driver 并替换为 TCP driver。若已经实际打开并连接第二个本地多人窗口，则拒绝切换。两个进程各自载入 ROM 后，先启动 Host，再启动 Join；断开使用 **File → Disconnect Network Link** 或退出 Join。

本实现已完成编译验证；实际交换仍需要人工运行两个 Qt 进程，确认两边的 `GBA Serial I/O` 日志具有同一序号的：

```text
NETLINK START role=host seq=N ...
NETLINK START role=join seq=N ...
NETLINK DATA role=join seq=N ...
NETLINK DATA role=host seq=N ...
NETLINK FINISH role=host|join seq=N
NETLINK SIO_IRQ role=host|join seq=N
```

## 参考资料

- [VBA-M 主仓库](https://github.com/visualboyadvance-m/visualboyadvance-m)：`ENABLE_LINK` 构建选项与持续维护状态。
- [VBA-M gbaLink.cpp](https://github.com/visualboyadvance-m/visualboyadvance-m/blob/master/src/core/gba/gbaLink.cpp)：`LINK_CABLE_SOCKET`、`CableServer`、`CableClient`、传输更新和断线处理的主参考。
- [mGBA 仓库](https://github.com/mgba-emu/mgba)：当前仍将 networked multiplayer Link Cable 列为计划功能；不要假设其本地 Link 可以跨网络。
- [GBA Link Cable Networking](https://www.mattgreer.dev/blog/gba-dev-link-cable-networking/)：用于核对 GBA 硬件 Link Cable 的基本通信模型，不是模拟器联网代码。
