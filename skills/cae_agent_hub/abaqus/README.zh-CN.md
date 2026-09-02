# Abaqus 有限元 Skills

本仓库导入的有限元仿真 skills 已统一整理到这个目录。Abaqus 专用 skills 按工作流阶段分类；通用 FEA 和 FEniCS skills 放在 `reference/` 下，因为它们可辅助 Abaqus 工作流，但不是 Abaqus 专用。

## 分类

| 分类 | Skills |
| --- | --- |
| `core` | `abaqus` |
| `modeling` | `abaqus-geometry`, `abaqus-material`, `abaqus-mesh`, `abaqus-interaction` |
| `setup` | `abaqus-amplitude`, `abaqus-bc`, `abaqus-docs`, `abaqus-field`, `abaqus-load`, `abaqus-output`, `abaqus-step` |
| `analysis` | `abaqus-contact-analysis`, `abaqus-coupled-analysis`, `abaqus-dynamic-analysis`, `abaqus-fatigue-analysis`, `abaqus-modal-analysis`, `abaqus-static-analysis`, `abaqus-thermal-analysis` |
| `execution` | `abaqus-job`, `abaqus-export` |
| `postprocessing` | `abaqus-odb` |
| `optimization` | `abaqus-optimization`, `abaqus-shape-optimization`, `abaqus-topology-optimization` |
| `reference` | `fea-structural`, `fenics-fem` |

## 推荐 Abaqus 组合

普通静力分析建议使用：

```text
core/abaqus
modeling/abaqus-geometry
modeling/abaqus-material
modeling/abaqus-mesh
setup/abaqus-load
setup/abaqus-bc
setup/abaqus-step
analysis/abaqus-static-analysis
execution/abaqus-job
postprocessing/abaqus-odb
```

接触分析增加 `modeling/abaqus-interaction` 和 `analysis/abaqus-contact-analysis`。

热分析或耦合分析使用 `analysis/abaqus-thermal-analysis` 或 `analysis/abaqus-coupled-analysis`。

设计迭代时按需求增加 `optimization/` 下的优化 skill。

## 客户端使用方法

这些是 skill 目录，不是 MCP server。它们应作为 agent 指令模块，配合 Abaqus、ANSYS、FEniCS 或其他本地求解器/MCP 工具使用。

### Codex

把需要的 skill 目录复制到 Codex skills 目录，然后重启 Codex：

```powershell
$src = "E:\Code\text-to-cae\Skill\abaqus\analysis\abaqus-static-analysis"
$dst = "$env:USERPROFILE\.codex\skills\abaqus-static-analysis"
New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
Copy-Item -Recurse -Force $src $dst
```

推荐提示词：

```text
使用 abaqus-static-analysis、abaqus-mesh、abaqus-job 和 abaqus-odb skills。帮我构建完整的 Abaqus 静力分析流程；如果 Abaqus MCP 或本地 Abaqus CLI 可用，就实际运行，并报告使用的文件和命令。
```

### Claude Code

项目级使用：

```powershell
New-Item -ItemType Directory -Force -Path .claude\skills | Out-Null
Copy-Item -Recurse -Force "E:\Code\text-to-cae\Skill\abaqus\modeling\abaqus-mesh" ".claude\skills\abaqus-mesh"
```

### Claude Desktop

Claude Desktop 主要通过 MCP server 配置工具能力。可以把这些目录作为参考上下文，或复制到支持 skills 的配套客户端中。配合 Abaqus MCP 使用时，引用对应 `SKILL.md` 并使用：

```text
按附加的 Abaqus 有限元 skill 指令执行。只有在需要真实求解操作时才调用已配置的 MCP 工具；如果只是建模建议，请明确说明不是求解结果。
```

### Cursor 和其他客户端

如果客户端支持项目级 skills，把需要的目录复制到对应的 skills 目录。如果不支持，就把相关 `SKILL.md` 作为项目上下文，并在提示词中明确要求遵循这些指令。

## 许可证和来源

每个导入目录都包含 `UPSTREAM.md`，记录来源 URL 和导入日期。如果上游仓库提供了许可证文件，也已保存为 `UPSTREAM_LICENSE` 或 `UPSTREAM_LICENSE.md`。

这些是第三方公开 skills。二次分发、修改后发布或商业打包前，应再次检查上游仓库和许可证条款。
