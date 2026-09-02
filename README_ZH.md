 # ABAQUS MCP Pro

 [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
 [![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/downloads/)

 [English](README.md) | 中文

 > **让 AI 直接驱动 Abaqus。** 描述你想要的模型 —— 几何、材料、载荷、分析步 —— AI 就能在你正在运行的 Abaqus/CAE 会话中执行对应操作。

 **ABAQUS MCP Pro** 通过 TCP socket 桥接，将 Codex、Claude 等 MCP 兼容客户端连接到正在运行的 Abaqus/CAE 实例。你描述任务，AI 将其转化为 Abaqus 操作，模型实时更新。

 本项目整合了社区多个优秀开源项目的精华，核心架构基于 [Abaqus-Control-MCP](https://github.com/Whfkl/Abaqus-Control-MCP)。

 ## 为什么选择它？

 - **直接在 GUI 中工作** — 操作发生在当前 Abaqus 窗口中，几何、网格和结果即时可见。
 - **流畅建模体验** — 通过 TCP socket 桥接直接与 Abaqus 内核交互，延迟 10-50ms。
 - **完整 API 访问** — `mdb`、`session`、`odb` 以及其它 Python API 均可直接使用。
 - **保持会话可交互** — 工程师可以随时查看建模进度，无需中断会话。
 - **仅本地运行** — 桥接只监听 `127.0.0.1:48152`，数据不会离开你的机器。
 - **智能错误诊断** — 基于 AST 自动分析 KeyError、AttributeError、NameError、TypeError 并给出修复建议。

 ## 架构

 ```
 MCP 客户端 (Codex/Claude)
     |
     v  stdio
 MCP 服务器 (server.py)
     |
     v  TCP socket (localhost:48152)
 Abaqus GUI 插件 (gui_plugin.py)
     |
     v  Abaqus Python API
 Abaqus/CAE 内核
 ```

 MCP 服务器作为 AI 客户端的子进程运行。当客户端调用工具（如 `run_python`）时，服务器通过 TCP socket 将请求转发到运行在 Abaqus/CAE 内的轻量级代理，代理在 Abaqus Python 内核中执行代码并返回结果。

 ## 安装

 ### 环境要求

 - Python 3.10+
 - Abaqus 2024+（内置 Python 3.10）
 - MCP 兼容的 AI 客户端（Codex、Claude Desktop 等）

 ### 安装包

 ```bash
 pip install -e .
 ```

 ### 安装 Abaqus GUI 插件

 ```bash
 abaqus-mcp-pro-setup
 ```

 或手动将 `src/abaqus_mcp_pro/gui_plugin.py` 复制到 Abaqus 插件目录（通常为 `~/abaqus_plugins/`）。

 > 可通过设置环境变量 `ABAQUS_MCP_PLUGIN_DIR` 自定义插件安装目录。

 ## 使用方法

 ### 1. 启动 Abaqus/CAE

 正常启动 Abaqus/CAE，然后激活插件：

 **Plug-ins > ABAQUS MCP Pro > Start MCP Bridge**

 启动后，Abaqus 消息区会显示：

 ```
     o---o
    /   /|   < Abaqus MCP Bridge Active!
   o---o o   Listening on 127.0.0.1:48152
   |___|/    <<--  May your meshes converge and your residuals drop.  -->>
 ```

 ### 2. 配置 MCP 客户端

 #### Codex

 使用命令行添加：

 ```bash
 codex mcp add abaqus-mcp-pro -- python路径 "server.py的绝对路径"
 ```

 例如：

 ```bash
 codex mcp add abaqus-mcp-pro -- D:/ProgramData/anaconda3/python.exe "R:/100_Private/WQG/codex/ABAQUS MCP/abaqus-mcp-pro/src/abaqus_mcp_pro/server.py"
 ```

 #### Claude Code

 在 `~/.claude.json` 的 `mcpServers` 节点下添加：

 ```json
 "abaqus-mcp-pro": {
   "command": "abaqus-mcp-pro-server",
   "env": {
     "ABAQUS_MCP_HOST": "127.0.0.1",
     "ABAQUS_MCP_PORT": "48152",
     "ABAQUS_MCP_TIMEOUT": "120"
   }
 }
 ```

 ### 3. 使用工具

 连接成功后，AI 客户端即可使用全部 22 个工具：

 | 工具 | 说明 |
 |------|------|
 | `ping` | 检查桥接连接 + 会话状态（模型、视口、PID） |
 | `check_abaqus_connection` | 人类可读的连接状态 |
 | `run_python` | 在 Abaqus 内核中执行任意 Python 代码 |
 | `execute_script` | 兼容包装器，返回 stdout 文本 |
 | `set_workdir` | 修改 Abaqus 工作目录 |
 | `get_model_info` | 列出部件、材料、分析步、载荷、边界条件 |
 | `list_jobs` | 列出所有作业及其状态 |
 | `submit_job` | 提交作业并等待完成 |
 | `monitor_job_status` | 读取 .sta/.msg 文件获取进度与诊断 |
 | `inspect_odb` | 只读打开 ODB：帧裁剪、变量含分量信息 |
 | `get_odb_info` | inspect_odb 的兼容包装器 |
 | `capture_viewport` | 截取视口图像为 base64（PNG/TIFF/SVG） |
 | `get_viewport_image` | 兼容包装器，返回 data URI |

 ### noGUI 模式

 在批处理模式下运行 Abaqus，使用 TCP 代理：

 ```bash
 abaqus cae noGUI=scripts/start_abaqus_mcp_pro_agent.py
 ```

 或使用文件 IPC 备用通道：

 ```bash
 abaqus cae noGUI=scripts/start_abaqus_mcp_pro_ipc.py
 ```

 ### CLI 诊断

 ```bash
 # 检查与运行中 Abaqus 桥接的连通性
 abaqus-mcp-pro-check

 # 完整诊断
 abaqus-mcp-pro-doctor

 # 安装/更新 GUI 插件
 abaqus-mcp-pro-setup
 ```

 ## 环境变量

 | 变量 | 默认值 | 说明 |
 |------|--------|------|
 | `ABAQUS_MCP_HOST` | `127.0.0.1` | TCP 桥接主机地址 |
 | `ABAQUS_MCP_PORT` | `48152` | TCP 桥接端口 |
 | `ABAQUS_MCP_TIMEOUT` | `60` | 执行超时（秒） |
 | `ABAQUS_MCP_MAX_MESSAGE_BYTES` | `33554432` | 最大消息大小 |
 | `ABAQUS_MCP_PLUGIN_DIR` | `~/abaqus_plugins` | GUI 插件安装目录 |
 | `ABAQUS_MCP_HOME` | 自动检测 | 文件 IPC 的工作目录 |

 ## Python API

 ```python
 from abaqus_mcp_pro.client import AbaqusBridgeClient

 client = AbaqusBridgeClient(timeout=60)
 result = client.execute("from abaqus import mdb; result = list(mdb.models.keys())")
 print(result['return_value'])  # ['Model-1', ...]
 ```

 ## 示例

 参见 `examples/` 目录中的 Abaqus Python 脚本：

 - `abaqus_cantilever_classic.py` — 悬臂梁静力分析
 - `abaqus_tensile_bar_classic.py` — 拉伸试棒（含颈缩）
 - `show_tensile_result_viewport.py` — 后处理可视化

 ## 项目结构

 ```
 abaqus-mcp-pro/
 +-- pyproject.toml           # 包元数据
 +-- README.md                # 英文说明
 +-- README_ZH.md             # 中文说明（本文件）
 +-- src/abaqus_mcp_pro/
 |   +-- __init__.py          # 包初始化
 |   +-- server.py            # MCP stdio 服务器（22 工具 + 13 提示 + 74 资源）
 |   +-- agent.py             # Abaqus 端 TCP socket 代理（纯标准库）
 |   +-- gui_plugin.py        # Abaqus/CAE GUI 插件（AFX 菜单）
 |   +-- file_ipc_plugin.py   # 基于文件的 IPC 备用插件
 |   +-- client.py            # CLI 工具的 TCP 客户端
 |   +-- protocol.py          # 共享的行分隔 JSON 协议
 |   +-- cli.py               # CLI：check、doctor、setup
 +-- scripts/
 |   +-- start_abaqus_mcp_pro_agent.py   # noGUI 启动器（TCP）
 |   +-- start_abaqus_mcp_pro_ipc.py     # noGUI 启动器（文件 IPC）
 |   +-- stop_mcp_agent.py           # 文件 IPC 停止信号
 +-- examples/
 |   +-- abaqus_cantilever_classic.py
 |   +-- abaqus_tensile_bar_classic.py
 |   +-- show_tensile_result_viewport.py
 +-- tests/                    # 测试目录
 ```

 ## 故障排查

 | 问题 | 解决方案 |
 |-------|----------|
 | `WinError 10061` 连接被拒绝 | 未在 Abaqus/CAE 中开启桥接服务。请先启动 Abaqus/CAE，并在顶部菜单栏选择 **Plug-ins -> ABAQUS MCP -> Start MCP Bridge**。 |
 | 连接超时 | 先在 Abaqus 内启动插件，再启动 MCP 服务。 |
 | `Module abaqusGui can only be used...` | 通过 **Plug-ins** 菜单启动，不要用 File -> Run Script。 |
 | 模型未出现在 GUI 中 | 运行 `abaqus-mcp-pro-check`，确认 `"thread": "MainThread"`。 |
 | Codex 看不到 MCP 工具 | 运行 `codex mcp list` 检查是否已注册。如未列出，重启 Codex。 |
 | 找不到 `abaqus-mcp-pro-server` | 重新安装或运行 `abaqus-mcp-pro-doctor`。 |

 ## 致谢

 本项目整合了以下开源项目的优秀设计：

 - [Abaqus-Control-MCP](https://github.com/Whfkl/Abaqus-Control-MCP) — TCP socket 桥接、AST 错误诊断
 - [CAE-Agent-Hub](https://github.com/Cai-aa/CAE-Agent-Hub) — 高层工具与架构设计
 - [abaqus-mcp](https://github.com/Cai-aa/abaqus-mcp) — 文件 IPC 传输
 - [Codex_MCP_Abaqus](https://github.com/Zhangyoupeng1996/Codex_MCP_Abaqus) — noGUI 模式与示例

 ## 许可证

 MIT — 详见 [LICENSE](LICENSE)。
