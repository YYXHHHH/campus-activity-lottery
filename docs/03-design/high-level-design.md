# 校园活动报名抽签与签到系统 —— 概要设计说明书（HLD）

> **所属阶段**：系统设计（概要）　|　**版本**：v1.0　|　**整理日期**：2026-10-02
> **内容来源**：《开发文档》§1 总体设计、§2 功能模块拆分与职责；《需求与设计文档》§7 技术架构、§10 前端设计
> **编号说明**：本文章节编号沿用来源文档，以便与《开发文档》《需求与设计文档》交叉检索。

---
## 1. 总体设计

### 1.1 分层架构

系统为经典三层单体架构，浏览器直连 FastAPI（前后端同源部署，无跨域需求，MVP 不启用 CORS）。

```
浏览器（纯 HTML + JS + fetch）
        │  HTTP + JSON（JWT Bearer）
        ▼
FastAPI（uvicorn，单进程单 worker）
  ├─ routers/   路由层：参数校验、鉴权、调 service、组装响应
  ├─ services/  服务层：业务规则、状态机、事务边界
  ├─ models.py  模型层：ORM 定义与约束
  ├─ deps.py    依赖注入：DB 会话 / 当前用户 / 角色 / 归属校验
  ├─ errors.py  统一异常与响应包装
  └─ scheduler  APScheduler：自动抽签（仅调用 service）
        │  SQLAlchemy 2.0 ORM
        ▼
SQLite（app.db，WAL 模式）→ 可零改动切换 MySQL 8
```

各层职责与红线：

| 层 | 代码位置 | 职责 | 禁止事项 |
| --- | --- | --- | --- |
| 路由层 | `app/routers/` | Pydantic 入参校验、鉴权与角色检查、调用 service、包装响应 | 禁止编写跨表业务规则、禁止自行 `commit` 事务 |
| 服务层 | `app/services/` | 全部业务规则：状态机守卫、抽签、递补、签到、统计、导出 | 禁止依赖 HTTP 对象（Request/Response） |
| 模型层 | `app/models.py` | ORM 模型、唯一约束、索引、枚举 | 禁止出现业务方法之外的逻辑 |
| 基础设施 | `config.py`、`database.py`、`security.py`、`deps.py`、`errors.py` | 配置、引擎/会话、密码/JWT、依赖注入、异常 | — |
| 调度层 | `app/scheduler.py` | 周期扫描到期活动并调用 `run_lottery` | 禁止内联业务逻辑，只做「查询 + 委托」 |
| 前端 | `static/` | 页面渲染与交互，全部数据经 `/api` | 禁止在前端做截止判断等业务决策（仅作展示提示） |

### 1.2 目录结构与模块映射

```
activity-lottery/
├─ app/
│  ├─ main.py                # FastAPI 实例、路由注册、静态挂载、lifespan 启动调度器
│  ├─ config.py              # pydantic-settings 读取 .env（M0）
│  ├─ database.py            # engine / SessionLocal / Base / get_db（M0）
│  ├─ models.py              # 全部 ORM 模型（M0）
│  ├─ schemas.py             # Pydantic 请求/响应模型（M0）
│  ├─ security.py            # 密码哈希、JWT 签发与解析（M0/M1）
│  ├─ deps.py                # get_current_user / require_role / assert_activity_owner（M0）
│  ├─ errors.py              # BizError + 全局异常处理器（M0）
│  ├─ services/
│  │  ├─ registration.py     # 报名 / 取消 / 退出（M3）
│  │  ├─ lottery.py          # 抽签 run_lottery + 递补 promote_waitlist（M4/M5）
│  │  ├─ checkin.py          # 签到 do_checkin（M6）
│  │  ├─ stats.py            # 统计计算（M7）
│  │  └─ exporter.py         # openpyxl 导出（M7）
│  ├─ routers/
│  │  ├─ auth.py             # 认证（M1）
│  │  ├─ activities.py       # 活动（M2，含抽签/名单/统计/导出路由）
│  │  ├─ registrations.py    # 报名（M3）
│  │  ├─ checkins.py         # 签到（M6）
│  │  └─ admin.py            # 用户管理（M9）
│  └─ scheduler.py           # APScheduler 自动抽签（M8）
├─ static/                   # 前端页面（M10，见 §2.12）
├─ tests/                    # pytest 用例（见 §10）
├─ seed.py                   # 初始化 ADMIN + 演示数据
├─ init_db.py                # 建表脚本（可并入 main lifespan）
├─ requirements.txt / .env.example / run.bat / README.md
└─ app.db                    # SQLite 数据文件（gitignore）
```

