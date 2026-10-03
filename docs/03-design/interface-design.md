> **所属阶段**：系统设计（接口）　|　**版本**：v1.0　|　**整理日期**：2026-10-02
> **性质**：实现完成后的对外接口契约（含入参、出参与错误码），与《详细设计说明书》§3 接口定义配套。

# 校园活动报名抽签与签到系统 —— 接口设计说明书

> 文档性质：**开发完成后产出**的对外接口契约清单，由 `app/main.py` 注册的实际路由与运行中的 `openapi.json` 核对生成（共 24 个业务接口 + 健康检查）。
> 与开发文档 §3 的差异统一记录在 §7「与设计文档的差异」。
> 在线文档：`/api/docs`（Swagger UI）、`/api/openapi.json`、`/redoc`。

## 1. 全局约定

| 项 | 约定 |
| --- | --- |
| 前缀 | 全部业务接口以 `/api` 开头；静态页面挂根路径（`/login.html` 等） |
| 响应体 | `{"code": 0, "message": "ok", "data": {...}}`；失败时 `code≠0`、`message` 为中文提示、HTTP 状态码语义化 |
| 例外 | 二维码接口返回 `image/png`（`Cache-Control: no-store`）；导出接口返回 xlsx 字节流 |
| 鉴权 | 除 `/api/auth/register`、`/api/auth/login`、`/api/health` 外均需 `Authorization: Bearer <token>`；失效/缺失 → 401/40101；账号被禁用 → 401/40101（每请求查库，禁用即时生效） |
| 时间 | 出入参一律 ISO 8601 UTC（`2026-10-01T10:34:23Z`）；空值输出 `null`；解析失败 → 40001 |
| 分页请求 | `page`（默认 1，<1 归 1）、`size`（默认 10，>50 截断为 50） |
| 分页响应 | `data = {items, total, page, size, pages}` |
| 默认排序 | 活动列表 `created_at desc`；报名名单 `id asc`；中签名单/候补队列 `lottery_rank asc`；我的报名 `created_at desc`；签到名单 `checked_in_at asc` |
| 权限标记 | 「组织者本人」= `require_role(ORGANIZER, ADMIN)` + `assert_activity_owner`；「学生」= `require_role(STUDENT)` |

**错误码总表（附录 B）**

| code | HTTP | 典型场景 |
| --- | --- | --- |
| 0 | 200 | 成功 |
| 40001 | 400 | 参数错误、报名已截止、状态不允许、名额改小越界 |
| 40101 | 401 | 未登录 / token 失效 / 账号被禁用 |
| 40102 | 401 | 用户名或密码错误（不区分具体原因） |
| 40301 | 403 | 越权（角色不符、非活动归属人、查看他人二维码、DRAFT 详情） |
| 40401 | 404 | 资源不存在 / 签到码无效 |
| 40901 | 409 | 重复报名 / 重复签到 / 用户名已存在 |
| 50001 | 500 | 服务器内部错误（`logger.exception` 记录堆栈） |

> Pydantic 校验失败按 §7.1 统一改写为 **400 / 40001**（不是 FastAPI 默认的 422），message 形如 `quota：取值过小`。

## 2. 认证（M1）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/auth/register` | 公开 | 注册 STUDENT/ORGANIZER；ADMIN 不可由此创建 |
| POST | `/api/auth/login` | 公开 | 返回 token 与用户摘要 |
| GET | `/api/auth/me` | 登录 | 当前用户完整信息 |

**POST /api/auth/register**

```json
{"username":"2023001","password":"123456","real_name":"张三",
 "role":"STUDENT","email":null,"phone":null}
```

`username`：4~50 位，`^[A-Za-z0-9_]+$`；`password`：6~64 位；`real_name`：1~50 位；`role` ∈ `STUDENT|ORGANIZER`。
`data` = `{id, username, real_name, role, email, phone, is_active, created_at}`。
错误：用户名重复 40901「用户名已存在」；格式非法 40001。

**POST /api/auth/login** → `data`：

```json
{"access_token":"eyJ…","token_type":"bearer","expires_in":86400,
 "user":{"id":1,"username":"2023001","real_name":"张三","role":"STUDENT"}}
```

错误：账密不符 40102（同一文案，防枚举）；被禁用 40101「账号已被禁用」。

JWT payload（S1）：`{"sub":"<用户id字符串>","role":"STUDENT","iat":…,"exp":…}`，HS256，密钥 `SECRET_KEY`，有效期 `ACCESS_TOKEN_EXPIRE_MINUTES`（默认 1440）。

