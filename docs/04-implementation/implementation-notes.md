# 校园活动报名抽签与签到系统 —— 实现说明
> **所属阶段**：编码实现　|　**版本**：v1.0　|　**整理日期**：2026-10-02

> 文档性质：**开发完成后产出**的实现对照说明。
> 输入依据：《开发文档》（其内容已拆分为 docs/03-design/ 与 docs/05-testing/ 的规范文档，含 S1~S10 约定、M0~M10 模块、I-1~I-8 集成点、R1~R12 风险）。
> 本文回答三件事：**建了哪些文件、开发文档的每一条落在哪段代码、与文档有哪些差异**。
> 配套文档：`interface-design.md`（对外契约）、`test-report.md`（自动化测试）、`deployment-manual.md`（运行与排障）、`acceptance-report.md`（A1~A12）。

## 1. 交付物总览

| 层 | 文件 | 规模 | 说明 |
| --- | --- | --- | --- |
| 后端 | `app/`（10 个基础模块 + 5 个 router + 5 个 service + scheduler） | 约 2200 行 | 严格三层：`routers → services → models` |
| 前端 | `static/`（9 个 HTML + `js/api.js` + `js/app.js` + `css/style.css`） | 12 个文件 | 原生 HTML/CSS/JS，无构建工具、无 CDN 依赖 |
| 测试 | `tests/`（`conftest.py` + `helpers.py` + 13 个测试文件） | 约 2000 行，78 个用例 | 内存 SQLite + TestClient |
| 脚本 | `seed.py`（附录 C 演示数据）、`init_db.py`（建表） | — | 均为幂等 |
| 配置 | `requirements.txt`、`.env.example`、`pytest.ini`、`run.bat`、`.gitignore`、`README.md` | — | 对应 §11 |

依赖版本与开发文档一致：FastAPI 0.111.0、SQLAlchemy 2.0.30、Pydantic 2.7.1、passlib 1.7.4 + bcrypt 4.1.3（双 pin，R5）、PyJWT 2.8.0、APScheduler、openpyxl、qrcode + pillow、pytest 8.2.0。

## 2. 模块实现对照（M0~M10）

