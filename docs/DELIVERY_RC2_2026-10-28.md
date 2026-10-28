# ABAQUS MCP Pro 1.1.0rc2 验收报告

- 日期：2026-10-28
- 时区：Asia/Shanghai
- 源码基线：`master` / `7cfecb8`
- 验收范围：当前工作树，包含未提交改动

## 结论

当前工作树在本机可执行范围内通过 MCP stdio、真实 GUI 故障恢复、隔离安装、Python 与前端回归、发行物校验、接触收敛、124,138 节点接触和百万节点浏览器 GPU 验收。

这不是公开发布验收。其他 Abaqus 版本因本机环境阻塞，远程 CI 尚未运行。本次只提交源码，不创建带标签或打包的正式公开发布。

远程桥接不纳入本轮验收。桥接保持本机回环连接。noGUI 仅在用户明确要求时启用。

运行中的受保护 GUI 会话在整个验收期间得到保留：

- `ABQcaeG.exe` PID `28484`
- `ABQcaeK.exe` PID `38416`
- `SMAPython.exe` PID `41288`
- 本机桥接 `127.0.0.1:48152`，监听 PID `28484`

## 验收矩阵

| 项目 | 结果 | 关键证据 |
|---|---|---|
| 当前构建 MCP stdio 端到端链路 | 通过 | `.acceptance/final-gates/stdio-connect-e2e.json` |
| 桥接断开、端口冲突、启动崩溃 | 通过 | `.acceptance/faults/report.json` |
| 真实 GUI CAE 强杀与同会话恢复 | 通过 | `.acceptance/gui-crash/report.json` |
| 完全隔离依赖安装与 wheel 冒烟 | 通过 | `.acceptance/final-gates/venv-isolated` |
| Python 全量测试 | 通过，410 项 | `.acceptance/final-gates/pytest.log` |
| 前端测试与生产构建 | 通过，57 项 | `.acceptance/final-gates/viewer-test.log` |
| 当前 wheel/sdist 重建与 Twine 校验 | 通过 | `.acceptance/final-gates/dist` |
| 接触收敛阈值 | 通过 | `.acceptance/contact-convergence/report.json` |
| 124,138 节点接触求解与导出 | 通过 | `.acceptance/large-contact/report.json` |
| 百万节点真实线单元求解 | 通过，范围为 T3D2 | `.acceptance/million-rod/report.json` |
| 百万节点浏览器 GPU | 通过，范围为线渲染 | `.acceptance/million-gpu/report.json` |
| 其他 Abaqus 版本 | 环境阻塞 | `.acceptance/environment/abaqus_versions.json` |
| 远程 CI | 未执行 | 本轮无远程执行 |
| 带标签/打包的正式公开发布 | 未执行 | 本次只提交源码 |

## MCP stdio 与连接

当前构建使用 10 个独立 MCP stdio 进程复验。10/10 运行通过，20 次 `connect_abaqus` 均返回 `bridge_ready`，10 次真实 GUI `ping` 均成功，Abaqus 版本为 2026。

这是 stdio 链路的独立复验，不以既有 GUI 桥接结果替代。单次运行耗时 2.430 至 3.904 秒。

连接策略保持如下边界：

- Abaqus/CAE 未打开时，MCP 启动 GUI CAE，并自动启动本机桥接。
- Abaqus/CAE 已打开但桥接未启动时，用户可从 `Plug-ins -> ABAQUS MCP Pro -> Start MCP Bridge` 手动启动。
- noGUI 只在用户明确选择时使用，适用于仅需完整 INP 和 noGUI 计算的场景。

## 故障恢复

受控故障覆盖桥接端口消失、请求中断、占用端口无响应、启动器提前退出，以及同一 MCP stdio 会话内重新连接。端口冲突不会重复启动 CAE，受保护的 GUI 进程未被终止。

真实 GUI 强杀使用独立端口 `48153` 和可牺牲的独立 GUI 进程组。强制终止该组后，连接端口关闭，原 MCP stdio 会话重新启动 GUI CAE 并完成 `ping`。恢复后 Abaqus 版本仍为 2026，受保护的 `48152` 会话及其 PID 未受影响。

首次强杀尝试保留了 `.acceptance/gui-crash/report.attempt-1.json`；最终通过结果位于 `.acceptance/gui-crash/report.json`。

## 隔离安装与回归

