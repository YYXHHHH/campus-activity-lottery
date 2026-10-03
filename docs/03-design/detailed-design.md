# 校园活动报名抽签与签到系统 —— 详细设计说明书（DLD）

> **所属阶段**：系统设计（详细）　|　**版本**：v1.0　|　**整理日期**：2026-10-02
> **内容来源**：《开发文档》§3 接口定义、§5 关键技术实现方案、§6 模块间依赖与集成点、§7 边界条件与异常处理策略、附录 A/B
> **编号说明**：本文章节编号沿用来源文档，以便与《开发文档》《需求与设计文档》交叉检索。

---
## 3. 接口定义

### 3.1 全局约定

1. **前缀与格式**：统一前缀 `/api`；请求/响应均为 JSON（UTF-8），二维码接口与导出接口除外（PNG / xlsx 字节流）。
2. **统一响应体**：`{"code": 0, "message": "ok", "data": {...}}`；`code` 非 0 时 `message` 为中文提示，HTTP 状态码语义化（400/401/403/404/409）。错误码总表见附录 B。
3. **鉴权**：除注册/登录外全部需要 `Authorization: Bearer <token>`；token 失效或缺失返回 `40101`（HTTP 401）。
4. **时间**：出入参一律 ISO 8601 UTC 字符串（如 `2025-06-01T10:00:00Z`）；解析失败按参数错误 40001。空时间字段输出 `null`。
5. **分页请求**：`page`（1 起，默认 1）、`size`（默认 10，上限 50，越界截断）。
6. **分页响应**（S2）：`data = {"items": [...], "total": 总条数, "page": 当前页, "size": 每页条数, "pages": 总页数}`。
7. **默认排序**（S3）：活动列表 `created_at desc`；报名名单 `id asc`；中签名单 `lottery_rank asc`；候补队列 `lottery_rank asc`；我的报名 `created_at desc`；签到名单 `checked_in_at asc`。
8. **权限写法**：表格中"组织者本人"= `require_role(ORGANIZER, ADMIN)` + `assert_activity_owner`；"学生"= `require_role(STUDENT)`。

### 3.2 认证接口

**POST /api/auth/register**（公开）

请求：

```json
{
  "username": "2023001",
  "password": "123456",
  "real_name": "张三",
  "role": "STUDENT",
  "email": null,
  "phone": null
}
```

响应 200：`data` = 用户信息（id/username/real_name/role/email/phone/created_at）。
错误：用户名重复 40901；格式非法/role 非法 40001。

**POST /api/auth/login**（公开）

请求：`{"username": "...", "password": "..."}`

响应 200：

```json
{
  "code": 0,
  "data": {
    "access_token": "eyJ...",
    "token_type": "bearer",
    "expires_in": 86400,
    "user": { "id": 1, "username": "2023001", "real_name": "张三", "role": "STUDENT" }
  }
}
```

错误：用户名或密码错误 40102；账号被禁用 40101。

**GET /api/auth/me**（登录）：返回当前用户完整信息（同注册响应结构）。

### 3.3 活动接口

**POST /api/activities**（组织者/管理员）：创建活动。

请求（`status` 可选，默认 `DRAFT`；传 `PUBLISHED` 即创建并发布）：

```json
{
  "title": "AI 前沿讲座",
  "description": "特邀教授主讲",
  "location": "图书馆报告厅",
  "start_time": "2025-06-01T10:00:00Z",
  "end_time": "2025-06-01T12:00:00Z",
  "signup_deadline": "2025-05-30T23:59:00Z",
  "quota": 10,
  "status": "PUBLISHED"
}
```

响应 200：`data` = ActivityOut（含 `id`、`status`、`organizer_id`、`created_at` 等）。
错误：`quota < 1`、`signup_deadline <= now`、`signup_deadline > start_time` 均 40001。