| 模块 | 文件 | 关键实现点 | 对应文档 |
| --- | --- | --- | --- |
| M0 基础设施 | `app/config.py` | `Settings`（pydantic-settings）+ `lru_cache` 单例；启动即校验 `SECRET_KEY`（长度 <16 或命中示例值集合直接抛 `RuntimeError`）；`PUBLIC_BASE_URL` 去尾部 `/` | §1.3、R9 |
| | `app/database.py` | `utcnow/as_utc/iso_z` 全项目唯一时间入口（R3）；SQLite `check_same_thread=False, timeout=30`；`event.listens_for(engine,"connect")` 执行 `PRAGMA journal_mode=WAL` + `busy_timeout=30000`；`clamp_page`（size 默认 10 上限 50）、`build_page`（S2）、`retry_on_locked` 退避重试 | §5.9、S2/S4、R1 |
| | `app/models.py` | 4 张表 + 全部唯一约束与索引；`_StrEnum` 基类；`SAEnum(native_enum=False)`；`cascade="all, delete-orphan"`；`ACTIVITY_STATUS_CN/REGISTRATION_STATUS_CN/ROLE_CN`（附录 A） | §4.2、§4.4 |
| | `app/schemas.py` | `UtcDatetime = Annotated[datetime, PlainSerializer(iso_z, when_used="json")]` → 所有时间输出 `...Z`；Pydantic 层拦截 quota/长度/role 白名单 | §3.7、S6 |
| | `app/errors.py` | `BizError` + 6 个便捷子类；4 个全局异常处理器；`FRIENDLY_MESSAGES` 把 Pydantic 英文错误转中文（`字段：中文提示`） | §7.1、附录 B |
| M1 认证 | `app/security.py`、`app/deps.py`、`app/routers/auth.py` | JWT payload `{sub,role,iat,exp}`（`sub` 为用户 id 字符串）；`verify_password` 吞异常永不抛；`get_current_user` 每请求查库 → 禁用即时生效（§2.11）；`require_role` 工厂 + `assert_activity_owner` 构成「角色 + 归属」双校验 | §5.1、S1 |
| M2 活动 | `app/routers/activities.py` | 创建（默认 DRAFT，可一步发布）、列表（学生视角状态白名单 + `mine` + `keyword` LIKE 参数化）、详情（I-2 兜底抽签 + `my_registration` + `registered_count` + DRAFT 非本人 40301）、编辑（§2.4 状态机守卫 + S10 名额改小拒绝 + I-4 递补）、发布/取消 | §2.4、§3.3、I-2/I-4 |
| M3 报名 | `app/services/registration.py`、`app/routers/registrations.py` | `signup`（S4 `now < deadline`、取消记录复用并保留 `created_at`、`IntegrityError → 40901`）；`cancel_or_withdraw` 语义分流（WON → WITHDRAWN + 清 `qr_token` + 同事务 `promote_waitlist`）；`my_registrations`（`joinedload` 预加载，排除 CANCELLED）；二维码 PNG（`box_size=8, border=2`，`no-store`） | §2.5、§5.5、I-3 |
| M4 抽签 | `app/services/lottery.py::run_lottery` | 抽签唯一入口（§6.1-3）：状态守卫 → **条件 UPDATE 原子占位** → `random.Random(seed).shuffle`（输入 `order_by(id)` 固定）→ rank 赋值 → WON 发码 / WAITING / LOST → commit + INFO 日志 | §5.2 |
| M5 递补 | `app/services/lottery.py::promote_waitlist` | 按 `lottery_rank` 升序补 `quota - won_count` 差额；**只 flush 不 commit/rollback**，事务控制权归调用方；MySQL 才加 `with_for_update()` | §5.3、§6.4 |
| M6 签到 | `app/services/checkin.py`、`app/routers/checkins.py` | 六步校验链（空码/URL 解析 → 码存在 → 归属活动 → 状态 WON → 未签到 → 落库）；重复签到返回 40901 + 「该同学已于 HH:mm 签到」+ 首次时间；`manual_checkin` 按学号补签 `method=MANUAL` | §5.6、I-5 |
| M7 统计导出 | `app/services/stats.py`、`app/services/exporter.py` | 六计数三比率、分母为 0 记 0、比率 4 位小数（S8）；两张表列头严格按 §5.8，表头加粗居中、`freeze_panes="A2"`、按 CJK 宽度自适应列宽；`filename*=UTF-8''`（S9/R6） | §5.7、§5.8 |
| M8 调度 | `app/scheduler.py` | `BackgroundScheduler` interval job（`max_instances=1, coalesce=True`），逐活动 `try/except + logger.exception`（单活动失败不断批）；`AUTO_LOTTERY_ENABLED=false` 可关；关闭时 `shutdown(wait=False)` | §5.4、I-1 |
| M9 管理 | `app/routers/admin.py` | 用户分页 + `keyword/role` 过滤；`AdminUserPatch` + `exclude_unset` 局部更新；禁改 ADMIN 角色；禁用后旧 token 立即 40101 | §2.11 |
| M10 前端 | `static/` | `api.js` 作为唯一 HTTP 出口（token 注入、401 跳登录、`{code,message,data}` 拆包、错误 toast）；状态徽章配色统一在 `style.css` | §5.x、I-7 |

## 3. 集成点落地核对（I-1 ~ I-8）

| 编号 | 文档要求 | 实现位置 | 验证方式 |
| --- | --- | --- | --- |
| I-1 | 调度器每 30s 扫到期 PUBLISHED | `scheduler.scan_due_activities` → `run_lottery` | `test_scheduler.py::test_scan_lots_due_activities`；真实运行日志显示截止后 7 秒完成抽签 |
| I-2 | 详情接口兜底触发抽签 | `routers/activities.get_activity` | `test_activity.py` + `test_scheduler.py::test_scan_is_idempotent` |
| I-3 | 退出中签 → 同事务递补 | `services/registration.cancel_or_withdraw` | `test_waitlist.py::test_waitlist_promotion_on_withdraw`（断言 `promoted=1` 且新码生效、旧码失效） |
| I-4 | 名额调大 → 同事务递补 | `routers/activities.edit_activity` | `test_waitlist.py::test_quota_increase_promotes_from_waitlist` |
| I-5 | 签到校验链 + UNIQUE 兜底 | `services/checkin.do_checkin` | `test_checkin.py` 9 例 + `test_data_integrity.py::test_checkin_unique_registration_blocks_double_row` |
| I-6 | 导出 left join 取签到时间 | `services/exporter.build_workbook` | `test_export_excel.py` |
| I-7 | 前端统一 API 出口 | `static/js/api.js` | 手工验收 A1~A9 |
| I-8 | seed 演示数据 | `seed.py` | `python seed.py` 输出 + 手工验收 A2 |