隔离环境位于 `.acceptance/final-gates/venv-isolated`，其 `pyvenv.cfg` 明确设置 `include-system-site-packages = false`。完整依赖和 `abaqus_mcp_pro-1.1.0rc2` 从最终 wheel 安装成功。

包从该环境的 `Lib/site-packages/abaqus_mcp_pro/__init__.py` 加载，版本为 `1.1.0rc2`。隔离环境冒烟结果包括：

- stdio roundtrip 通过
- 139 个工具
- 13 个提示词
- 74 个资源
- 内置查看器资源可用
- 已安装查看器 HTTP 服务可用
- GUI 插件运行时可用

Python 测试为 `410 passed, 0 failed`，耗时 5.18 秒。前端测试为 `57 passed, 0 failed`，耗时 469.941 毫秒。Vite 生产构建通过。

`python -m pyflakes src` 通过。全仓库 Pyflakes 仍会报告既有测试和平台脚本中的未使用导入等问题；Ruff 对 `src` 仍有历史样式和导入规则告警。这些告警没有计作 Ruff 全绿或全仓库静态检查通过。

## 发行物

最终发行物位于 `.acceptance/final-gates/dist`：

| 文件 | SHA256 |
|---|---|
| `abaqus_mcp_pro-1.1.0rc2-py3-none-any.whl` | `6557f965f39331a665f536743522b8c0f46b56784ac6c78312815e0828106e53` |
| `abaqus_mcp_pro-1.1.0rc2.tar.gz` | `9d0ae5403a59e5e8fe8653f41cf7a6083583a540decbfe2c3c383b01dee9ddd` |

Twine 对 wheel 和 sdist 的检查均为 `PASSED`。

## 接触收敛

曲面接触族新增 3、3.5、4 级网格复验。投影接触面积从 22.3333 降至 20.9796，再降至 20.0625 mm²；最后两级相对变化为 4.571%，低于 5% 阈值。总反力、峰值 CPRESS 和峰值 Mises 的最后两级相对变化分别为 0.0589%、1.8668% 和 0.1941%，也均低于 5%。

早期 `2` 至 `3` 级报告中，平面接触族的力、面积、峰值 CPRESS 和峰值 Mises 同样均低于 5%；摩擦和塑性扩展检查也通过。该证据保留在 `.acceptance/contact-convergence/report.levels-2-to-3.json`。

接触面积仍是无变形表面节点分摊面积的估计值，不是精确接触边界。材料为演示性材料，未做工程标定。

## 124,138 节点接触

真实三维接触模型包含 124,138 节点、114,688 个单元和 15 帧，以 8 CPU 求解完成，耗时 819.111 秒。

验证通过连续时间完成、力平衡、人工应变能比例、接触压力存在且非负、COPEN、有限穿透和接触指标有限性检查。总反力为 411.7278 N，力平衡相对差为 `3.1235e-7`，人工应变能比为 `1.0286e-4`，压力积分力相对差为 0.3084%。

ODB 导出状态为 `completed`，包含 `CPRESS` 和 `COPEN`，导出耗时 222.847 秒。

## 百万节点规模

真实 T3D2 连接杆包含 1,000,001 节点和 1,000,000 单元，求解耗时 115.868 秒。端位移为 0.0476180613 mm，反力为 -999.975952 N，数值检查通过。U 场导出为 `completed`，耗时 241.385 秒。

该结果证明百万节点线单元的求解和导出路径，不代表百万节点实体接触、全应力场或实体网格性能。

浏览器 GPU 复验加载同一百万节点线模型。Intel Iris Xe D3D11、WebGL 2 环境下，总加载时间为 8.740 秒，强制渲染为 56.212 FPS，首交互帧为 180.338 毫秒。场景包含 1,000,001 个线顶点和 1,000,000 条线，console error 和 page error 均为 0。

该 GPU 结果验证百万节点线渲染，不替代百万节点实体接触或跨硬件 GPU 验收。

## 环境边界与未完成

本机只检测到 Abaqus 2026，未安装其他 Abaqus 版本，因此跨版本真实求解状态为 `environment_blocked`，不能表述为通过。

远程 CI 尚未运行。工作区内 CI 配置不能替代远程流水线结果。

带标签、打包和公开分发的正式发布未执行。本报告描述的是提交到源码仓库前的工作树验收状态。

机器可读状态见 [VALIDATION_RC2_2026-10-28.json](VALIDATION_RC2_2026-10-28.json)。2026-09-30 文档保留为历史快照，不应再作为当前状态使用。