**GET /api/activities**（登录）：活动列表。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `status` | str? | 学生视角仅允许 `PUBLISHED`/`LOTTERY_DONE`，缺省时默认二者；组织者/管理员传任意状态或用 `mine` |
| `keyword` | str? | 对 `title`/`location` 做 LIKE `%kw%`（参数化拼接） |
| `page` / `size` | int | 分页 |
| `mine` | bool? | `true` 时仅返回当前用户创建的活动（任意状态），组织者/管理员专用 |

响应 200：分页结构，`items[]` = ActivityOut。

**GET /api/activities/{id}**（登录）：活动详情。`data` = ActivityOut + `my_registration`（当前用户在该活动的报名摘要：status/lottery_rank/qr 可用性；未报名为 `null`）+ `registered_count`。
**兜底逻辑（集成点 I-2）**：若查询时发现 `status=PUBLISHED && now >= signup_deadline`，先同步调用一次 `run_lottery`（幂等）再返回。

**PATCH /api/activities/{id}**（组织者本人）：编辑，body 为可变字段的 Partial（title/description/location/start_time/end_time/signup_deadline/quota）。校验见 §2.4；quota 调大时同事务调用 `promote_waitlist`（集成点 I-4）。

**POST /api/activities/{id}/publish**（组织者本人）：`DRAFT → PUBLISHED`。

**POST /api/activities/{id}/cancel**（组织者本人）：`→ CANCELLED`。

**POST /api/activities/{id}/lottery**（组织者本人）：手动抽签。query：`force`（bool，仅 ADMIN 生效，用于调试）。响应：`{"executed": bool, "reason": "already_done|concurrent_or_done", "won": n, "waiting": n, "lost": n}`。未截止且非 force 返回 40001。

**GET /api/activities/{id}/registrations**（组织者本人）：报名名单。query：`status`（可选过滤）、`page`/`size`。`items[]` = RegistrationOut。

**GET /api/activities/{id}/winners**（组织者本人）：`data = {"winners": [...], "waitlist": [...]}`，均含用户信息与 `lottery_rank`，按 §3.1-7 排序。

**GET /api/activities/{id}/checkins**（组织者本人）：`data = {"checked_in": [...], "not_checked_in": [...]}`（各含用户信息与签到时间，后者为 `null`）。

**GET /api/activities/{id}/stats**（组织者本人）：统计，结构见 §5.7。

**GET /api/activities/{id}/export?type=all|winners**（组织者本人）：返回 xlsx 文件流，见 §5.8。

### 3.4 报名接口

**POST /api/activities/{id}/registrations**（学生）：body `{"accept_waitlist": true}`。成功返回 RegistrationOut；错误：重复报名 40901、已截止/状态不允许 40001、非学生 40301、活动不存在 40401。

**DELETE /api/activities/{id}/registrations/me**（学生）：取消/退出（语义分流见 §2.5-4）。响应 200：`{"status": "新状态", "promoted": n}`（`promoted` 仅退出中签时有值，表示本次递补人数）。

**GET /api/me/registrations**（学生）：我的报名列表（分页），`items[]` = MyRegistrationOut（活动摘要 + 状态 + lottery_rank + 签到状态 + `qr_available` 布尔）。

**GET /api/registrations/{id}/qrcode**（本人学生 / 该活动组织者 / ADMIN）：返回 `image/png` 字节流，`Cache-Control: no-store`。错误：报名不存在 40401、非中签或码失效 40001、无权 40301。

### 3.5 签到接口

**POST /api/activities/{id}/checkin**（组织者本人）：body `{"code": "xY3k9Qz2LmN8pR4t"}`。`code` 允许传完整 URL（含 `code=` 参数，服务端解析）。成功响应：

```json
{ "code": 0, "data": { "user_name": "张三", "username": "2023001", "checked_in_at": "2025-06-01T10:03:11Z" } }
```

重复签到返回 40901，`message` = 「该同学已于 {HH:mm} 签到」，`data.checked_in_at` 返回首次签到时间。

**POST /api/activities/{id}/checkin/manual**（组织者本人）：body `{"username": "2023001"}`，按学号补签（`method=MANUAL`）。校验链同上（找到该活动下该学生的 `WON` 报名）；无报名或非中签 40001。