### 1.3 配置项定义（.env）

由 `config.py` 使用 `pydantic-settings` 加载；`.env` 文件不入库，仓库提供 `.env.example`。

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `APP_NAME` | str | 校园活动抽签系统 | 应用名，用于日志与页面标题 |
| `SECRET_KEY` | str | 无（必填） | JWT 签名密钥；缺失或等于示例值时**启动直接抛错**，防止弱密钥上线 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | int | 1440 | token 有效期（分钟），即 24h |
| `DATABASE_URL` | str | `sqlite:///./app.db` | 数据库连接串；切 MySQL 改为 `mysql+pymysql://...?charset=utf8mb4` |
| `PUBLIC_BASE_URL` | str | `http://localhost:8000` | 二维码内容前缀，必须为局域网可达地址（手机扫码依赖） |
| `AUTO_LOTTERY_INTERVAL_SECONDS` | int | 30 | 自动抽签扫描周期（秒） |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | str | admin / admin123 | seed.py 初始管理员账号 |

启动加载规则：`SECRET_KEY` 非空且长度 ≥ 16，否则 `raise RuntimeError`；`PUBLIC_BASE_URL` 不以 `/` 结尾（启动时自动 strip）。

## 2. 功能模块拆分与职责

### 2.1 模块总览

| 编号 | 模块 | 代码位置 | 对应需求 | 优先级 |
| --- | --- | --- | --- | --- |
| M0 | 公共基础设施 | `config.py`、`database.py`、`models.py`、`schemas.py`、`security.py`、`deps.py`、`errors.py` | 支撑全部 | P0 |
| M1 | 认证与用户 | `routers/auth.py` | FR-1 | P0 |
| M2 | 活动管理 | `routers/activities.py` | FR-2 | P0 |
| M3 | 报名 | `routers/registrations.py`、`services/registration.py` | FR-3 | P0 |
| M4 | 抽签 | `services/lottery.py::run_lottery` | FR-4 | P0 |
| M5 | 候补递补 | `services/lottery.py::promote_waitlist` | FR-5 | P0 |
| M6 | 签到 | `routers/checkins.py`、`services/checkin.py` | FR-6 | P0 |
| M7 | 统计与导出 | `services/stats.py`、`services/exporter.py` | FR-7 | P0 |
| M8 | 定时调度 | `scheduler.py` | FR-4.1 | P0 |
| M9 | 管理员用户管理 | `routers/admin.py` | FR-1.7 | P1 |
| M10 | 前端页面 | `static/` | 全部 | P0 |

### 2.2 M0 公共基础设施

职责：为各业务模块提供配置、数据库会话、ORM 模型、鉴权依赖、异常体系，**不含任何业务规则**。

关键函数与契约：

| 函数/类 | 位置 | 签名与说明 |
| --- | --- | --- |
| `get_db` | `database.py` | FastAPI 依赖，yield `Session`，请求结束自动关闭；不自动 commit |
| `get_current_user` | `deps.py` | 解析 `Authorization: Bearer` → 查 `users` → 校验 `is_active=1` → 注入 `User`；失败抛 40101 |
| `require_role(*roles)` | `deps.py` | 返回依赖工厂；角色不在 roles 内抛 40301。`ADMIN` 单独放行场景见 §5.1 |
| `assert_activity_owner(activity, user)` | `deps.py` | `user.role == ADMIN` 或 `activity.organizer_id == user.id`，否则抛 40301 |
| `hash_password` / `verify_password` | `security.py` | passlib bcrypt；`verify` 失败返回 False，不得抛异常 |
| `create_access_token(user)` | `security.py` | 签发 JWT（payload 见 §5.1） |
| `decode_token(token)` | `security.py` | 过期/篡改抛 `JWTError`，由 `get_current_user` 统一转 40101 |
| `BizError` | `errors.py` | `BizError(code, http_status, message, data=None)`；全局 handler 统一输出响应体 |
| `utcnow()` | `database.py` 或工具模块 | `datetime.now(timezone.utc)`，全项目唯一时间来源，禁止散落调用 `datetime.now()` |