## 3. 活动（M2）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/activities` | 组织者/管理员 | 创建（默认 `DRAFT`，传 `status=PUBLISHED` 一步发布） |
| GET | `/api/activities` | 登录 | 列表：`status`/`keyword`/`mine`/`page`/`size` |
| GET | `/api/activities/{activity_id}` | 登录 | 详情 + `my_registration` + `registered_count`；**含 I-2 到期兜底抽签** |
| PATCH | `/api/activities/{activity_id}` | 组织者本人 | 编辑可变字段；quota 调大同事务递补（I-4） |
| POST | `/api/activities/{activity_id}/publish` | 组织者本人 | `DRAFT → PUBLISHED` |
| POST | `/api/activities/{activity_id}/cancel` | 组织者本人 | `→ CANCELLED` |
| POST | `/api/activities/{activity_id}/lottery` | 组织者本人 | 手动抽签；query `force`（仅 ADMIN 生效） |
| GET | `/api/activities/{activity_id}/registrations` | 组织者本人 | 报名名单，`status` 过滤 + 分页 |
| GET | `/api/activities/{activity_id}/winners` | 组织者本人 | `{winners:[…], waitlist:[…]}`，均按 `lottery_rank asc` |
| GET | `/api/activities/{activity_id}/checkins` | 组织者本人 | `{checked_in:[…], not_checked_in:[…]}` |
| GET | `/api/activities/{activity_id}/stats` | 组织者本人 | 六计数 + 三比率 + `lottery_at` |
| GET | `/api/activities/{activity_id}/export` | 组织者本人 | `type=all\|winners`，返回 xlsx 流 |

**POST /api/activities** 请求：

```json
{"title":"AI 前沿讲座","description":"特邀教授主讲","location":"图书馆报告厅",
 "start_time":"2026-11-01T10:00:00Z","end_time":"2026-11-01T12:00:00Z",
 "signup_deadline":"2026-10-30T23:59:00Z","quota":10,"status":"PUBLISHED"}
```

校验（→40001）：`quota < 1`（Pydantic `ge=1` 拦截）、`signup_deadline > start_time`（「报名截止时间不能晚于活动开始时间」）、`signup_deadline <= now` 仅在 **DRAFT** 创建/编辑时拒绝（「报名截止时间必须晚于当前时间」）；直接创建为 `PUBLISHED` 时允许截止时刻已过（§7.2「发布态除外」，用于补录场景，随后由兜底/调度立即抽签）。
`data` = ActivityOut：`{id, organizer_id, title, description, location, start_time, end_time, signup_deadline, quota, status, lottery_at, created_at}`。

**GET /api/activities** 参数语义：学生视角 `status` 仅允许 `PUBLISHED|LOTTERY_DONE`，缺省即二者；组织者/管理员可用任意 `status` 或 `mine=true` 看自己全部状态；`keyword` 对 `title/location` 参数化 LIKE，最长 50 字符（超出截断）。

**GET /api/activities/{id}** `data` = ActivityOut + 

```json
{"my_registration":{"id":41,"status":"WAITING","lottery_rank":12,"qr_available":false,
  "accept_waitlist":true,"checked_in":false},
 "registered_count":20,"lottery_status_cn":"已抽签"}
```

未报名 `my_registration = null`；`qr_available` 表示当前能否出签到码（WON 且有 token）；`registered_count` 为有效报名数（不含 CANCELLED）。DRAFT 活动对非归属者 40301。

**PATCH /api/activities/{id}**：body 字段全部可选（Partial，`exclude_unset`），空 body → 40001「没有需要修改的字段」。守卫：`LOTTERY_DONE/CANCELLED` 拒绝编辑（40001）；`PUBLISHED` 且已过截止时间不可再编辑（要提前截止请在截止前操作）；新 `quota < 当前 WON 数` → 40001（S10）。quota 调大成功时响应额外返回 `promoted`（本次递补人数）。

**POST /api/activities/{id}/lottery** `data`（五键恒定）：

```json
{"executed":true,"reason":null,"won":10,"waiting":7,"lost":3}
{"executed":false,"reason":"already_done","won":10,"waiting":7,"lost":3}
{"executed":false,"reason":"concurrent_or_done","won":10,"waiting":7,"lost":3}
```

未截止且非 force → 40001「报名尚未截止，不能抽签」；`force=true` 仅 ADMIN 生效（组织者传该参数被忽略）。

**GET …/winners** 行结构（`test_pagination` 校验排序）：

```json
{"registration_id":44,"user":{"id":6,"username":"stu004","real_name":"学生004"},
 "lottery_rank":1,"checked_in":false}
```

**GET …/checkins** 行结构：`{registration_id, user{…}, lottery_rank, checked_in_at, method}`，`checked_in_at` 未签到为 `null`，`method ∈ SCAN|MANUAL`。

**GET …/stats** 实测响应：

```json
{"activity_id":3,"quota":10,"registered":20,"pending":0,"won":10,"waiting":7,
 "lost":3,"withdrawn":0,"cancelled":0,"checked_in":0,
 "win_rate":0.5,"checkin_rate":0.0,"quota_usage":1.0,"lottery_at":"2026-10-01T10:36:30Z"}
```

比率保留 4 位小数；分母为 0 时比率记 0（`registered=0`、`won=0`）。

**GET …/export**：`type` 缺省 `all`，非法值 40001。响应头实测：