### 3.6 管理员接口

**GET /api/admin/users**（ADMIN）：分页 + `keyword`/`role` 过滤。
**PATCH /api/admin/users/{id}**（ADMIN）：body `{"role": "ORGANIZER"}` 或 `{"is_active": 0}` 或两者。规则见 §2.11。

### 3.7 Pydantic Schema 定义（schemas.py）

```python
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

# ---------- 通用 ----------
class PageOut(BaseModel):
    items: list
    total: int
    page: int
    size: int
    pages: int

# ---------- 认证 ----------
class RegisterIn(BaseModel):
    username: str = Field(min_length=4, max_length=50,
                          pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=6, max_length=64)
    real_name: str = Field(min_length=1, max_length=50)
    role: Literal["STUDENT", "ORGANIZER"]
    email: str | None = None
    phone: str | None = None

class LoginIn(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    real_name: str
    role: str
    email: str | None
    phone: str | None
    is_active: int
    created_at: datetime

# ---------- 活动 ----------
class ActivityCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str | None = None
    location: str = Field(min_length=1, max_length=200)
    start_time: datetime
    end_time: datetime | None = None
    signup_deadline: datetime
    quota: int = Field(ge=1, le=100000)
    status: Literal["DRAFT", "PUBLISHED"] = "DRAFT"

class ActivityUpdate(BaseModel):   # 全部可选
    title: str | None = None
    description: str | None = None
    location: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    signup_deadline: datetime | None = None
    quota: int | None = Field(default=None, ge=1)

class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organizer_id: int
    title: str
    description: str | None
    location: str
    start_time: datetime
    end_time: datetime | None
    signup_deadline: datetime
    quota: int
    status: str
    lottery_at: datetime | None
    created_at: datetime

# ---------- 报名 ----------
class RegistrationCreate(BaseModel):
    accept_waitlist: bool = True

class RegistrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activity_id: int
    user_id: int
    username: str      # 由 service join 填充
    real_name: str
    status: str
    accept_waitlist: bool
    lottery_rank: int | None
    checked_in_at: datetime | None   # 无签到记录为 None
    created_at: datetime
```

序列化要求：`datetime` 字段统一输出 ISO 8601 UTC（`Z` 结尾），在 `main.py` 注册自定义 JSON 序列化或逐字段 `field_serializer`；`checked_in_at` 通过 left join `checkins` 填充，避免 N+1 查询（`selectinload`/`joinedload`）。

> 数据结构与数据库表结构（ER 关系、表结构 DDL、ORM 实现要点、数据完整性约束）见《数据库设计说明书》。

## 5. 关键技术实现方案

### 5.1 JWT 认证与权限

payload（S1）：

```json
{ "sub": "123", "role": "STUDENT", "iat": 1748000000, "exp": 1748086400 }
```

- `sub` 为**用户 id 字符串**（非 username，改名/换名不影响）；算法 HS256；密钥取 `SECRET_KEY`。
- `get_current_user` 流程：取 header → `decode_token` → 查库取用户 → `is_active` 校验 → 返回。**每次请求都查库**（保证禁用即时生效），单机 SQLite 下开销可忽略。
- `require_role("ORGANIZER", "ADMIN")` 返回依赖函数；`assert_activity_owner` 在取得 activity 对象后调用。两者组合完成"角色 + 归属"双重校验，所有活动级接口必须同时使用。

### 5.2 抽签算法（services/lottery.py::run_lottery）

执行步骤（单一事务）：

1. 读活动；`CANCELLED → 40001`；`LOTTERY_DONE → return {"executed": False, "reason": "already_done"}`（幂等）；未截止且非 force → 40001。
2. **原子占位**：`seed = secrets.token_hex(16)`，执行条件 UPDATE：

