<div align="center">

<img src="https://img.shields.io/badge/License-MIT-yellow" alt="License">
<img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python">
<img src="https://img.shields.io/github/v/release/TutuBarry/abaqus-mcp-pro?color=green" alt="Release">
<img src="https://img.shields.io/badge/Abaqus-2024%2B-orange" alt="Abaqus">

<br>
<br>

<pre>
  ___  ______   ___   _____  _   _  _____  ___  ___ _____ ______  ______ ______  _____ 
 / _ \ | ___ \ / _ \ |  _  || | | |/  ___| |  \/  |/  __ \| ___ \ | ___ \| ___ \|  _  |
/ /_\ \| |_/ // /_\ \| | | || | | |\ `--.  | .  . || /  \/| |_/ / | |_/ /| |_/ /| | | |
|  _  || ___ \|  _  || | | || | | | `--. \ | |\/| || |    |  __/  |  __/ |    / | | | |
| | | || |_/ /| | | |\ \/ /| |_| |/\__/ / | |  | || \__/\| |     | |    | |\ \ \ \_/ /
\_| |_/\____/ \_| |_/ \_/\_\ \___/ \____/  \_|  |_/ \____/\_|     \_|    \_| \_| \___/ 
</pre>

**AI 原生 Abaqus 自动化 -- MCP 服务器 + 3D 查看器 + 求解器诊断**

[English](README.md) . [中文](README_ZH.md)

</div>

---

## 这是什么？

ABAQUS MCP Pro 通过 TCP Socket 桥接将 AI 助手直接连接到 Abaqus/CAE。
你用自然语言描述仿真任务，AI 实时执行 -- 建立几何、赋予材料、提交作业、诊断错误、可视化结果。

> *"创建一个悬臂梁，端部施加 10 kN 载荷，用 C3D8R 单元划分网格，提交作业。"*

AI 通过 MCP 工具完成每一步操作，模型在你的 Abaqus 窗口中实时更新。

<div align="center">
  <img src="docs/images/abaqus-mcp-comic.jpeg" alt="ABAQUS MCP Pro" width="800">
  <p><em>ABAQUS MCP Pro -- AI-Native Abaqus Automation Workflow</em></p>
</div>

---

## 快速开始

```bash
# 1. 安装
pip install -e .
abaqus-mcp-pro-setup

# 2. 启动 Abaqus/CAE，激活插件
#    Plug-ins > ABAQUS MCP Pro > Start MCP Bridge

# 3. 连接 AI 客户端
codex mcp add abaqus-mcp-pro -- python "path/to/server.py"

# 4. 开始与 Abaqus 对话
#    "创建一个拉伸试棒模型，使用钢材料属性..."
```

---

## 亮点

<table>
<tr>
<td width="33%" align="center">
<h3>闪电延迟</h3>
TCP Socket 桥接。无文件 I/O，无轮询。
</td>
<td width="33%" align="center">
<h3>26+ 个 MCP 工具</h3>
模型 . 作业 . ODB . KPI . 胶囊 . 合约 . 报告 . 视口 . 医生
</td>
<td width="33%" align="center">
<h3>GUI 实时可见</h3>
几何、网格、结果在当前 Abaqus 窗口中即时更新。
</td>
</tr>
<tr>
<td align="center">
<h3>3D 结果查看器</h3>
ODB 到 VTU 到 Three.js 浏览器可视化。Vite + FastAPI。
</td>
<td align="center">
<h3>求解器医生</h3>
40+ 错误模式自动诊断 + 收敛建议。
</td>
<td align="center">
<h3>本地运行</h3>
桥接监听 127.0.0.1:48152。数据不离开你的机器。
</td>
</tr>
</table>

---

## 架构

### 系统概览

```
+------------------+
|  AI 客户端       |  "创建一个钢制支架..."
|  (Codex/Claude)  |
+--------+---------+
         | stdio (MCP)
         v
+------------------+
|  MCP 服务器      |  server.py -- 26+ 工具, 13 提示词, 74 资源
|  (Python)        |
+--------+---------+
         | TCP :48152
         v
+------------------+
|  GUI 插件        |  agent.py -- 运行在 Abaqus/CAE 内核中
|  (Abaqus 内部)   |
+--------+---------+
         | Abaqus Python API
         v