### 2.3 M1 认证与用户

职责：注册（STUDENT/ORGANIZER）、登录发 token、查询当前用户。

业务规则（对齐 FR-1）：

1. 注册校验：用户名 4–50 位 `[A-Za-z0-9_]`、唯一；密码 ≥ 6 位；姓名 1–50 位；`role` 仅允许 `STUDENT`/`ORGANIZER`，传 `ADMIN` 返回 40001。
2. 用户名重复：依赖 `users.username` UNIQUE，捕获 `IntegrityError` 转 40901「用户名已存在」。
3. 密码 bcrypt 哈希存储；任何响应体不得含 `password_hash` 字段。
4. 登录失败统一 40102「用户名或密码错误」，不区分用户名不存在/密码错误（防枚举）。
5. `is_active=0` 的用户登录返回 40101「账号已被禁用」；已登录用户被禁用后，下一次请求 `get_current_user` 校验 `is_active` 即拒绝。

### 2.4 M2 活动管理

职责：活动 CRUD、发布、取消、状态机守卫、组织者归属控制。

状态机与守卫（对齐 FR-2 与需求文档 §5.1）：

```
DRAFT ──publish──> PUBLISHED ──(截止且抽签)──> LOTTERY_DONE
  │                    │
  └──────cancel────────┴────> CANCELLED
```

| 操作 | 前置状态 | 校验要点 | 失败错误 |
| --- | --- | --- | --- |
| 创建 | — | 必填：title/location/start_time/signup_deadline/quota；`quota ≥ 1`；`signup_deadline > now`；`signup_deadline <= start_time`；初始 `status=DRAFT`（创建请求体可显式传 `PUBLISHED` 直接发布，仍走同一套校验） | 40001 |
| 编辑 | `DRAFT` 或 `PUBLISHED` 且未截止 | 同创建校验；改小名额时要求 `新quota ≥ 当前WON人数`（S10），否则 40001；`LOTTERY_DONE/CANCELLED` 不可编辑（40001） | 40001 |
| 发布 | `DRAFT` | `signup_deadline > now` 才可发布，否则 40001 | 40001 |
| 取消 | `DRAFT`/`PUBLISHED`/`LOTTERY_DONE` | 置 `CANCELLED`；已有报名保留但不可签到（签到校验链拦截，见 §5.6） | — |
| 手动抽签 | `PUBLISHED` 且已截止 | 委托 `run_lottery`（M4） | 40001/幂等返回 |

补充约定：`PUBLISHED` 状态下将 `signup_deadline` 修改为过去时间是**允许的**（组织者提前截止），下一次调度扫描（≤30s）或任何人访问该活动详情时触发抽签。

### 2.5 M3 报名

职责：报名、取消/退出（同一接口两种语义）、我的报名列表。

规则（对齐 FR-3）：

1. 报名条件：活动 `PUBLISHED` 且 `now_utc() < signup_deadline`；报名人角色必须为 `STUDENT`（组织者报名自己活动 40301，报名他人活动同样 40301——统一按"非 STUDENT 不可报名"实现）。
2. 重复报名：先查有效记录（状态 ≠ CANCELLED）返回 40901；并发兜底靠 `UNIQUE(activity_id, user_id)`，捕获 `IntegrityError` 转 40901。
3. 取消后重报：复用原记录，状态回 `PENDING`，`accept_waitlist` 按新请求更新，`created_at` 保留原值、`updated_at` 刷新。
4. `DELETE /api/activities/{id}/registrations/me` 为**取消/退出统一入口**，按当前状态分流：`PENDING/WAITING → CANCELLED`；`WON → WITHDRAWN`（清空 `qr_token` 并同事务触发递补）；其余状态 40001。
5. 我的报名列表按 `created_at desc` 排序，每条含活动摘要、报名状态、`lottery_rank`、签到状态。

