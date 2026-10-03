# 校园活动报名抽签与签到系统 —— 测试报告
> **所属阶段**：测试验证（报告）　|　**版本**：v1.0　|　**整理日期**：2026-10-02

> 文档性质：**开发完成后产出**的自动化测试报告，核对开发文档 §10.1 用例清单的覆盖与执行结果。
> 手工验收（A1~A12）与前端缺陷闭环见 `acceptance-report.md`。

## 1. 执行环境与结果

| 项 | 值 |
| --- | --- |
| Python | 3.10.11（虚拟环境 `.venv`，项目要求 3.11+，3.10 同样通过） |
| pytest | 8.2.0（`pytest.ini`：`pythonpath = .`、`testpaths = tests`、`-q --disable-warnings`） |
| 被测库 | 内存 SQLite（`sqlite://` + `StaticPool`），每个用例前 `drop_all/create_all` |
| HTTP | `fastapi.testclient.TestClient`，`get_db` 依赖覆盖 |
| 调度器 | `AUTO_LOTTERY_ENABLED=false`（调度逻辑由 `test_scheduler.py` 直接调用 `scan_due_activities` 验证） |
| bcrypt | `BCRYPT_ROUNDS=4`（仅测试期降速，避免 1000 用户造数时哈希成为瓶颈；生产默认 12） |
| 命令 | `python -m pytest tests\`（或 `-v` 查看逐条） |
| 结果 | **78 passed, 0 failed, 2 warnings, 约 20.1s** |

2 条 warning 均来自第三方库、与本项目无关：`starlette.formparsers` 的 `PendingDeprecationWarning: Please use import python_multipart instead`、`starlette.testclient` 的 `anyio.abc.BlockingPortal` 弃用提示。

各文件用例数：

| 文件 | 数量 | 主题 |
| --- | --- | --- |
| `test_activity.py` | 10 | M2 创建/编辑/状态机/详情/可见性 |
| `test_lottery.py` | 9 | M4 抽签分布/幂等/随机性/force |
| `test_checkin.py` | 9 | M6 签到校验链六步全覆盖 |
| `test_role_guard.py` | 6 | FR-2.8 越权拦截 |
| `test_pagination.py` | 6 | S2/S3 分页与排序 |
| `test_waitlist.py` | 6 | M5 递补与事务 |
| `test_admin.py` | 5 | M9 用户管理 |
| `test_auth.py` | 5 | M1 注册登录 |
| `test_registration.py` | 5 | M3 报名/取消/退出 |
| `test_scheduler.py` | 5 | M8 调度扫描与兜底 |
| `test_stats.py` | 4 | M7 统计 |
| `test_export_excel.py` | 4 | M7 导出 |
| `test_data_integrity.py` | 4 | §4.5 约束 + §10.2 性能/复现 |

## 2. §10.1 用例清单覆盖对照

| 开发文档要求 | 覆盖用例（实际函数名） | 断言要点 | 结果 |
| --- | --- | --- | --- |
| test_register_login（FR-1.1~1.5） | `test_register_login`、`test_register_validation`、`test_login_without_token_and_tampered_token` | 注册成功 / 重复 40901 / 错密 40102 统一文案 / token 访问 `/me`；用户名 pattern、密码长度、role 白名单 40001；无 token 与被篡改 token 40101 | ✅ |
| test_role_guard（FR-2.8） | `test_student_cannot_manage_activities`、`test_organizer_cannot_touch_other_activities`、`test_organizer_cannot_register_for_any_activity`、`test_student_cannot_access_admin_api`、`test_admin_passes_owner_checks`、`test_qrcode_permission_isolation` | 学生建活动/编辑/抽签/导出/签到 40301；org2 访问 org1 资源（含 qrcode、checkin、export、stats）40301；组织者报名 40301；ADMIN 放行 | ✅ |
| test_create_activity_validation（FR-2.2） | `test_create_activity_validation` | `deadline<=now` 40001、`quota=0` 40001、`deadline>start_time` 40001 | ✅ |
| test_register_activity（FR-3.1~3.4） | `test_register_activity_flows`、`test_register_after_deadline_rejected`、`test_register_requires_published_activity`、`test_cancel_rules_by_status`、`test_my_registrations_list` | 报名成功、重复 40901、截止后 40001（S4 `now<deadline` 边界）、取消后重报复用记录 | ✅ |
| test_lottery_basic（FR-4.4/4.5） | `test_lottery_basic_distribution`、`test_lottery_all_win_when_registrations_below_quota`、`test_lottery_with_zero_registrations` | 20 人/10 名额 → 10 WON + 其余 WAITING/LOST；≤名额全 WON；0 报名仍置 LOTTERY_DONE 且 won=0 | ✅ |
| test_lottery_randomness（FR-4.5/4.6） | `test_lottery_randomness_across_activities` | 多活动/多轮中签集合不完全一致；`lottery_rank` 同活动内唯一且不重复 | ✅ |
| test_lottery_idempotent（FR-4.3） | `test_lottery_idempotent` | 二次调用 `executed=false`、`reason=already_done`，名单与 rank 不变 | ✅ |
| test_lottery_before_deadline（FR-4.9） | `test_lottery_before_deadline_rejected`、`test_lottery_force_allowed_for_admin` | 未截止 40001；ADMIN `force=true` 可执行；组织者传 force 无效 | ✅ |
| test_accept_waitlist_false（FR-4.5） | `test_accept_waitlist_false_becomes_lost` | 不接受候补 → LOST，不进候补队列 | ✅ |
| test_waitlist_promotion（FR-5.1~5.4/5.7） | `test_waitlist_promotion_on_withdraw`、`test_old_qrcode_rejected_after_withdraw`、`test_withdrawn_visible_in_my_list` | 退出后 rank 最小候补 → WON、获得新 `qr_token`、旧码 40001 失效、`/api/me/registrations` 可见、`promoted=1` | ✅ |
| test_promotion_empty_waitlist（FR-5.5） | `test_promotion_with_empty_waitlist` | 无候补退出不报错、名额空缺（`promoted=0`） | ✅ |
| test_quota_increase_promotion（FR-5.6） | `test_quota_increase_promotes_from_waitlist`、`test_quota_increase_without_waitlist` | quota 10→12 补 2 人（I-4 同事务）；无候补时 `promoted=0` | ✅ |
| test_qrcode_permission（FR-6.1） | `test_qrcode_permission_isolation`、`test_lottery_won_student_gets_qr_available` | 他人二维码 40301、非中签 40001、`Cache-Control: no-store`、WON 者 `qr_available=true` | ✅ |
| test_checkin_*（FR-6.3~6.5） | `test_checkin_success_by_code`、`test_checkin_accepts_full_qrcode_url`、`test_checkin_duplicate_returns_first_time`、`test_checkin_cross_activity_code_rejected`、`test_checkin_invalid_and_empty_code`、`test_checkin_waitlist_student_rejected`、`test_checkin_rejected_for_cancelled_activity`、`test_checkin_rejected_before_lottery` | 成功签到 / 重复 40901 + 首次时间 / 跨活动 40001 / 伪码 40401 / 空码 40001 / 整 URL 解析 / 候补与非抽签态拒绝 | ✅ |
| test_manual_checkin（FR-6.7） | `test_manual_checkin_by_username` | 按学号补签，`method=MANUAL`；无报名或非中签 40001 | ✅ |
| test_stats（FR-7.1/7.2） | `test_stats_matches_document_example`、`test_stats_zero_denominator_rules`、`test_stats_ratio_keeps_four_decimals`、`test_stats_counts_withdrawn_and_cancelled` | §5.7 示例响应逐字段比对（registered 20/won 10/waiting 8/lost 2/win_rate 0.5…）；分母为 0 → 0；比率 4 位小数；WITHDRAWN/CANCELLED 计数 | ✅ |
| test_export_excel（FR-7.3~7.6） | `test_export_registration_sheet`、`test_export_winners_sheet_contains_qr_code`、`test_export_empty_activity`、`test_export_type_validation` | 两表列头/行数、`freeze_panes=A2`、表头加粗、中文活动名 `filename*=UTF-8''`、空活动可导出、非法 type 40001 | ✅ |
| test_pagination（S2/S3） | `test_pagination_structure_and_clamp`、`test_activities_sorted_by_created_at_desc`、`test_winners_and_registrations_ordering`、`test_checkins_sorted_by_time_asc`、`test_keyword_truncated_to_50_chars`、`test_my_registrations_pagination` | `{items,total,page,size,pages}`、`size>50` 截断、`page<1` 归 1、四类默认排序、keyword 截断 | ✅ |

**结论：§10.1 列出的 18 类用例条目全部有对应实现并通过**，附录 D 的「需求 ↔ 模块 ↔ 测试」映射中 P0 项无遗漏（FR-1~FR-7 均有测试文件）。

## 3. 超出 §10.1 的补充用例

| 用例 | 目的 |
| --- | --- |
| `test_data_integrity.py::test_unique_activity_user_blocks_duplicate_rows` | 直接绕过 API 写库，证明 `UNIQUE(activity_id,user_id)` 是并发下的最终防线（§4.5） |
| `test_data_integrity.py::test_checkin_unique_registration_blocks_double_row` | 同上，`checkins.registration_id UNIQUE` 拦截重复签到 |
| `test_data_integrity.py::test_lottery_is_reproducible_from_seed` | 用 `lottery_seed` 重放 `random.Random(seed).shuffle` 得到与库中 `lottery_rank` 完全一致的顺序（§4.3 审计复现） |
| `test_data_integrity.py::test_lottery_1000_registrations_under_one_second` | §10.2 性能验收（详见 §4） |
| `test_scheduler.py`（5 例） | I-1 扫描到期、幂等、单活动异常不断批、配置可关闭、interval job 参数（`max_instances=1/coalesce`） |
| `test_activity.py::test_edit_guard_blocks_after_lottery` 等 5 例 | §7.2 状态边界矩阵（抽签后禁编辑、真实截止后禁编辑、可提前截止、S10 名额改小、DRAFT 对学生不可见） |
| `test_auth.py::test_disabled_user_blocked_on_login_and_request` | §2.11 禁用即时生效（每请求查库） |
| `test_admin.py::test_admin_cannot_be_created_via_register` | FR-1.2 ADMIN 不开放注册 |
| `test_registration.py::test_cancel_rules_by_status` | §2.5-4 取消 / 退出语义分流 |

## 4. §10.2 性能与并发验收

| 项目 | 要求 | 实测 | 结论 |
| --- | --- | --- | --- |
| 1000 条报名单次抽签 | < 1s（`time` 打点） | **48.0 ms**（quota 100；won=100，waiting 448 + lost 452）；另有 pytest 用例 `test_lottery_1000_registrations_under_one_second` 常驻断言 | ✅ |
| 100 并发报名无重复 | `COUNT(DISTINCT (activity_id,user_id))` 与总行数一致 | 100 个不同学生并发报名：**HTTP 200 全部 100 条**，报名总数 100、去重用户 100、重复组 0 | ✅ |
| 同人并发双击报名 | 恰一条成功，其余 40901（§7.2 并发边界） | 对已报名学生再发 20 路并发：全部 409（40901），该生库中仍只有 1 条记录 | ✅（详见 §6 说明） |
| 调度 + 兜底并发 | 条件 UPDATE 只让一方生成名单 | `test_scheduler.py::test_scan_is_idempotent`、`test_lottery_idempotent` 覆盖；返回 `concurrent_or_done/already_done` | ✅ |

性能数据备注：抽签成本主要是 1000 次 `UPDATE registrations`（按对象赋值后一次 commit）。文档 §5.2 提到的「按 status 分组批量 UPDATE」替代方案未采用，因为 48 ms 已远低于 1s 阈值，保留逐对象写法以便 `lottery_rank/qr_token` 逐行赋值。

100 并发验收使用一次性脚本（`ThreadPoolExecutor(100)` + `TestClient`，独立临时 SQLite 文件，不触碰演示库 `app.db`），验收后已删除；脚本要点：预建 1 活动 + 100 学生、token 由 `create_access_token` 直签（排除登录耗时）、并发 POST `/api/activities/{id}/registrations`、结束后按 `(activity_id,user_id)` 分组 `HAVING count>1` 校验。

## 5. 测试基础设施说明

- `tests/conftest.py`：环境变量在 **import app 之前**设置（否则 `engine` 会连到真实 `app.db`）；`client` fixture 刻意不使用 `with`，跳过 lifespan（不建表、不启调度器）。
- `tests/helpers.py`：`register/login/make_user/create_activity/create_students/signup_many/close_signup/run_lottery/admin_session/user_id/offset/iso` 等，统一「组织者提前把 deadline 改到过去」的动作，避免真实等待。
- 断言风格：一律断言 `response.json()["code"]` 与中文 `message` 片段，而非仅状态码；抽签分布类断言避免依赖随机结果（如只断言 `waiting + lost == 10`）。

## 6. 开发期缺陷闭环记录（全部已修复）

| # | 现象 | 根因 | 修复 | 防回归 |
| --- | --- | --- | --- | --- |
| 1 | `/stats` 抛 `KeyError: 'PENDING'` | `str(ActivityStatus.DRAFT)` 返回 `"ActivityStatus.DRAFT"` 而非 `"DRAFT"`，污染所有按状态聚合/比较的逻辑 | 新增 `_StrEnum` 基类覆写 `__str__`，枚举列加 `values_callable` | `test_data_integrity.py` 断言 `str(row.status) == "LOTTERY_DONE"`；全量状态相关用例 |
| 2 | 退出中签者后 `promoted=0`（I-3 失效） | 会话 `autoflush=False` 使刚置的 WITHDRAWN 未落盘，`promote_waitlist` 读到过期 WON 计数 | 恢复默认 autoflush，并在 `promote_waitlist` 首行显式 `db.flush()` | `test_waitlist_promotion_on_withdraw` 断言 `promoted=1` |
| 3 | `/winners`、`/checkins` 500 | `UserBrief` 继承 `BaseModel` 而非 `ORMModel`，缺 `from_attributes` 无法从 ORM 行序列化 | 改继承 `ORMModel` | `test_winners_and_registrations_ordering`、`test_checkins_sorted_by_time_asc` |
| 4 | 重复签到响应 `TypeError: Object of type datetime is not JSON serializable` | `BizError.data` 里放了 naive `datetime` | 统一 `iso_z()` 转 ISO 字符串 | `test_checkin_duplicate_returns_first_time` |
| 5 | 详情接口 `ValidationError: my_registration Field required` | `ActivityDetailOut` 附加字段无默认值 | 给 `my_registration/registered_count/lottery_status_cn` 默认值 | `test_detail_contains_my_registration_and_count` |
| 6 | 启动 `KeyError: unknown CryptContext keyword 'bcrypt_rounds'` | passlib 1.7.4 的参数名是 `bcrypt__rounds` | 改正并抽出 `BCRYPT_ROUNDS` 环境变量 | 手工 `seed.py` + `test_auth` 全链路 |
| 7 | 抽签边界：截止瞬间可报名/不可抽签判定不一致 | 误用 `deadline >= now` | 按 S4 改为 `utcnow() < as_utc(deadline)` | `test_register_after_deadline_rejected`、`test_lottery_before_deadline_rejected` |
| 8 | 报名名单接口 N+1 查询 | 循环内访问 `registration.user`/`checkin` | `joinedload` 预加载 + `.unique()` | `test_winners_and_registrations_ordering`（含签到时间填充） |
| 9 | 校验错误返回 422 | FastAPI 默认 `RequestValidationError` 处理 | 处理器改写为 400/40001 + 中文 message | `test_create_activity_validation`、`test_register_validation` |
| 10 | 测试自身误报 4 处 | ① 以为 WITHDRAWN 不在我的报名列表 ② 以为递补后取消返回 CANCELLED（实际 WON→WITHDRAWN） ③ 断言 `waiting==10`（随机分配） ④ S10 分支无法仅通过 API 到达 | 修正断言与造数方式（用例内直改活动状态/截止时间） | 现全部通过；说明「代码正确、断言错误」的判别过程 |

## 6b. 手工验收期发现并修复的缺陷

这些缺陷由浏览器实测（见 `acceptance-report.md`）暴露，自动化用例当时未覆盖：

| # | 现象 | 根因 | 修复 | 回归防护 |
| --- | --- | --- | --- | --- |
| 11 | `/my_registrations.html` 打开即被空的「签到二维码」遮罩盖住，整页按钮不可点（阻断） | `.modal-mask{display:flex}` 优先级高于 `hidden` 属性，样式表无 `[hidden]{display:none}` | `static/css/style.css` 增加 `[hidden]{display:none !important}` | A6 复测 |
| 12 | 导出文件名是 `activity_1_all.xlsx`，丢失后端给的中文文件名 | `api.js download()` 忽略 `Content-Disposition`，页面硬编码兜底名 | 解析 `filename*=UTF-8''` 并挂到 `blob.name`，下载时优先使用 | A9 复测；后端头由 `test_export_excel` 保证 |
| 13 | 重复签到提示「已于 10:42 签到」，同页前端显示 18:42（差 8 小时） | SQLite 读回的 `checked_in_at` 是 naive 值，`astimezone()` 把 UTC 墙上时间当成本地时间（R3 的具体表现） | `as_utc()` 先按 UTC 还原再转本地时区 | `test_checkin_duplicate_returns_first_time` 增加断言：提示中的 `HH:mm` 必须等于首次时间的本地时区值 |
| 14 | 导出文件名日期使用 naive `datetime.now()` | 违反 §5.9/R3「全项目唯一时间入口 `utcnow()`」 | 改为 `utcnow().astimezone():%Y%m%d`（仍是本地日期标签，但来源显式） | `test_export_excel` 文件名断言 |
| 15 | 组织者无任何活动编辑入口，`PATCH /api/activities/{id}` 在 UI 上无法触达（FR-2.3、I-4 名额调大递补因此不可演示） | 前端漏做表单（仅 admin.html 用了 PATCH） | `activity_manage.html` 增加「编辑活动」表单（含名额调大提示、改小/截止提前的二次确认，R11） | A3/A5 复测 |
| 16 | 中签/候补、签到名单 Tab 保留 `/registrations?status=WON` 兜底死代码与「后端会 500」的过时注释 | 早期接口确有 `UserBrief` 500（缺陷 3），修复后兜底永不触发 | 删除兜底分支，统一直接调用 §3.3 的 `/winners`、`/checkins` | A8 复测；同时消除「超过 50 人只显示 50」的隐患（兜底按 size=50 翻页） |
| 17 | 活动详情「活动状态」一行出现两次相同中文（徽章 + `lottery_status_cn`） | 前端重复渲染同一映射 | 该行改为状态补充说明：报名中提示「截止后 30 秒内自动抽签」（R11 要求）、已抽签显示抽签时间 | A4 复测 |
| 18 | 直接把 `.env.example` 的示例 `SECRET_KEY` 复制到 `.env` 也能启动（R9 校验存在漏网的示例值） | `EXAMPLE_SECRET_KEYS` 未包含模板里的 `change-me-to-a-random-64-hex-string` | 补入该值 | 启动即 `RuntimeError`，手工验证 |

另有一条**未修复但已确认不影响验收**的观察：`checkin.html` 的摄像头扫码依赖 `BarcodeDetector` + `getUserMedia`，在非 `localhost` 的 HTTP 局域网地址下浏览器会拒绝（安全上下文限制）；本项目的局域网签到路径是「学生手机出示二维码 → 组织者手工输入/粘贴码」，功能不受影响。已记入 `acceptance-report.md` 的建议项。


## 7. 未覆盖项与后续建议

| 项 | 现状 | 建议 |
| --- | --- | --- |
| 前端 UI 自动化 | 仅手工 + 浏览器人工验证，无 Selenium/Playwright 用例 | MVP 明确不引入（文档 §10 只要求后端 pytest）；后续可对 A1~A12 关键路径补 E2E |
| 100 并发报名 | 以一次性脚本验收，未常驻测试 | 若纳入 CI，需改独立临时库 + 降 bcrypt rounds，避免拖慢 |
| MySQL 回归 | 未执行（环境无 MySQL 实例） | R7 要求「迁移时跑全量 pytest」，切库后按 §5 环境改动 `DATABASE_URL` 直接重跑即可 |
| 摄像头真实扫码 | 依赖 `BarcodeDetector`，未做真机验证 | 人工验收项，见 A8 |
| 大导出内存（R8） | 千行级已验证（5.7 KB xlsx / 10 行） | 万级需改分批写入 |
