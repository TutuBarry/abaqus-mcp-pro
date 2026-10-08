# 结构静力与接触参考包

2026-09-28已在本机Abaqus 2026上运行通过六个参考算例和三点载荷扫描，并完成原始ODB/VTU数值对照。详见[真实验收报告](../../docs/ABAQUS_2026_VALIDATION.md)。这只覆盖所列算例与当前版本，不是全功能或跨版本认证。

单位采用 N、mm、s、tonne；应力为 MPa。`suite.json` 包含六个参考场景：

| 场景 | 输入 | 验收量与依据 |
|---|---|---|
| 轴向杆 | rod.inp | u=FL/(EA)，S11=F/A，支反力=-F |
| 悬臂梁 | beam.inp | u=-PL³/(3EI)，支反力=P；允许约1%的剪切和离散误差 |
| 两个实例同节点号 | instances.inp | 相同杆施加 F 和 2F，分别检查实例位移 |
| 壳膜拉伸 | shell.inp | S11=Eε，右端总反力=Eεbt，指定截面点1 |
| 两块接触压缩 | contact.inp | 无摩擦、ν=0、小滑移；R=EAδ/(2h)=10 N，容差0.2 N |
| 模态扩展检查 | modal.inp | 悬臂梁第一频率 β₁²/(2πL²)√(EI/ρA)，允许2%误差 |

`load_scan.json` 对杆件施加500、1000、1500 N，每个参数点分别验收。`exact` 合约的 tolerance 是**绝对误差**，与 expected 单位相同。`pct_change` 使用百分数。

## 准备、求解与复现

在仓库根目录执行：

```powershell
# 不启动求解器：展开参数、复制输入、记录哈希
python -m abaqus_mcp_pro.workflow examples/verification/suite.json --output runs

# 在安装了 Abaqus 的机器上执行
$env:ABAQUS_COMMAND = 'C:\SIMULIA\Commands\abaqus.bat'
python -m abaqus_mcp_pro.workflow examples/verification/suite.json --output runs --run
python -m abaqus_mcp_pro.workflow examples/verification/load_scan.json --output runs --run

# 从某次运行的自包含输入快照重新执行
python -m abaqus_mcp_pro.workflow runs/<run-id>/manifest.json --output runs --run
```

安装 wheel 后可直接使用 `abaqus-mcp-pro-verify --output runs`，默认选择随包附带的六场景清单；加 `--run` 才会求解。命令参数应是可执行文件或批处理路径，不是包含额外参数的整段 shell 命令。

每个运行都有独立目录，包含 `source_manifest.json`、可重放的 `manifest.json`、`run.json`、`report.md`、每个场景的 `analysis.inp`。真实运行额外产生求解日志、ODB、KPI JSON和合约结果。记录输入、源清单、重放清单和成功提取后的ODB SHA256。失败不会覆盖为 PASS；请求执行却未全部通过时退出码为2。

## 真实环境验收步骤

1. 在 Abaqus 2024、2025、2026 中分别完成输入处理和求解，记录版本、平台、许可和完整日志。不能依据当前软件测试声称兼容矩阵已通过。
2. 若输入语法或区域名称有版本差异，修正参考输入并保留失败证据。禁止只放宽容差以消除失败。
3. 用 CAE 原生查询核对每个 KPI 的 step、frame、region、component、position 与 section point；接触检查反力、间隙、接触压力和收敛日志。
4. 对梁和接触场景加密网格，确认误差趋势；当前参考包只提供基础单次/参数运行，不自动证明网格收敛。
5. 比较原生 ODB 与 VTU 的节点/单元数、实例节点号和数值。Viewer 将高阶单元显示为角点线性表面，元素节点应力采用等贡献平均、先计算不变量，可能跨材料区域；不能将云图峰值直接当作原生积分点极值。

## API 依据

- [Abaqus FieldOutput：getSubset / getScalarField](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEKERRefMap/simaker-c-fieldoutputpyc.htm)
- [Abaqus 梁单元与节点顺序](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEELMRefMap/simaelm-r-beamlibrary.htm)
- [Abaqus/Standard 面面接触定义](https://docs.software.vt.edu/abaqusv2025/English/SIMACAECAERefMap/simacae-t-itnhelpsurftosurfstd.htm)
- [VTK 单元类型](https://vtk.org/doc/nightly/html/vtkCellType_8h_source.html)


## rc2 接触扩展

```bash
python examples/verification/generate_contact.py --output runs/friction --curved --friction 0.2 --slide 0.5
python examples/verification/generate_contact.py --output runs/plastic --curved --plastic
python scripts/verify_contact_extensions.py --output audit-output --baseline <已有三级网格算例目录>
```

`--plastic` 使用演示性硬化曲线，不是实测材料。摩擦例采用有限滑移与 DIRECT 法向约束。检查器输出原生压力分布、未变形投影节点面积估计、压力积分力及能量。收敛指标独立报告，不能用反力收敛替代面积或峰值收敛。详见 [rc2 验收](../../docs/DELIVERY_RC2_2026-09-30.md)。
