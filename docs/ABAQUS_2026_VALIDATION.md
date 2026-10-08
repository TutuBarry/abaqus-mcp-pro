# Abaqus 2026 真实环境验收（2026-09-28）

已确认本机Abaqus 2026可启动并完成真实求解。六个参考算例、三点载荷扫描均通过预先定义的数值合约；这不是全部工具、所有分析类型或跨版本兼容认证。

## 环境与证据

- 启动命令：`D:\Program Files\SIMULIA\Commands\abaqus.bat`。
- Abaqus内置Python：3.10.5；宿主测试Python：3.14.6。
- 六场景运行：`E:\WQG\Agent workspace\ABAQUS MCP\audit-artifacts\abaqus-2026-runs\20260928T135106Z_72c295df24c5`。
- 三点扫描运行：`E:\WQG\Agent workspace\ABAQUS MCP\audit-artifacts\abaqus-2026-runs\20260928T135339Z_3b4237808fa8`。
- 机器可读记录：[VALIDATION_2026-09-28.json](VALIDATION_2026-09-28.json)。旧的9月26日报告保留为当时状态。

## 数值结果

| 算例 | KPI | 解析目标 | 实际结果 | 绝对容差 | 结果 |
|---|---|---:|---:|---:|---|
| axial_rod | u | 0.04761904762 | 0.04761904851 | 4.7619e-07 | PASS |
| axial_rod | stress | 100 | 100 | 0.001 | PASS |
| axial_rod | reaction | -1000 | -1000 | 0.01 | PASS |
| cantilever | u | -1.904761905 | -1.904837489 | 0.02 | PASS |
| cantilever | reaction | 1 | 1 | 1e-05 | PASS |
| multiple_instances | one | 0.04761904762 | 0.04761904851 | 4.7619e-07 | PASS |
| multiple_instances | two | 0.09523809524 | 0.09523809701 | 9.52381e-07 | PASS |
| shell_membrane | stress | 21 | 21 | 0.021 | PASS |
| shell_membrane | reaction | 210 | 210 | 0.21 | PASS |
| frictionless_contact | reaction | 10 | 10 | 0.2 | PASS |
| cantilever_modes | frequency | 8.355165944 | 8.3524 | 0.167103 | PASS |

载荷扫描500、1000、1500 N分别通过位移、应力和反力合约。合约容差未因运行结果而放宽。

## 额外联调

- 使用独立脚本遍历ODB原始场值，与已保存KPI逐项对照，六个算例一致。
- 六个真实ODB均成功导出VTU；所有导出帧的位移与原始ODB一致。
- 轴向杆S11=100 MPa；双实例分别100/200 MPa；壳S11=21 MPa；接触块S33=-10 MPa，导出节点值均符合解析目标。
- CAE noGUI实际创建实体、材料、截面和网格，得到189节点、80单元；弹性、密度和塑性表可执行。
- 实际CAE进程中的socket ping、能力查询、模型信息、ODB打开/摘要/S与U提取/关闭及脚本执行共9项均通过。
- 查看器HTTP接口完成接触ODB导出、状态查询、重复请求去重和真实文件回载：16节点、2单元、11帧。
- 有意失败的CAE脚本返回码为0，但包含Abaqus错误诊断；产品现在正确返回ok=false。

## 联调发现与修复

1. 无Part/Assembly块的参考输入，其节点集实际位于`PART-1-1`实例下。清单已显式使用`PART-1-1/TIP`等选择，不做模糊回退。首轮失败日志保留。
2. Abaqus FieldValueArray拒绝切片，结构化字段提取改用有界索引访问；同时按精度回退dataDouble，且仅在MISES有效时返回mises。
3. 本次noGUI新模型未暴露constraints仓库，模型摘要和capsule现在显式报告unavailable_repositories，不使整个查询失败。
4. CAE noGUI脚本没有__file__，真实验证脚本改由显式源码目录环境变量定位。
5. 安装后运行中的客户端PATH未刷新，增加统一命令发现，覆盖Program Files下的安装目录。
6. 识别启动器零返回码但日志含`Abaqus Error:`的失败。

软件回归：379项通过；新增5项覆盖这些实测API形状、启动器和发现路径。Pyflakes检查通过。

## 已安装插件及尚待验证

已更新用户插件目录中的GUI插件和同目录runtime。需要在实际CAE窗口中激活菜单才能验收GUI事件循环；本轮通过的是noGUI内核及socket，不把它等同于GUI菜单验收。

本轮浏览器连接不可用，真实模型的页面渲染尚未目视验收。2024/2025版本、大型ODB性能、网格收敛、接触压力/间隙更完整的判据、持久化恢复仍是后续工作。

验证脚本：`scripts/abaqus_runtime_smoke.py`；运行前设置`ABAQUS_MCP_VERIFY_SOURCE`和`ABAQUS_MCP_VERIFY_ODB`，在独立目录执行`abaqus cae noGUI=<脚本绝对路径>`。

字段API依据：[Abaqus FieldValue文档](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEKERRefMap/simaker-c-fieldvaluepyc.htm)。本机2026对应文档也已核对。

发布候选检查：sdist/wheel构建、独立环境安装、MCP stdio握手与工具/资源查询、twine均通过；工具135、提示词13、资源74。构建产物位于工作区`audit-artifacts/release-2026-09-28`，未对外发布。
