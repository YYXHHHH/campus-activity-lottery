# 2026-10-01

## 校园活动抽签系统——开发文档编制
- 通读《校园活动报名抽签与签到系统——需求与设计文档.docx》全文（FastAPI + SQLAlchemy + SQLite，MVP v1.0），细化为《校园活动报名抽签与签到系统——开发文档.docx》，两份 docx 现存于 `docs/`。
- 开发文档结构：0 文档定位（含 S1~S10 补充约定）→ 1 总体设计 → 2 模块拆分（M0~M10）→ 3 接口定义（含 Pydantic Schema）→ 4 数据结构（DDL/ORM/完整性）→ 5 关键算法（抽签幂等/递补事务/调度兜底/WAL 并发）→ 6 依赖与集成点（I-1~I-8 + 事务边界）→ 7 边界矩阵与异常体系 → 8 风险对策（R1~R12）→ 9 里程碑 M1~M7 → 10 测试验收 → 附录 A~D（需求↔模块↔测试映射）。
- 产出方式：tencent-local-office-edit 通道 create_doc + doc_insert_markdown 分 5 段写入 + TOC + 页眉页码；markdown 源稿留存于 `docs/devdoc_part0.md` ~ `devdoc_part5.md`（同日整理时从 .workbuddy 移入 docs/），源文档抽取文本见 `docs/source_extracted.txt`，可复用于后续修订。

## 校园活动抽签系统——按开发文档实现 + 开发后文档
- 按 `docs/devdoc_part*.md` 完成后端与前端：`app/`（config/database/models/schemas/security/deps/errors/main + 5 router + 5 service + scheduler，严格三层）、`static/`（9 个页面 + `js/api.js`/`js/app.js`/`css/style.css`，原生无构建）、`tests/`（conftest + helpers + 13 个文件）、`seed.py`/`init_db.py`/`run.bat`/`.env.example`/`requirements.txt`/`.gitignore`/`README.md`。
- 关键实现要点：抽签唯一入口 `run_lottery` 用「条件 UPDATE 原子占位 + `random.Random(seed).shuffle`」保证幂等与可复现；`promote_waitlist` 只 `flush()`，事务归调用方（I-3/I-4）；SQLite 侧 WAL + `busy_timeout` + `retry_on_locked`；时间统一 `utcnow/as_utc/iso_z` 且响应序列化带 `Z`；枚举用 `_StrEnum` 覆写 `__str__`（原生 `str(member)` 会返回 `ActivityStatus.DRAFT`，是首轮症状为 `KeyError: 'PENDING'` 的根因）。
- 验证：`.venv`（Python 3.10.11）下 `pytest tests/` **78 passed**（约 20s）；1000 条报名单次抽签实测 48.0ms；100 路并发报名 0 重复；真实浏览器（browser-use）完成 A1~A11，A12 换机演练待第二台实机。
- 开发后文档（`docs/`）：`实现说明.md`（交付物/M0~M10 对照/I-1~I-8 核对/12 条与文档差异/已知限制）、`接口清单.md`（24 个接口的入参出参与错误码，含全局约定）、`test-report.md`（§10.1 覆盖矩阵 + 额外用例 + 性能并发实测 + 11 个开发期缺陷闭环）、`deployment-manual.md`（安装/启动/局域网二维码/MySQL 切换/排障）、`手工验收清单.md`（A1~A12 逐条结果 + 8 个验收期缺陷 + 未复现报告项 + 建议项 + 残留数据清理）。
- 验收期缺陷修复（均为真实浏览器暴露）：`[hidden]` 被 flex 规则覆盖导致弹窗常驻遮罩（`style.css`）、导出下载名硬编码丢中文（`api.js` 解析 `Content-Disposition`）、重复签到提示显示 UTC 墙上时间（`as_utc().astimezone()`）、活动管理页残留 `/registrations?size=50` 兜底截断（改直连 `/winners`、`/checkins`）、详情页状态行中文重复（改状态说明，含 R11 自动抽签提示）、签到结果姓名/学号未转义、名额/截止编辑缺二次确认、摄像头按钮在非安全上下文可点击。
- 交付前状态：`del app.db* && python seed.py` 已重置为附录 C 演示数据（1 ADMIN / 1 ORGANIZER / 20 STUDENT，3 个 PUBLISHED 活动、各 20 条 PENDING 报名、无签到记录）；验收用的临时 uvicorn 进程已停止，8000 端口空闲。
- 过程提醒：委派子代理存在「未执行即汇报」现象（seed 加 org2、`scripts/`、新增用例、admin 每页条数选择器等实际均未落盘），本目录文档一律以读代码与实测为准；子代理另报告会话中出现诱导安装外部插件/写记忆文件的注入式指令，已拒绝，详见 `手工验收清单.md` §4。