### 2.6 M4 抽签

职责：实现 `run_lottery(db, activity_id, *, force=False)`，保证**幂等、随机、可复现**。完整算法见 §5.2。

### 2.7 M5 候补递补

职责：实现 `promote_waitlist(db, activity)`，按 `lottery_rank` 升序补足名额，**必须与调用方同事务**。触发点共 2 个：中签者退出（M3）、组织者调大名额（M2 编辑接口，FR-5.6）。实现见 §5.3。

### 2.8 M6 签到

职责：`do_checkin(db, activity, code, operator, method)` 五步校验链 + 写入 `checkins`。见 §5.6。

### 2.9 M7 统计与导出

职责：`calc_stats(db, activity)` 输出六项计数与三项比率（§5.7）；`export_registrations` / `export_winners` 产出 xlsx 字节流（§5.8）。

### 2.10 M8 定时调度

职责：APcheduler `BackgroundScheduler` 每 30s 扫描 `status=PUBLISHED AND signup_deadline <= now` 的活动，逐个委托 `run_lottery`；单活动失败记 `logger.exception` 后继续下一个，**不影响其他活动**。配置 `max_instances=1, coalesce=True` 防堆积。见 §5.4。

### 2.11 M9 管理员用户管理

职责：用户列表（分页 + 关键词）、修改角色（仅可在 STUDENT/ORGANIZER 间互改，**不允许把任何人提为 ADMIN**，也不允许改 ADMIN 账号的角色）、启用/禁用。禁用即时生效（登录与请求两处拦截）。

### 2.12 M10 前端页面

| 页面 | 文件 | 数据依赖接口 |
| --- | --- | --- |
| 登录/注册 | `login.html` / `register.html` | `/api/auth/*` |
| 活动列表（首页） | `index.html` | `GET /api/activities`（分页/筛选） |
| 活动详情 | `activity_detail.html` | `GET /api/activities/{id}`、`POST .../registrations` |
| 我的报名 | `my_registrations.html` | `GET /api/me/registrations`、`GET /api/registrations/{id}/qrcode`、`DELETE .../registrations/me` |
| 我的活动（组织者） | `organizer.html` | `GET /api/activities?mine=true`、`POST /api/activities` |
| 活动管理 | `activity_manage.html` | `registrations`/`winners`/`checkins`/`stats`/`export`/`lottery` |
| 扫码签到 | `checkin.html` | `POST .../checkin`、`GET .../stats`（10s 轮询） |
| 用户管理 | `admin.html` | `/api/admin/users`、`PATCH /api/admin/users/{id}` |

前端通用要求：`js/api.js` 统一封装 fetch（自动注入 token、401 清 token 跳登录、统一解析 `{code,message,data}`）；所有时间展示用 `new Date(iso).toLocaleString('zh-CN')`；状态徽章颜色 `WON`绿/`WAITING`橙/`LOST`灰/`PENDING`蓝/`CANCELLED、WITHDRAWN`红。

## 7. 技术架构（来源：需求与设计文档 §7）