```python
rows = db.execute(
    update(Activity)
    .where(Activity.id == activity_id,
           Activity.status == ActivityStatus.PUBLISHED)
    .values(status=ActivityStatus.LOTTERY_DONE,
            lottery_seed=seed, lottery_at=utcnow())
).rowcount
if rows == 0:                      # 并发或已被处理
    db.rollback()
    return {"executed": False, "reason": "concurrent_or_done"}
```

3. 取全部 `PENDING` 报名（`order_by(id)` 保证输入顺序稳定，可复现）。
4. `random.Random(seed).shuffle(ranks)` 生成每人 `lottery_rank`（同活动内唯一）。
5. 按 `lottery_rank` 排序：前 `quota` 名 → `WON` + 生成 `qr_token = secrets.token_urlsafe(16)`；其余 → `accept_waitlist ? WAITING : LOST`。
6. `db.commit()`；写 INFO 日志（activity_id/seed/won/waiting/lost）。
7. 返回计数。

边界行为：报名 0 人 → 状态仍置 `LOTTERY_DONE`，无中签；报名 ≤ 名额 → 全部 `WON`、无候补（rank 仍赋值，便于审计排序）。

性能：1000 人报名 = 1000 行内存 shuffle + 批量状态更新，远低于 1s 要求；注意用 `db.execute(update(...).values(status=...))` 按 status 分组批量更新替代逐对象 flush 亦可，两种实现均达标。

### 5.3 候补递补（promote_waitlist）

```python
def promote_waitlist(db, activity) -> list[Registration]:
    won_count = count(WON of activity)          # 当前中签数
    vacancy = activity.quota - won_count
    if vacancy <= 0:
        return []
    candidates = db.scalars(
        select(Registration)
        .where(activity_id == activity.id,
               status == RegistrationStatus.WAITING)
        .order_by(Registration.lottery_rank.asc())
        .limit(vacancy)
        .with_for_update()   # MySQL 行锁；SQLite 忽略，靠写锁串行
    ).all()
    for reg in candidates:
        reg.status = RegistrationStatus.WON
        reg.qr_token = secrets.token_urlsafe(16)
    db.flush()
    return candidates
```

硬性要求：**不 commit、不 rollback**——事务控制权归调用方（退出接口 / 编辑接口），保证"退出 + 递补"或"改名额 + 递补"原子。候补为空时直接返回空列表，名额空缺不做处理（FR-5.5）。

### 5.4 自动抽签调度与兜底

1. `lifespan` 内 `Base.metadata.create_all` → 注册 job（interval=配置值，默认 30s，`max_instances=1, coalesce=True`）→ `scheduler.start()`；关闭时 `shutdown(wait=False)`。
2. job 内逐活动 `try: run_lottery(...) except Exception: logger.exception(...)`，单活动失败不中断批次。
3. **兜底（集成点 I-2）**：`GET /api/activities/{id}` 发现到期未抽签时同步触发一次 `run_lottery`（幂等，即使调度器宕机结果仍正确）。
4. 开发期注意：`uvicorn --reload` 会加载两次应用导致调度器双实例，开发调试时可设 `AUTO_LOTTERY_ENABLED=false`（M0 配置项，默认 true）跳过调度注册；验收/演示部署**不得使用 --reload**。

### 5.5 二维码生成

- 内容：`{PUBLIC_BASE_URL}/checkin.html?code={qr_token}`；`qrcode.make(content, box_size=8, border=2)` → PNG → `StreamingResponse(media_type="image/png", headers={"Cache-Control": "no-store"})`。
- 权限：学生仅本人；组织者需 `assert_activity_owner`；ADMIN 放行。
- 仅 `status == WON` 且 `qr_token` 非空可出码；退出/取消后 `qr_token=None`，接口自然拒绝（40001）。

### 5.6 签到校验链（do_checkin）

按序执行，命中即返回对应错误：