事务边界（§6.4）核对：只有 `run_lottery`、`do_checkin`、`manual_checkin`、以及路由/服务层的**调用方**（报名、退出+递补、编辑+递补）会 `commit()`；`promote_waitlist` 仅 `flush()`。

## 4. 与开发文档的差异、补充与修正

以下均为**实现期发现并处理**的事项，未改变 P0 需求语义。

1. **枚举 `str()` 陷阱（必须记录的坑）**
   文档 §4.4-1 建议 `class ActivityStatus(str, enum.Enum)`。Python 3.10/3.11 下 `str(member)` 得到 `"ActivityStatus.DRAFT"` 而非 `"DRAFT"`，导致按状态聚合的字典键、SQL 绑定值和响应文案全部错位（首个症状是 `stats.py` 抛 `KeyError: 'PENDING'`）。
   处理：新增 `_StrEnum` 基类覆写 `__str__` 返回 `self.value`，四个枚举统一继承；同时所有枚举列显式传 `values_callable=lambda e: [m.value for m in e]`，保证 DB 存的是纯字符串。
2. **`promote_waitlist` 前置 `db.flush()`**
   「退出 + 递补」在同事务内先置 `WITHDRAWN` 再统计 `won_count`；若依赖 autoflush 时序（或关闭 autoflush）会读到过期计数，`vacancy` 算成 0 导致「退了没补」。
   处理：函数首行显式 `db.flush()`，同时 `SessionLocal` 保持 SQLAlchemy 默认 `autoflush=True`（测试库同样如此）。这是 I-3 的正确性前提，已写入 `test_waitlist.py` 断言。
3. **活动详情响应新增 `lottery_status_cn`**
   §3.3 未定义该字段；前端需要中文状态标签（附录 A）。作为**附加只读字段**加入 `ActivityDetailOut`，不影响既有契约。
4. **统计响应新增 `cancelled`**
   §5.7 定义六计数三比率；实现额外返回 `cancelled`（已取消报名数），便于排查「名单里少了几个人」。原有字段名与含义完全保持，文档 §5.7 的示例响应被 `test_stats_matches_document_example` 逐字段断言通过。
5. **抽签响应成功时也带 `reason: null`**
   §3.3 的响应结构只在未执行时出现 `reason`。统一为 `{executed, reason, won, waiting, lost}` 五键恒定，前端无需判空分支。
6. **`with_for_update()` 按方言启用**
   文档 §5.3 代码无条件调用；SQLite 会忽略但 SQLA 仍生成 `FOR UPDATE` 文本，改为仅 `db.bind.dialect.name == "mysql"` 时附加（§4.2 迁移注意项的一部分）。
7. **`BCRYPT_ROUNDS` 环境变量（默认 12）**
   性能与测试可用性的平衡：§10.2 性能验收与 1000 用户造数时 bcrypt 成为瓶颈，测试环境设 4。生产保持 12，不影响哈希兼容性（同 rounds 校验自动识别）。
8. **OpenAPI/Swagger 路径挂在 `/api` 前缀下**
   在线文档实际地址是 `/api/docs`、`/api/openapi.json`（`/redoc` 保持默认），避免与静态站点根路径冲突。
9. **签到路由独立成 `app/routers/checkins.py`**
   与文档 §1.2 目录树一致（M6 单独成模块），§3.5 的两个接口路径不变。
10. **`audit_logs` 可选表未实现**
    §4.2 标注为 P1、建议预留但 MVP 不写数据。当前以 INFO 日志承担审计（抽签 seed、递补 user_ids、签到 operator、导出行数），未建空表，避免引入无写入方的 schema。
11. **`retry_on_locked` 兼容位置参数**
    文档 §5.9-2 只描述装饰器；实现需从 `kwargs["db"]` 或位置参数中定位 Session 才能 `rollback()`，否则重试前事务未回滚、必然再次失败。
12. **Pydantic 校验错误统一 400/40001**
    FastAPI 默认返回 422；文档 §7.1 要求 400。已在 `RequestValidationError` 处理器中改写状态码与中文 message，`test_role_guard`/`test_activity` 按 400 断言。

## 5. 关键技术点实现摘要

