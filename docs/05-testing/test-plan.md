# 校园活动报名抽签与签到系统 —— 测试计划

> **所属阶段**：测试验证（计划）　|　**版本**：v1.0　|　**整理日期**：2026-10-02
> **内容来源**：《开发文档》§10 测试与验收要求、附录 D；《需求与设计文档》§12.1、§12.3
> **编号说明**：本文章节编号沿用来源文档，以便与《开发文档》《需求与设计文档》交叉检索。

---
## 10. 测试与验收要求

### 10.1 自动化测试（pytest + TestClient + 内存 SQLite）

用例清单与断言要求（`tests/`，conftest 提供 `client` 与 `db` fixture）：

| 用例 | 覆盖 | 断言要点 |
| --- | --- | --- |
| test_register_login | FR-1.1~1.5 | 注册成功；重复 409；错密 401（统一文案）；token 访问 /me |
| test_role_guard | FR-2.8 | 学生建活动 403；org2 摸 org1 资源 403（含 qrcode/checkin/export） |
| test_create_activity_validation | FR-2.2 | deadline≤now 400；quota=0 422/400；deadline>start 400 |
| test_register_activity | FR-3.1~3.4 | 成功；重复 409；截止后 400；取消后重报成功且复用记录 |
| test_lottery_basic | FR-4.4/4.5 | 20 报名/10 名额 → 10 WON + 10 WAITING/LOST；≤名额全 WON |
| test_lottery_randomness | FR-4.5/4.6 | 多轮中签集合不同；lottery_rank 同活动唯一不重复 |
| test_lottery_idempotent | FR-4.3 | 二次调用 executed=False，名单与 rank 不变 |
| test_lottery_before_deadline | FR-4.9 | 未截止 400；ADMIN force=true 可执行 |
| test_accept_waitlist_false | FR-4.5 | 不接受候补 → LOST，不进队列 |
| test_waitlist_promotion | FR-5.1~5.4/5.7 | 退出后 rank 最小候补变 WON、获新 qr_token、旧码失效、my 接口可见 |
| test_promotion_empty_waitlist | FR-5.5 | 无候补退出不报错、名额空缺 |
| test_quota_increase_promotion | FR-5.6 | quota 10→12 补 2 人 |
| test_qrcode_permission | FR-6.1 | 他人 403；非 WON 400；no-store 头 |
| test_checkin_* | FR-6.3~6.5 | 成功/重复 409+首时/跨活动 400/伪码 404/整 URL 解析 |
| test_manual_checkin | FR-6.7 | 按学号补签 method=MANUAL |
| test_stats | FR-7.1/7.2 | 六计数 + 三比率精确到 4 位 |
| test_export_excel | FR-7.3~7.6 | 两表列头/行数/冻结首行/中文名可读 |
| test_pagination | S2/S3 | size 上限截断、排序方向 |

### 10.2 手工验收（A1–A12）与性能验收

按需求文档 §12.2 清单逐项执行（发布 3 活动 → 20 人报名 → 抽签 → 递补 → 签到 → 导出 → 权限隔离 → 换机部署）；性能验收：1000 条报名抽签 < 1s（`time` 打点）；100 并发（httpx/locust）报名后 `COUNT(DISTINCT (activity_id,user_id))` 无重复。

## 12.1 自动化测试用例（pytest + TestClient + 内存 SQLite）
| 用例 | 覆盖需求 | 断言 |
|---|---|---|
| `test_register_login` | FR-1.1~1.4 | 注册成功、重复用户名 409、错误密码 401、token 可访问 /me |
| `test_role_guard` | FR-2.8 | 学生创建活动 403；组织者操作他人活动 403 |
| `test_create_activity_validation` | FR-2.2 | 截止时间早于当前 400；quota=0 400 |
| `test_register_activity` | FR-3.1~3.4 | 报名成功；重复报名 409；截止后报名 400；取消后可重报 |
| `test_lottery_basic` | FR-4.4 | 20 人报名、名额 10：10 个 WON + 10 个候补/未中；报名 ≤ 名额时全部 WON |
| `test_lottery_randomness` | FR-4.5/4.6 | 多次造数据，中签集合不完全一致；`lottery_rank` 唯一；中签者不重复 |
| `test_lottery_idempotent` | FR-4.3 | 连续调用两次，第二次返回 `executed=False`，名单不变 |
| `test_lottery_before_deadline` | FR-4.9 | 未截止触发返回 400 |
| `test_accept_waitlist_false` | FR-4.5 | 不接受候补者状态为 LOST，不进候补队列 |
| `test_waitlist_promotion` | FR-5.1~5.4 | 中签者退出后，候补 rank 最小者变 WON 且拿到新 qr_token |
| `test_promotion_empty_waitlist` | FR-5.5 | 无候补时退出不报错，名额空缺 |
| `test_qrcode_permission` | FR-6.1 | 他人二维码 403；非中签者 400 |
| `test_checkin_success` | FR-6.3~6.4 | 正确 code 签到成功，签到记录生成 |
| `test_checkin_duplicate` | FR-6.5 | 二次签到 409 |
| `test_checkin_wrong_activity` | FR-6.4 | 跨活动 code 400 |
| `test_checkin_invalid_code` | FR-6.4 | 伪造 code 404 |
| `test_stats` | FR-7.1/7.2 | 各计数与比率计算正确 |
| `test_export_excel` | FR-7.3/7.4 | 返回 xlsx，openpyxl 可读取，行数 = 报名数，列头正确 |

## 12.3 性能验收
- 1000 条报名数据下单次抽签耗时 < 1s（`time` 打点验证）；
- 100 并发报名（`httpx` 或 `locust`）后 `SELECT COUNT(*)` 无重复 `(activity_id, user_id)`。
---

## 附录 D　需求 ↔ 模块 ↔ 测试映射（P0 全覆盖核对表）

| 需求组 | 模块 | 测试文件 |
| --- | --- | --- |
| FR-1 认证 | M1 | test_auth.py |
| FR-2 活动 | M2 | test_role_guard / test_create_activity_validation |
| FR-3 报名 | M3 | test_registration.py |
| FR-4 抽签 | M4/M8 | test_lottery*.py |
| FR-5 递补 | M5 | test_waitlist.py |
| FR-6 签到 | M6 | test_checkin*.py |
| FR-7 统计导出 | M7 | test_stats / test_export_excel |

（文档完）