| # | 校验 | 失败 |
| --- | --- | --- |
| 1 | code 非空；若含 `code=` 则解析出参数值 | 40001「签到码不能为空」 |
| 2 | `qr_token` 存在 | 40401「签到码无效」 |
| 3 | `reg.activity_id == activity.id` 且活动非 CANCELLED | 40001「签到码不属于本活动」 |
| 4 | `reg.status == WON` | 40001「该同学当前不是中签状态」 |
| 5 | 无既有签到记录（前置查询 + UNIQUE 兜底） | 40901 + 首次签到时间 |
| 6 | 写入 checkins（method=SCAN/MANUAL）并 commit | — |

### 5.7 统计计算（calc_stats）

```
registered = count(status in [PENDING, WON, WAITING, LOST, WITHDRAWN])
won / waiting / lost / withdrawn = 各状态计数
checked_in = count(checkins of activity)
win_rate     = won / registered      (registered == 0 → 0)
checkin_rate = checked_in / won      (won == 0 → 0)
quota_usage  = won / quota
```

比率保留 4 位小数（S8），前端按百分比展示。响应结构：

```json
{ "code": 0, "data": {
  "activity_id": 1, "quota": 10, "registered": 20, "pending": 0,
  "won": 10, "waiting": 8, "lost": 2, "withdrawn": 0, "checked_in": 7,
  "win_rate": 0.5, "checkin_rate": 0.7, "quota_usage": 1.0,
  "lottery_at": "2025-05-31T00:00:12Z" } }
```

### 5.8 Excel 导出（exporter.py）

- 列定义：报名表（序号/学号工号/姓名/报名时间/接受候补/状态/抽签序号/签到状态/签到时间）；中签表（序号/学号工号/姓名/抽签序号/签到码/签到状态/签到时间）。
- 样式：表头加粗居中、`freeze_panes="A2"`、按内容自适应列宽；状态列输出中文映射（附录 A）。
- 文件名：`{活动名}_{报名表|中签表}_{YYYYMMDD}.xlsx`；响应头 `Content-Disposition: attachment; filename*=UTF-8''<urlencoded>`（S9，防中文乱码）；`Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`。
- 签到码列仅中签表导出，且**仅导出当前有效中签者**（WITHDRAWN 者不含）。

### 5.9 并发控制与 SQLite 优化

1. 引擎参数：`connect_args={"check_same_thread": False, "timeout": 30}`；首次建连执行 `PRAGMA journal_mode=WAL`（`event.listens_for(engine, "connect")`）。
2. 写操作统一 `retry_on_locked(n=3)` 装饰器：捕获 `OperationalError("database is locked")` 时回滚并退避重试（50ms/100ms/200ms）。
3. 部署约束：**单进程单 worker**（`uvicorn` 不加 `--workers`，不加 `--reload`），彻底规避多实例调度与写锁竞争。
4. 报名/签到等高频写接口的并发正确性完全依赖 UNIQUE 约束 + 事务，应用层前置查询仅作友好提示。

## 6. 模块间依赖关系与集成点

### 6.1 依赖规则（开发红线）

1. 依赖方向单向：`routers → services → models`；禁止反向依赖、禁止 router 直接 import 另一个 router。
2. service 之间依赖白名单（除此之外禁止互相 import）：

| 调用方 | 被调方 | 场景 |
| --- | --- | --- |
| `services/registration.py` | `services/lottery.py::promote_waitlist` | 中签者退出时同事务递补 |
| `routers/activities.py`（编辑） | `services/lottery.py::promote_waitlist` | 名额调大时同事务递补 |
| `routers/activities.py`（详情/抽签） | `services/lottery.py::run_lottery` | 手动抽签、到期兜底 |
| `services/exporter.py` | `services/stats.py` 及 models | 导出数据源 |

3. `run_lottery` 是抽签的**唯一入口**：调度器、手动触发、详情兜底三条路径都必须收敛到该函数，禁止在路由层重写抽签逻辑。

### 6.2 依赖关系图