+------------------+
|  Abaqus/CAE      |
|  Kernel          |
+------------------+
```

### 3D 查看器流水线

```
+----------+    export_to_vtk.py     +----------+    Three.js     +----------+
|  .odb    |  --------------------> |  .vtu    |  -------------> | 浏览器   |
|  (Abaqus)|  (节点平均 + 不变量     |  (VTK     |  (vtuparser.js  |  查看器   |
|          |   提取)                 |   ASCII)  |   + viewer3d)  |  本地    |
+----------+                        +----------+                 +----------+
       |                                  |
       |         +----------------+         |
       +-------->|  model.json    |<--------+
                 |  (元数据)       |
                 +----------------+
```

导出器（基于 Liujie-SYSU/odb2vtk）在 Abaqus Python 中运行，
提取节点平均场数据和应力不变量，并写入标准 VTK 非结构化网格 (.vtu) 文件。
浏览器查看器直接解析这些文件 -- 无需中间 JSON 转换，无需上传云端。

---

## 浏览器 3D 结果查看器

> **ODB 到 VTU 到 Three.js。一条命令。**

```bash
# 启动查看器服务器
python viewer/serve_viewer.py
# -> http://localhost:8080
```

输入 ODB 路径，点击 **Export from ODB**，立即查看结果：

- **旋转 / 平移 / 缩放** OrbitControls
- **场变量着色** -- S, U, PEEQ, RF, E, SDV，jet 色图 + 图例
- **变形切换** 可配置缩放因子
- **动画播放** 跨所有帧
- **线框叠加** 切换
- **探针拾取** -- 点击任意单元查看场值
- **PBR 渲染** RoomEnvironment 真实感光照
- **多帧支持** 通过每帧 .vtu 导出
- **导出缓存** -- 仅在 ODB 或参数变化时重新导出

<table>
<tr>
<td>

**从 Python（Abaqus 内部）：**
```python
from viewer.export.export_to_vtk import export_odb_to_vtk
export_odb_to_vtk("my_job.odb", output_dir="./vtk_out")
# 生成: model.json, frame_0000.vtu, frame_0001.vtu, ...
```

</td>
<td>

**从 MCP（通过 AI）：**
```
AI: "export_result_mesh for my_job.odb"
-> VTU 文件已导出
-> 在 http://localhost:8080 查看器中加载
```

</td>
</tr>
</table>

### 导出格式

| 文件 | 格式 | 描述 |
|------|------|------|
| model.json | JSON | 元数据：单元类型、场变量列表、帧索引、边界 |
| frame_NNNN.vtu | VTK XML ASCII | 非结构化网格：节点、单元、单元类型、节点场数据 |

.vtu 文件是标准 VTK XML 格式 -- 可在 **ParaView**、**PyVista**、**F3D** 或任何 VTK 兼容查看器中打开。
无专有格式锁定。

### 支持的单元类型

**3D 实体:** C3D4, C3D5, C3D6, C3D8/R/I, C3D10/M, C3D15, C3D20/R/H
**壳:** S3/R, S4/R, S6, S8/R, S9, STRI3, STRI65
**薄膜:** M3D3, M3D4/R, M3D6, M3D8/R, M3D9
**梁/桁架:** B21, B22, B31/H, B32/H, B33, T2D2/3, T3D2/H/3, R2D2, R3D3/4

### 导出的场变量

| 符号 | 描述 | 不变量 |
|------|------|--------|
| S | 应力张量 | Mises, Tresca, Press, Inv3, MaxPrincipal, MidPrincipal, MinPrincipal |
| U | 位移 | Magnitude, U1, U2, U3 |
| PEEQ | 等效塑性应变 | - |
| RF | 反力 | Magnitude, RF1, RF2, RF3 |
| E | 应变张量 | 6 个分量 |
| SDV | 解相关变量 | 每个单元的 SDV 值 |

---

## 工具参考

| 类别 | 工具 | 功能 |
|------|------|------|
| **桥接** | ping | 连接健康检查 + 会话状态 |
| | check_abaqus_connection | 可读状态报告 |
| **代码** | run_python | 在 Abaqus 内核中执行任意 Python |
| | execute_script | 兼容性包装（stdout 文本） |
| | set_workdir | 切换工作目录 |
| **模型** | get_model_info | 部件、材料、分析步、载荷、边界条件 |
| | check_model_integrity | 验证模型健康与一致性 |
| **作业** | list_jobs | 所有作业及其状态 |
| | submit_job | 提交并等待完成 |
| | monitor_job_status | 监控 .sta / .msg 诊断 |
| | diagnose_job | 求解器医生：40+ 错误模式 |
| **ODB** | inspect_odb | 帧、变量、截面 |
| | get_odb_info | 兼容性包装 |
| | extract_kpis | ODB Lens：KPI 提取 |
| | export_result_mesh | 导出 ODB 到 VTU 用于 3D 查看器 |
| **医生** | check_silent_failures | 检测静默模型问题（无错误但错误的结果） |
| | converge_advice | 收敛建议，带排序修复建议 |
| **胶囊** | create_capsule | 保存实验状态快照 |
| | list_capsules | 列出保存的胶囊 |
| | load_capsule | 加载保存的胶囊 |
| | delete_capsule | 删除保存的胶囊 |
| | compare_capsules | 对比两个胶囊 |
| **合约** | check_physics_contracts | 验证物理合约 |
| **报告** | generate_report | 生成仿真报告（Markdown） |
| **视口** | capture_viewport | 截图作为 base64 |
| | get_viewport_image | 兼容性包装 |

另外 **50+ 扩展工具** 用于特定的 Abaqus 操作：
create_part_*, create_*_material, create_*_section, create_*_step,
create_*_load (力、压力、重力、力矩、热流、壳边缘),
create_*_bc (位移、速度、加速度、温度、固支、销接、对称),
create_*_constraint (绑定、耦合、刚体、方程、MPC、嵌固区域),
create_contact, create_surface, create_set, generate_mesh, seed_part, set_element_type
create_instance, rotate_instance, translate_instance, create_reference_point
... 等等。

---

## 安装

### 前置条件

| 要求 | 版本 |
|------|------|
| Python | 3.10+ |
| Abaqus | 2024+ (Python 3.10) |
| AI 客户端 | Codex, Claude Desktop 等 |

### 安装

```bash
pip install -e .
abaqus-mcp-pro-setup          # 安装 GUI 插件到 Abaqus
```

### 查看器依赖

```bash
cd viewer
npm install                    # Three.js + Vite
cd ..
pip install fastapi uvicorn    # 查看器服务器（可选）
```

### 环境变量

| 变量 | 默认值 | 描述 |
|------|--------|------|
| ABAQUS_MCP_HOST | 127.0.0.1 | TCP 主机 |
| ABAQUS_MCP_PORT | 48152 | TCP 端口 |
| ABAQUS_MCP_TIMEOUT | 60 | Socket 超时（秒） |
| ABAQUS_MCP_MAX_MESSAGE_BYTES | 33554432 | 最大消息大小 |
| ABAQUS_MCP_PLUGIN_DIR | ~/abaqus_plugins | 插件安装目录 |
| ABAQUS_MCP_HOME | 自动检测 | 文件 IPC 工作目录 |

---

## 运行模式

```bash
# GUI 模式（主要）-- 启动 Abaqus/CAE，激活插件