```
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename=export.xlsx;
  filename*=UTF-8''%E6%91%84%E5%BD%B1%E9%87%87%E9%A3%8E%E6%B4%BB%E5%8A%A8_%E4%B8%AD%E7%AD%BE%E8%A1%A8_20261001.xlsx
Cache-Control: no-store
```

即「摄影采风活动_中签表_20261001.xlsx」。列定义见 §5.8：报名表（序号/学号工号/姓名/报名时间/接受候补/状态/抽签序号/签到状态/签到时间）、中签表（序号/学号工号/姓名/抽签序号/签到码/签到状态/签到时间），状态列为中文。

## 4. 报名与二维码（M3）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/activities/{activity_id}/registrations` | 学生 | body `{"accept_waitlist": true}`（缺省 true） |
| DELETE | `/api/activities/{activity_id}/registrations/me` | 学生 | 取消 / 退出，语义按状态分流 |
| GET | `/api/me/registrations` | 学生 | 我的报名（分页，`created_at desc`，不含 CANCELLED） |
| GET | `/api/registrations/{registration_id}/qrcode` | 本人 / 该活动组织者 / ADMIN | PNG 流，`no-store` |

报名错误：重复报名 40901、已截止或状态不允许 40001、非学生 40301、活动不存在 40401。
`data` = RegistrationOut：`{id, activity_id, user_id, username, real_name, status, accept_waitlist, lottery_rank, checked_in_at, created_at}`。

取消 / 退出规则（§2.5-4）：`PENDING/WAITING/LOST → CANCELLED`；`WON → WITHDRAWN`，同时清空 `qr_token`（旧码立即失效）并**同事务递补**。响应：

```json
{"status":"WITHDRAWN","promoted":1}
```

`promoted` 仅在退出中签者时有意义（无候补时为 0，名额保持空缺，FR-5.5）。

我的报名行：`{activity{ id,title,location,start_time,signup_deadline,status,lottery_at }, registration_id, status, lottery_rank, accept_waitlist, qr_available, checked_in_at, created_at}`。

二维码：内容 `{PUBLIC_BASE_URL}/checkin.html?code=<qr_token>`；仅 `status=WON` 且 `qr_token` 非空可出码，否则 40001；越权 40301；报名记录不存在 40401。

## 5. 签到（M6）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/activities/{activity_id}/checkin` | 组织者本人 | body `{"code":"…"}`，支持裸 token 或完整 URL |
| POST | `/api/activities/{activity_id}/checkin/manual` | 组织者本人 | body `{"username":"stu001"}`，`method=MANUAL` |

成功响应：

```json
{"code":0,"message":"ok","data":{"user_name":"张三","username":"2023001",
 "checked_in_at":"2026-10-01T10:40:11Z","registration_id":41,"method":"SCAN"}}
```

校验链与失败码：空码 40001「签到码不能为空」→ 码不存在 40401「签到码无效」→ 跨活动/活动已取消 40001 → 非 WON 状态 40001「该同学当前不是中签状态」→ 已签到 40901，`message`=「该同学已于 18:40 签到」且 `data.checked_in_at` 为首次时间。手动补签查不到该活动下的 WON 报名时 40001。

## 6. 管理员（M9）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/admin/users` | ADMIN | `keyword`（用户名/姓名）+ `role` 过滤 + 分页 |
| PATCH | `/api/admin/users/{user_id}` | ADMIN | body `{"role":"ORGANIZER"}` 或 `{"is_active":0}` 或两者（`exclude_unset` 局部更新） |

规则：不可把 ADMIN 降级/改角色（40001）；不可禁用/降级自己；被禁用用户的旧 token 下一次请求即 40101。学生访问管理接口 40301。

## 7. 与健康检查、与设计文档的差异

| 项 | 设计文档 | 实际实现 | 原因 |
| --- | --- | --- | --- |
| `GET /api/health` | §1.2 M1 里程碑提到「健康检查」 | 已实现，返回 `{app,status}` | 部署与验收自检用 |
| Swagger 路径 | 未指定 | `/api/docs`、`/api/openapi.json`（`/redoc` 默认） | 避免与静态站点 `/` 挂载冲突 |
| 详情 `lottery_status_cn` | 未定义 | 新增只读字段 | 前端中文状态标签（附录 A） |
| 统计 `cancelled` | §5.7 六计数 | 额外返回 `cancelled` | 名单人数核对更方便；原字段含义未变 |
| 抽签响应 `reason` | 仅未执行时出现 | 成功时也存在（值为 `null`） | 前端免判空 |
| 校验错误码 | §7.1 要求 400/40001 | 已从默认 422 改写为 400/40001 | 与统一响应体一致 |
| 签到响应字段 | §3.5 三字段 | 额外 `registration_id`、`method` | 签到台需要区分扫码/补签并支持撤销排查 |
| `GET …/checkins` 的 `not_checked_in` | 未指定排序 | 按报名 id 升序（等价报名时间先后） | 便于现场按名单顺序点名 |