```
routers/auth ──────────> security + deps + models
routers/activities ─┬──> models
                    ├──> lottery.run_lottery（手动/兜底）
                    └──> lottery.promote_waitlist（改名额）
routers/registrations → services/registration ─┬─> models
                                              └─> lottery.promote_waitlist（退出）
routers/checkins ─────> services/checkin ─────> models
routers/admin ─────────> models
scheduler ────────────> lottery.run_lottery（自动）
services/stats / exporter ──> models
（全部 routers 依赖 deps.get_current_user / require_role / assert_activity_owner）
```

### 6.3 集成点清单

| 编号 | 上游 | 下游 | 契约 | 失败影响 |
| --- | --- | --- | --- | --- |
| I-1 | scheduler | run_lottery | 每 30s 扫描到期 PUBLISHED 活动 | 抛异常记日志跳过；兜底 I-2 仍可保证结果 |
| I-2 | 活动详情接口 | run_lottery | 读时发现到期未抽则同步触发 | 幂等，与调度器并发安全 |
| I-3 | 报名取消/退出接口 | promote_waitlist | 退出 WON 时同事务递补 | 同事务回滚，不会出现"退了没补" |
| I-4 | 活动编辑接口 | promote_waitlist | quota 调大时同事务补足差额 | 同上 |
| I-5 | 签到接口 | 报名状态 + checkins | 校验链 §5.6 + UNIQUE 兜底 | 并发重复签到由 DB 拦截转 40901 |
| I-6 | 导出接口 | 名单查询 + checkin 关联 | left join checkins 取签到时间 | — |
| I-7 | 前端 api.js | 全部 /api | token 注入、401 统一跳登录、`{code,message,data}` 解析 | 前端唯一 HTTP 出口 |
| I-8 | seed.py | models + security | 建 ADMIN/org1/stu001~020 + 3 活动 + 60 报名 | 见附录 C |

### 6.4 事务边界一览

| 用例 | 事务范围 | 提交点 |
| --- | --- | --- |
| run_lottery | 占位 UPDATE → 状态写回 → commit | lottery.py |
| 退出 + 递补（I-3） | 状态置 WITHDRAWN + 清 qr_token + 递补 | 调用方（registration.withdraw） |
| 改名额 + 递补（I-4） | 更新 quota + 递补 | 调用方（activities.edit） |
| 报名/取消 | 单记录状态变更 | 调用方 |
| 签到 | 校验 + insert checkins | checkin.py |
| 统计/导出 | 只读，无事务 | — |

规则：service 函数内部**只允许** `run_lottery` / `do_checkin` 这类完整用例函数 commit；`promote_waitlist` 等被复用子函数只 flush 不 commit。

## 7. 边界条件与异常处理策略

### 7.1 全局异常体系（errors.py）

```python
class BizError(Exception):
    def __init__(self, code=40001, http_status=400,
                 message="请求错误", data=None): ...

@app.exception_handler(BizError)          # → 统一响应体 + 对应 HTTP 码
@app.exception_handler(RequestValidationError)  # → 400 / 40001，message 取首条错误
@app.exception_handler(IntegrityError)    # → 409 / 40901「数据冲突」兜底
@app.exception_handler(Exception)         # → 500 / 50001，logger.exception 记录
```

使用要求：业务代码只抛 `BizError`（或其便捷构造 `BadRequest/NotFound/Forbidden/Conflict`），禁止直接抛 `HTTPException`；每处抛出必须携带中文 message。

### 7.2 边界条件矩阵

**时间边界**

| 场景 | 判定 | 行为 |
| --- | --- | --- |
| 报名时 `now == signup_deadline` | `now < deadline` 为可报名（S4） | 等于即拒绝，40001「报名已截止」 |
| 截止后 30s 空档内 | 调度器尚未扫描 | 报名接口已拒绝；详情兜底触发抽签 |
| 未截止手动抽签 | — | 40001；ADMIN `force=true` 例外（调试用） |
| 创建/编辑时 deadline 早于 now | — | 40001（发布态除外，见 §2.4） |
| 跨时区访问 | 服务端统一 UTC 判定 | 不信任前端时间 |

**数量边界**

