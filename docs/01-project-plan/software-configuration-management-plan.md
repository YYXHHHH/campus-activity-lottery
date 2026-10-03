# 校园活动报名抽签与签到系统 —— 软件配置管理计划（SCMP）

> **所属阶段**：项目计划（配置管理）　|　**版本**：v1.0　|　**整理日期**：2026-10-02
> **内容来源**：项目实际工程实践；《开发文档》§1.2 目录结构、§6 依赖规则、§9 里程碑；`.gitignore`、`requirements.txt`、`run.bat`。

---

## 1. 目的与范围

规定本项目配置项的识别、版本控制、基线、变更控制、构建发布与备份恢复方式，保证交付物可追溯、可复现、可回滚。

## 2. 配置项识别

| 类别 | 配置项 | 位置 | 说明 |
| --- | --- | --- | --- |
| 后端代码 | 应用模块、路由、服务、调度器 | app/ | 严格三层结构 |
| 前端代码 | 页面、脚本、样式 | static/ | 原生 HTML/CSS/JS，无构建 |
| 测试代码 | pytest 用例 | tests/ | conftest + helpers + 13 个用例文件 |
| 脚本 | 演示数据、建表、一键启动、文档构建 | seed.py、init_db.py、run.bat、scripts/ | 脚本幂等 |
| 配置 | 依赖、配置模板、测试、忽略规则 | requirements.txt、.env.example、pytest.ini、.gitignore | .env 不入库 |
| 文档 | 全生命周期文档集 | docs/ | 每篇 Markdown 源（Word 按需生成） |

## 3. 配置库与版本控制

- 版本控制：Git，单一主干；
- 不纳入版本控制的项（见 .gitignore）：`.env`（含 SECRET_KEY）、`app.db` / `app.db-shm` / `app.db-wal`、`app.log`、`__pycache__/`、`.pytest_cache/`、`.venv/`。

## 4. 基线

| 基线 | 内容 | 时点 |
| --- | --- | --- |
| 需求基线 | 需求规格说明书 v1.0 | 需求评审通过 |
| 设计基线 | 概要/详细/数据库/接口设计说明书 v1.0 | 设计评审通过 |
| 代码基线 | app/、static/、tests/ 通过全部测试 | 每里程碑 |
| 测试基线 | 测试计划、测试报告（78 passed） | 测试完成 |
| 交付基线 | 文档集 + 演示数据 + 可运行包 | 验收通过 |

## 5. 变更控制

- 需求变更先改《需求规格说明书》，再同步设计、数据库、接口、测试文档；
- 设计变更同步更新《开发文档》正式原件与拆分文档；
- 依赖升级须评估兼容性，passlib 与 bcrypt 必须成对升级；
- 文档变更后重跑 `scripts/md_to_docx.py` 刷新 Word 版；
- 变更记录写入《过程记录》。

## 6. 构建与发布

- 一键构建/启动：`run.bat`（demo 演示模式 / dev 开发模式）；
- 依赖安装：`pip install -r requirements.txt`（清华源）；
- 数据初始化：`python seed.py`（幂等）；建表：`python init_db.py`；
- 发布红线：单进程单 worker，演示/验收禁用 `--reload`（避免调度器多实例）；
- 文档构建：`scripts/md_to_docx.py`；结构校验：`scripts/verify_docx.py`。

## 7. 配置状态记录与审计

| 记录 | 位置 |
| --- | --- |
| 文档索引与整理规则 | docs/README.md |
| 过程记录 | docs/99-archive/process-log-2026-10-01.md |
| 测试与验收结果 | 测试报告、验收报告 |
| 归档说明 | docs/99-archive/README.md |

## 8. 备份与恢复

- 数据库备份：停服后备份 `app.db`（WAL 模式需同时保留 -wal/-shm 或先合并）；
- 演示数据重置：停止服务 → 删除 `app.db*` → `python seed.py`；
- 密钥管理：`SECRET_KEY` 仅存于 `.env`，不入库，长度 ≥ 16 的随机值。

---
（文档完）