### 7.1 架构图
```
┌─────────────────────────────────────────────┐
│  浏览器（纯 HTML + JS + fetch）              │
│  login / activities / detail / my / manage   │
│  / checkin / stats                           │
└───────────────────┬─────────────────────────┘
│ HTTP + JSON (JWT)
┌───────────────────▼─────────────────────────┐
│  FastAPI (uvicorn, 单进程)                   │
│  ├─ routers/   认证 活动 报名 签到 统计导出   │
│  ├─ services/  lottery / waitlist / export   │
│  ├─ deps.py    get_db / current_user / role  │
│  └─ scheduler  APScheduler 自动抽签           │
│  ├─ qrcode  → PNG 字节流                     │
│  └─ openpyxl → xlsx 字节流                   │
└───────────────────┬─────────────────────────┘
│ SQLAlchemy ORM
┌─────▼─────┐
│  SQLite   │ → 后续可换 MySQL 8
└───────────┘
```
### 7.2 技术选型说明
| 模块 | MVP | 后续升级 |
|---|---|---|
| 后端 | FastAPI 0.110+ | 不变 |
| ORM | SQLAlchemy 2.0 | 不变 |
| 数据库 | SQLite（`app.db`） | MySQL 8（只改 `DATABASE_URL`） |
| 前端 | 纯 HTML + 原生 JS（fetch） | Vue 3 + Vite + Element Plus |
| 认证 | python-jose(JWT) + passlib[bcrypt] | 不变 |
| 二维码 | `qrcode[pil]` | 不变 |
| Excel | `openpyxl` | 不变 |
| 定时任务 | `apscheduler` | Celery / 独立定时服务 |
### 7.3 依赖清单（requirements.txt）
```
fastapi==0.111.0
uvicorn[standard]==0.30.1
sqlalchemy==2.0.30
pydantic==2.7.1
pydantic-settings==2.3.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
bcrypt==4.1.3
qrcode[pil]==7.4.2
openpyxl==3.1.2
apscheduler==3.10.4
python-multipart==0.0.9
pytest==8.2.0
httpx==0.27.0
```
---

## 10. 前端设计（来源：需求与设计文档 §10）

### 10.1 页面清单
| 页面 | 文件 | 角色 | 主要功能 |
|---|---|---|---|
| 登录 | `login.html` | 全部 | 用户名密码登录，存 token 到 localStorage |
| 注册 | `register.html` | 全部 | 注册，可选角色 |
| 活动列表 | `index.html` | 全部 | 卡片列表、关键词搜索、状态筛选、分页 |
| 活动详情 | `activity_detail.html` | 学生 | 活动信息、报名按钮 + 「接受候补」勾选、我的状态展示 |
| 我的报名 | `my_registrations.html` | 学生 | 列表 + 状态徽章 + 「查看二维码」弹窗 + 取消/退出按钮 |
| 我的活动 | `organizer.html` | 组织者 | 我创建的活动列表 + 新建活动表单 + 进入管理 |
| 活动管理 | `activity_manage.html` | 组织者 | Tab：报名名单 / 中签名单 / 签到名单 / 统计 / 导出；「立即抽签」按钮 |
| 扫码签到 | `checkin.html` | 组织者 | 输入框 + 提交按钮 + 实时签到进度；URL 带 `?code=` 自动提交 |
| 用户管理 | `admin.html` | 管理员 | 用户列表、禁用、改角色 |
### 10.2 交互关键点
1. **token 处理**：`api.js` 统一封装 fetch，自动注入 `Authorization`，遇 401 清 token 并跳登录页。
2. **状态徽章颜色**：`WON` 绿、`WAITING` 橙、`LOST` 灰、`PENDING` 蓝、`CANCELLED/WITHDRAWN` 红。
3. **二维码展示**：`<img src="/api/registrations/{id}/qrcode?t=时间戳">`，加时间戳避免缓存；仅 `WON` 状态显示按钮。
4. **签到页自动提交**：读取 `location.search` 中的 `code`，存在则 300ms 后自动提交并显示结果卡片（成功绿色 / 重复橙色 / 无效红色），便于手机扫码后直接打开。
5. **抽签按钮**：点击后二次确认 → 调用接口 → 刷新名单；未截止时按钮禁用并提示剩余时间。
6. **实时签到率**：签到页每 10 秒轮询一次 `/stats`（MVP 用轮询，不上 WebSocket）。
### 10.3 前端目录
```
static/
├─ index.html / login.html / register.html
├─ activity_detail.html / my_registrations.html
├─ organizer.html / activity_manage.html
├─ checkin.html / admin.html
├─ css/style.css
└─ js/api.js auth.js activities.js manage.js checkin.js
```
> 迁移到 Vue3 时，页面结构一一对应组件，`api.js` 抽成 `src/api/index.js`（axios 实例），逻辑不变。
---