| 场景 | 行为 |
| --- | --- |
| 有效报名 0 人 | 抽签正常完成，`won=0` |
| 报名 ≤ 名额 | 全部 WON，无候补 |
| 改小名额 < 当前 WON 数 | 40001 拒绝（S10） |
| 候补为空时退出 | 名额空缺，不处理（FR-5.5） |
| quota=0 / 负数 | Pydantic `ge=1` 拦截 |

**状态边界（接口 × 活动状态）**

| 接口 | DRAFT | PUBLISHED | LOTTERY_DONE | CANCELLED |
| --- | --- | --- | --- | --- |
| 报名 | 40001 | ✅（未截止） | 40001 | 40001 |
| 取消/退出 | 40001（无报名） | ✅ PENDING/WAITING | ✅ WON/WAITING | 报名存在但不可签到 |
| 手动抽签 | 40001 | ✅（须已截止） | 幂等返回 executed=False | 40001 |
| 编辑 | ✅ | ✅（未截止） | 40001 | 40001 |
| 签到 | — | 40001 | ✅ | 40001 |
| 导出/统计 | ✅（空数据） | ✅（抽签前空指标） | ✅ | ✅ |

**并发边界**

| 场景 | 机制 | 结果 |
| --- | --- | --- |
| 同一学生并发双击报名 | 前置查询可能都通过 → UNIQUE 兜底 | 恰一条成功，另一条 40901 |
| 调度器与手动同时抽签 | 条件 UPDATE 原子占位 | 仅一方执行名单生成 |
| 两个组织者端同时给同一人签到 | 前置查询 + UNIQUE | 后到者 40901 + 首次时间 |
| 并发退出 + 递补 | 同事务 + quota-won_count 差额计算 | 名额不超发 |

**权限边界**

| 场景 | 结果 |
| --- | --- |
| 学生创建/编辑/抽签/导出 | 40301 |
| 组织者操作他人活动（含二维码、签到、导出） | 40301 |
| 学生查看他人二维码 | 40301 |
| 组织者报名任何活动 | 40301（按"非 STUDENT 不可报名"统一实现） |
| 被禁用用户任何请求 | 40101 |

**输入边界**：username/密码/姓名/quota/时间格式由 Pydantic 统一拦截（40001）；分页 `size>50` 截断为 50、`page<1` 置 1；`keyword` 最大 50 字符截断。

### 7.3 日志规范

统一格式：`{时间} {级别} [{模块}] {事件} key=value ...`。必记事件（INFO）：

| 事件 | 字段 |
| --- | --- |
| 抽签完成 | activity_id, seed, won, waiting, lost |
| 递补发生 | activity_id, promoted_user_ids, count |
| 签到成功 | activity_id, user_id, operator_id, method |
| 导出 | activity_id, type, row_count, operator_id |
| 登录失败（可 DEBUG 级） | username（不记密码） |

异常一律 `logger.exception`（含堆栈）。日志写文件 + 控制台（`logging.basicConfig`，MVP 不引日志框架）。

## 附录 A　状态中文映射

```
ACTIVITY_STATUS_CN = {"DRAFT":"草稿","PUBLISHED":"报名中",
  "LOTTERY_DONE":"已抽签","CANCELLED":"已取消"}
REGISTRATION_STATUS_CN = {"PENDING":"待抽签","WON":"已中签",
  "WAITING":"候补中","LOST":"未中签","CANCELLED":"已取消",
  "WITHDRAWN":"已退出"}
```

## 附录 B　错误码总表

| code | HTTP | 含义 |
| --- | --- | --- |
| 0 | 200 | 成功 |
| 40001 | 400 | 参数错误 / 报名已截止 / 状态不允许 |
| 40101 | 401 | 未登录或 token 失效 / 账号被禁用 |
| 40102 | 401 | 用户名或密码错误 |
| 40301 | 403 | 无权限访问该资源 |
| 40401 | 404 | 资源不存在 / 签到码无效 |
| 40901 | 409 | 重复报名 / 重复签到 / 用户名已存在 |
| 50001 | 500 | 服务器内部错误 |