**抽签可复现（§4.3 审计）**：`seed = secrets.token_hex(16)` 与活动状态占位在**同一条条件 UPDATE** 中写入，因此获得 seed 即获得执行权；未获得占位方（`rowcount==0`）直接返回 `concurrent_or_done`。待抽签报名以 `order_by(Registration.id)` 取入，`random.Random(seed).shuffle` 后按位次赋 `lottery_rank`，因此用同一个 seed 重放 shuffle 可完全重建名单——该性质由 `test_data_integrity.py::test_lottery_is_reproducible_from_seed` 断言。

**并发防重复报名/签到（§4.5）**：应用层前置查询只负责友好提示，正确性由 `UNIQUE(activity_id, user_id)`、`UNIQUE(checkins.registration_id)` 兜底，`IntegrityError` 转 40901；重复签到还会在 `data.checked_in_at` 回传首次签到时间（§3.5）。

**签到码解析（§5.6-1）**：`code` 允许是裸 token、`?code=xxx` 查询串或完整二维码 URL，统一取出参数值后查库；无效码 40401，跨活动码 40001。

**导出（§5.8）**：中签表仅导出**当前有效** WON 记录（WITHDRAWN 排除），并含签到码列；报名表含签到状态与时间。响应同时给出 `filename=export.xlsx`（兜底旧浏览器）与 `filename*=UTF-8''…`（RFC 5987），中文活动名实测为 `%E6%91%84%E5%BD%B1…_中签表_20261001.xlsx`。

**日志（§7.3）**：`setup_logging()` 控制台 + `app.log`（只读目录自动降级为仅控制台），格式 `{时间} {级别} [{模块}] {事件} key=value`；抽签/递补/签到/导出四类 INFO 事件字段齐全，异常统一 `logger.exception`。

## 6. 已知限制（按文档定位，非缺陷）

| 限制 | 来源 | 影响与后续 |
| --- | --- | --- |
| 单进程单 worker，禁止 `--reload` 演示 | §5.9-3、R2 | 多实例会导致调度器重复触发（条件 UPDATE 已提供最后防线）。`run.bat` 已把 dev/demo 两种模式分离 |
| SQLite 写并发上限 | §5.9、R1 | 高峰报名靠 WAL + timeout + 重试；超规模场景按文档切换 MySQL（只改 `DATABASE_URL`） |
| 静态二维码可被截图代签 | R4 | 签到页显示姓名/学号供人工核对；30s 轮换动态码属迭代方向 |
| 统计为实时计算，无缓存/物化视图 | §5.7 | 千行级无压力（实测 1000 人抽签 48ms） |
| 前端无构建、无路由框架 | §10.2 | 页面用 query 参数传递 id；迁移 Vue 时结构一一对应 |
| `audit_logs` 埋点表未建 | §4.2 P1 | 见 §4 差异 10 |

## 7. 验收结论摘要

- 自动化测试：**78 passed**，覆盖 §10.1 全部用例条目（映射见 `test-report.md`），并额外验证 §4.5 数据库约束、§4.3 seed 复现、§10.2 性能（1000 条报名抽签 48ms < 1s）。
- 运行验证：`python seed.py` + `uvicorn` 冷启动通过；自动抽签在截止后 7 秒完成；组织者侧 winners / checkins / stats / export 接口返回真实数据，中文文件名与 xlsx 字节流正常。
- 手工验收 A1~A12：见 `acceptance-report.md`（含逐条结果与发现的问题及修复记录）。
- 运行环境实测：`.venv` 使用 **Python 3.10.11**（开发文档 §0 规定 3.11）；依赖安装、服务启动、78 个用例与 A1~A11 全部通过，故 README 与部署手册把要求放宽为「3.10 / 3.11」，并注明文档基线为 3.11。
- 交付前清理：验收残留（临时活动、临时账号、签到记录）已清除，`del app.db* + python seed.py` 重置为附录 C 演示数据（1 ADMIN / 1 ORGANIZER / 20 STUDENT、3 个 PUBLISHED 活动、每活动 20 条 PENDING 报名、无签到记录）。
- 本轮修复补充：`checkin.html` 的摄像头扫码按钮改为「`BarcodeDetector` 与 `navigator.mediaDevices` 同时可用才显示」，避免局域网 `http://IP:8000` 非安全上下文下点击抛异常；导出文件名、弹窗遮罩、重复签到本地时间等修复见 `acceptance-report.md` §1。
