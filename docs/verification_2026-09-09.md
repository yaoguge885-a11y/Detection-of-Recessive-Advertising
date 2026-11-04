# P1 / M1 可运行交接验证（2026-09-09）

本记录来自整合后的独立工作区实际执行，不复用历史报告的测试数量。P1来源 `36298fa`、M1来源 `f43b6ff`、合并提交 `ac4f8f5`；随后纳入已完成的本地修复和交付工具。

## 环境与命令

- Windows，Python **3.12.5**，新建独立虚拟环境。
- 依赖：`requirements-handoff.txt` 和 `requirements-handoff.lock`。
- 验证入口：`python -X utf8 scripts/verify_handoff.py`。
- 实际运行标识：`handoff_checks_20260909_133442_984844`（UTC时间格式）。本地日志在 `data/run_outputs/`，公开保留本文聚合结论。

## 实际结果

| 检查 | 结果 | 证明范围 |
| --- | --- | --- |
| 标注工具 Python 回归 | **80 passed** | 模型契约、指南/参数、数据门禁、并行续跑、盲测页面及便携包 |
| 传统基线 Python 回归 | **54 passed** | 合成数据上的四种方法、历史时间隔离、共同cohort及正式门禁 |
| 主系统 Python 回归 | **408 passed，2 skipped，1 warning** | Agent、证据链、MCP、RAG、数据治理、CLI/API、工作台和wheel资源打包 |
| Python 合计 | **542 passed，2 skipped** | 三套互不重复的测试目录 |
| 工作台 Node 行为测试 | **退出码0，1个测试文件通过** | 既有浏览器脚本行为回归 |
| 两套提交资产校验 | **均退出码0** | 各自验证30条content、30条supplement |
| 合成盲测完整演示 | **passed** | 两条合成样本生成A/B页面、角色专属ZIP；角色隔离、媒体相对路径、包内可用性检查 |
| 系统 CLI 演示 | **退出码0** | `implicit-ad-agent/run_demo.py` 运行仓库示例，生成证据报告与run记录 |
| 依赖一致性 | **No broken requirements found** | 独立环境的 `pip check` |
| A/B HTML 内嵌 JavaScript | **两角色语法检查通过** | 生成页面脚本经 Node.js 解析 |

依赖清单另经 `pip install --dry-run -r requirements-handoff.txt` 核对解析成功。交接入口的本地文档链接有效；待提交文件未发现真实逐条样本标识或新增密钥。仓库隐私测试中的模拟token为测试fixture。

## 干净文件树复核

从已提交版本 `8ee5781` 使用 `git archive` 导出只含版本控制文件的全新目录，确认两份私有逐条清单不存在，再使用已验证的独立依赖环境运行同一验证脚本。运行标识 `handoff_checks_20260909_134010_786808`：九项检查全部退出码0，Python仍为 **542 passed、2 skipped**。这次复核排除了工作区未跟踪文件和私有材料残留的影响；两次测试结果是同一套测试，数量不相加。

两项跳过为显式的真实视觉集成测试，需要另行配置 YOLO/OCR 等依赖与实际媒体。警告来自 Starlette 对 AnyIO `BlockingPortal` 旧别名的弃用提示，不影响本次测试通过。真实 Qwen/Ollama、GPU推理、真实平台抓取、人工盲测和论文指标未在本轮运行，不能用上述542项替代这些验收。

## 复现时修复的环境问题

原虚拟环境缺少 MCP、Chroma 和 scikit-learn，因此重新创建完整环境。进一步发现 Python 3.12 环境需要显式安装 setuptools/wheel 才能运行离线wheel资源检查，已加入依赖清单。验证脚本为子进程统一UTF-8和独立临时目录，解决中文路径与默认临时目录访问问题。

## 研究边界

本次确认的是工程可运行与回归通过。M1阶段4模型路线、21条真实独立盲标、仲裁、正式锁批、Gold、κ、无泄漏切分和最终Gate依旧按 `HANDOFF.md` 的顺序接续，不因代码测试通过而自动完成。