# noGUI 模式 -- 批量执行
abaqus cae noGUI=scripts/start_abaqus_mcp_pro_agent.py

# 文件 IPC 备用模式
abaqus cae noGUI=scripts/start_abaqus_mcp_pro_ipc.py
```

---

## CLI 工具

```bash
abaqus-mcp-pro-check     # 检查桥接连通性
abaqus-mcp-pro-doctor    # 全面系统诊断
abaqus-mcp-pro-setup     # 安装/更新 GUI 插件
```

---

## Python API

```python
from abaqus_mcp_pro.client import AbaqusBridgeClient

client = AbaqusBridgeClient(timeout=60)
result = client.execute(
    "from abaqus import mdb; result = list(mdb.models.keys())"
)
print(result["return_value"])  # ["Model-1", ...]
```

---

## 项目结构

```
abaqus-mcp-pro/
+-- src/abaqus_mcp_pro/
|   +-- server.py                 # MCP stdio 服务器
|   +-- tools.py                  # 核心 + 扩展 MCP 工具
|   +-- resources.py              # MCP 资源
|   +-- prompts.py                # 13 个 MCP 提示词
|   +-- skills.py                 # 74 个技能资源
|   +-- transport.py              # Socket + 文件 IPC
|   +-- solver_diagnosis.py       # 求解器医生：40+ 模式
|   +-- convergence_advisor.py    # 收敛修复建议
|   +-- silent_failures.py        # 静默失败检测
|   +-- odb_lens.py               # ODB Lens：KPI 提取
|   +-- capsule.py                # 实验状态跟踪
|   +-- contracts.py              # 物理合约
|   +-- report.py                 # 报告生成
|   +-- abaqus_tools.py           # 核心 Abaqus 包装器
|   +-- abaqus_tools_extended.py  # 扩展操作包装器
|   +-- abaqus_docs.py            # Abaqus 文档搜索
|   +-- export_result_mesh.py     # ODB -> JSON（旧版）
|   +-- agent.py                  # Abaqus 端 TCP 代理
|   +-- gui_plugin.py             # Abaqus/CAE GUI 插件
|   +-- file_ipc_plugin.py        # 文件 IPC 备用
|   +-- client.py                 # TCP 客户端
|   +-- protocol.py               # JSON 协议
|   +-- cli.py                    # CLI 入口
|   +-- pywinauto_tools.py        # Windows GUI 自动化
+-- viewer/
|   +-- serve_viewer.py           # 一键查看器服务器
|   +-- viewer_server.py          # FastAPI 查看器服务器
|   +-- cache.py                  # 导出缓存管理器
|   +-- package.json              # Vite + Three.js
|   +-- vite.config.js            # Vite 构建配置
|   +-- index.html                # 查看器入口
|   +-- main.js                   # 旧版查看器 (V1)
|   +-- src/
|   |   +-- main.js               # V2 查看器入口 (Vite)
|   |   +-- viewer3d.js           # Three.js 场景
|   |   +-- vtuparser.js          # VTU 解析器
|   |   +-- vtkparser.js          # VTP 解析器
|   |   +-- loader.js             # 模型加载 UI
|   |   +-- ui.js                 # UI 控件
|   |   +-- odbexport.js          # ODB 导出触发
|   |   +-- measure.js            # 测量工具
|   |   +-- colormaps.js          # 色图
|   |   +-- style.css             # 查看器样式
|   +-- export/
|   |   +-- __init__.py
|   |   +-- export_to_vtk.py      # ODB -> VTU (Liujie-SYSU)
|   +-- dist/                     # Vite 构建输出
|   +-- samples/                  # 示例 VTU 文件
|   +-- *.result_mesh.json        # 旧版测试数据
+-- scripts/                      # noGUI 启动器
+-- examples/                     # 端到端脚本
+-- tests/                        # 测试套件
+-- docs/                         # MkDocs 文档
+-- dev/                          # 开发工具
+-- skills/                       # AI 技能知识库
+-- MechAgent/                    # MechAgent 集成
+-- pyproject.toml
+-- CHANGELOG.md
+-- CONTRIBUTING.md
+-- README.md
```

---

## 故障排除

| 症状 | 修复 |
|------|------|
| WinError 10061 连接拒绝 | 启动桥接：Plug-ins > ABAQUS MCP Pro > Start MCP Bridge |
| 连接超时 | 先启动插件，再启动 MCP 服务器 |
| Module abaqusGui can only be used... | 使用 Plug-ins 菜单，而不是 File > Run Script |
| 模型在 GUI 中看不到 | abaqus-mcp-pro-check -> 确认 MainThread |
| Codex 看不到工具 | codex mcp list -> 重启 Codex |
| abaqus-mcp-pro-server 找不到 | 重新安装或运行 abaqus-mcp-pro-doctor |
| 查看器显示空白页 | cd viewer && npm install && npx vite build 然后重启 |

---

## 致谢

- [Abaqus-Control-MCP](https://github.com/Whfkl/Abaqus-Control-MCP) -- TCP Socket 桥接，AST 诊断
- [CAE-Agent-Hub](https://github.com/Cai-aa/CAE-Agent-Hub) -- 高级工具与架构
- [abaqus-mcp](https://github.com/Cai-aa/abaqus-mcp) -- 基于文件的 IPC 传输
- [Codex_MCP_Abaqus](https://github.com/Zhangyoupeng1996/Codex_MCP_Abaqus) -- noGUI 模式与示例
- [Liujie-SYSU/odb2vtk](https://github.com/Liujie-SYSU/odb2vtk) -- 单元节点平均、不变量提取、VTK 导出
- [MechAgent](https://github.com/ZPL-03/MechAgent) -- 多智能体 CAE 协作框架

---

<div align="center">

**MIT 许可证** . [查看许可证](LICENSE)

Made with for the CAE community

</div>