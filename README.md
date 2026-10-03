# 活动报名 · 抽签 · 签到系统模板

[![tests](https://github.com/YYXHHHH/campus-activity-lottery/actions/workflows/tests.yml/badge.svg)](https://github.com/YYXHHHH/campus-activity-lottery/actions/workflows/tests.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

一个可以直接改造成自己项目的**活动报名与抽签系统模板**：覆盖「发布活动 → 报名 → 候补 → 公平抽签 → 二维码签到 → 统计与 Excel 导出」的完整闭环，抽签过程可复现、可审计。

模板的重点不是让你照抄业务，而是让你**低成本换成自己的场景**：改 `.env` 就能换站名、主题色、界面术语；改 `app/models.py` 就能换数据模型；前后端结构清晰，无构建步骤。

- **后端**：FastAPI + SQLAlchemy 2.0 + SQLite（只改一个环境变量即可切 MySQL）
- **前端**：原生 HTML / CSS / JS，无需 npm、无需打包
- **测试**：78 个 pytest 用例（内存 SQLite，不污染本地库）
- **定制**：品牌与术语集中在配置层，改 `.env` 即可，见下文「定制成你自己的项目」

> 默认界面语言为中文；术语全部可通过 `UI_LABELS` 覆盖，换成英文或其他场景无需改代码。

## 功能一览

| 模块 | 能力 |
| --- | --- |
| 账号与权限 | 三种角色（学生 / 组织者 / 管理员）、JWT 登录、注册、管理员改角色与封禁 |
| 活动 | 创建 / 编辑 / 发布 / 取消、名额与报名截止时间、草稿态 |
| 报名 | 报名、取消、候补意愿；重复报名与越权报名均被拒 |
| 抽签 | 幂等、可按种子复现；原子条件 UPDATE 防并发重复中签；1000 人抽签 < 1 秒 |
| 候补 | 退出或名额增加时，在同一事务内自动递补 |
| 签到 | 二维码签到（PNG、`no-store` 不缓存）、重复签到返回首次时间、按学号补签 |
| 统计导出 | 六项计数 + 三项比率、报名名单 / 中签名单 Excel 导出 |
| 调度 | APScheduler 到期自动抽签，读取时兜底，失败不影响其他活动 |

## 技术栈

| 层次 | 选型 |
| --- | --- |
| Web 框架 | FastAPI 0.111 |
| ORM | SQLAlchemy 2.0（`Mapped` 声明式） |
| 数据库 | SQLite（默认）；MySQL 8 只需改 `DATABASE_URL` |
| 前端 | 原生 HTML + `fetch`，零构建 |
| 鉴权 | PyJWT（HS256）+ passlib[bcrypt] |
| 二维码 | qrcode + pillow |
| Excel | openpyxl |
| 定时任务 | APScheduler |
| 测试 | pytest + httpx（TestClient） |

## 快速开始

### 方式一：一键脚本（推荐，Windows）

1. 克隆或下载本仓库；
2. 双击 `run.bat`（演示模式：单进程、无 `--reload`、自动抽签开启）；
3. 打开 <http://localhost:8000>。

脚本会自动完成：建虚拟环境 → 装依赖 → 由 `.env.example` 生成 `.env` 并写入随机 `SECRET_KEY` → 初始化演示数据 → 启动服务。
开发时用 `run.bat dev`（`--reload` 热重载；脚本会关闭自动抽签，避免调度器起两个实例）。

### 方式二：手动（跨平台）

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -c "import secrets;print(secrets.token_hex(32))"   # 把输出填进 .env 的 SECRET_KEY
python seed.py                     # 可选：写入演示数据
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

打开 <http://localhost:8000>，接口文档在 <http://localhost:8000/api/docs>。

## 演示账号（由 `seed.py` 创建）

| 角色 | 用户名 | 密码 | 说明 |
| --- | --- | --- | --- |
| 管理员 | `admin` | `admin123` | 取自 `.env`，可改角色与封禁账号 |
| 组织者 | `org1` | `123456` | 演示活动均由其创建 |
| 学生 | `stu001` ~ `stu020` | `123456` | 每个活动 20 条报名，前 15 人接受候补 |

演示活动的报名截止时间 = 运行 `seed.py` 的时刻 + 2 分钟，到点后调度器会在 30 秒内自动抽签，方便你立刻看到完整流程。
`seed.py` 是幂等的，可重复执行；想重置数据就停掉服务、删除 `app.db*` 再跑一次。

## 定制成你自己的项目

最常见的三件事：

```dotenv
# 1) 换站名与主题色（改 .env，重启即生效）
APP_NAME=会议室预约系统
BRAND_NAME=会议室预约系统
BRAND_SHORT_NAME=会议室预约
BRAND_COLOR=#0f766e

# 2) 换界面术语（JSON，键名见 app/branding.py 的 LABELS）
UI_LABELS={"activity.list_title": "会议室列表", "activity.unit": "会议室", "user.student": "申请人"}
```

3）换数据模型：编辑 `app/models.py` → 调整 `app/schemas.py` 与 `app/routers/*` → 删除本地 `app.db`（模板不包含迁移工具，改表结构后重建即可）→ 补 `seed.py` 与 `tests/`。

> 品牌注入是三层联动的：HTML 里的 `{{BRAND_NAME}}` / `{{LABELS[...]}}` 由服务端渲染（`app/main.py` 的 `TemplateStaticFiles`），前端 JS 通过 `api/brand.js` 注入的 `window.__BRAND__` 读取，另有只读接口 `GET /api/meta` 供外部调用。

### 可覆盖的术语键名

术语默认值定义在 [`app/branding.py`](app/branding.py) 的 `LABELS`，用 `UI_LABELS` 覆盖任意项。常用键：

| 键 | 默认值 | 出现位置 |
| --- | --- | --- |
| `app.tagline` | 报名 · 抽签 · 签到 | 登录页副标题 |
| `activity.list` / `activity.list_title` | 活动列表 / 校园活动 | 导航栏、首页大标题 |
| `activity.mine_registrations` | 我的报名 | 导航栏、页面标题 |
| `activity.mine_managed` | 我的活动 | 导航栏、页面标题 |
| `activity.manage` / `activity.detail` | 活动管理 / 活动详情 | 导航栏、页面标题 |
| `activity.unit` | 活动 | 各处文案 |
| `checkin.title` / `checkin.onsite` | 扫码签到 / 现场签到 | 签到页 |
| `user.list` | 用户管理 | 导航栏、页面标题 |
| `user.student` / `user.organizer` / `user.admin` | 学生 / 组织者 / 管理员 | 角色下拉框、导航栏身份 |

状态徽章文案在 `app/branding.py` 的 `STATUS_LABELS`、`REGISTRATION_STATUS_LABELS`、`ROLE_LABELS`，键名与 `app/models.py` 的枚举值一致。

### 加减页面

1. 在 `static/` 新建页面，头部照抄现有页面的三件套：`css/style.css` + `api/brand.css` + `api/brand.js`；
2. 脚本里调用 `App.initPage({ page: 'xxx.html', roles: ['ADMIN'] })`，它负责渲染导航栏、校验登录态与角色；
3. 要出现在导航栏，就编辑 `static/js/app.js` 的 `NAV_ITEMS`（`href` + `labelKey` + `roles`）；
4. 新接口写在 `app/routers/`，并在 `app/main.py` 里 `include_router`。

不需要的页面直接删文件、从 `NAV_ITEMS` 去掉即可。

## 关键实现约定

| 约定 | 说明 |
| --- | --- |
| 统一响应信封 | 所有接口返回 `{code, message, data}`；`code != 0` 表示业务错误，HTTP 状态码同步设置。前端 `api.js` 统一解包，`40101` 自动清理登录态并跳登录页 |
| 抽签公平与幂等 | 仅 `PUBLISHED` 且已过截止的活动可抽签；用条件 `UPDATE` 抢占 `LOTTERY_DONE` 状态，天然防并发重复抽签；`lottery_seed` 落库，凭同一份数据可复算出同一结果，便于事后审计 |
| 候补递补 | 退出或增加名额时，在同一事务内按 `lottery_rank` 立即递补，避免名额空置 |
| 时间与时区 | 数据库统一存 UTC 朴素时间；前端 `datetime-local` 输入经 `App.toUtcIso()` 转 ISO 串提交，展示用 `App.fmtTime()` 转回本地时间 |
| 签到防重 | `Checkin.registration_id` 唯一约束兜底；重复签到不报错，返回首次签到时间；二维码同时接受完整 URL 与裸码值 |
| 权限模型 | 角色（`require_role`）+ 归属（`assert_activity_owner`）双重校验；学生不可报名他人活动，组织者不可查看他人报名的二维码 |

## 页面一览

| 页面 | 路径 | 角色 |
| --- | --- | --- |
| 登录 / 注册 | `/login.html`、`/register.html` | 公开 |
| 活动列表 | `/index.html` | 全部 |
| 活动详情与报名 | `/activity_detail.html?id=<id>` | 学生 |
| 我的报名（含二维码） | `/my_registrations.html` | 学生 |
| 创建活动 | `/organizer.html` | 组织者 / 管理员 |
| 活动管理 | `/activity_manage.html?id=<id>` | 组织者 / 管理员 |
| 现场签到 | `/checkin.html` | 组织者 / 管理员 |
| 用户管理 | `/admin.html` | 管理员 |

## 目录结构

```
app/
  config.py           配置与品牌设置（改这里 / 改 .env）
  branding.py         界面术语表 LABELS 与品牌注入上下文
  models.py           数据模型：User / Activity / Registration / Checkin
  schemas.py          请求与响应模型
  routers/            auth / activities / registrations / checkins / admin / meta
  services/           lottery 抽签、registration 报名与候补、checkin 签到、stats 统计、exporter 导出
  deps.py             依赖注入：当前用户、角色、活动归属校验
  errors.py           统一异常与 {code,message,data} 响应包装
  database.py         引擎、会话、分页工具
  scheduler.py        到期自动抽签
static/               前端页面（原生 HTML/CSS/JS；HTML 走 Jinja2 注入品牌）
tests/                pytest 用例（内存 SQLite）
seed.py               幂等演示数据
init_db.py            单独建表
run.bat               Windows 一键启动（demo / dev 两种模式）
```

## 运行测试

```bash
python -m pytest            # 78 passed
```

用例使用内存 SQLite（`StaticPool`），不会读写 `app.db`。CI 在 Python 3.10 / 3.11 上跑同一套用例，见 [`.github/workflows/tests.yml`](.github/workflows/tests.yml)。

## 配置项说明

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_NAME` | `校园活动抽签系统` | 应用名（`BRAND_NAME` 未设时作为站名） |
| `BRAND_NAME` | 同 `APP_NAME` | 站点全称：登录页大标题、浏览器标题、接口文档标题 |
| `BRAND_SHORT_NAME` | 同 `BRAND_NAME` | 导航栏短名称 |
| `BRAND_COLOR` | `#2563eb` | 主题色，自动派生 hover 深色 |
| `UI_LABELS` | 空 | 界面术语覆盖表（JSON） |
| `SECRET_KEY` | 无 | **必填**，长度 ≥ 16 的随机串；留空或为示例值将拒绝启动 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | 登录态有效期（分钟） |
| `DATABASE_URL` | `sqlite:///./app.db` | 换 MySQL 只改这里 |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | 二维码里写入的地址，手机签到必须填局域网可达地址 |
| `AUTO_LOTTERY_ENABLED` | `true` | 是否启用到期自动抽签 |
| `AUTO_LOTTERY_INTERVAL_SECONDS` | `30` | 扫描周期（秒） |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / `admin123` | 管理员初始账号，由 `seed.py` 创建 |

## 部署注意

- **单进程单 worker**：调度器在进程内，多进程会重复抽签；演示与验收务必不要开 `--reload`。
- 生产环境请设置 `AUTO_LOTTERY_ENABLED=false` 并单独用定时任务调用抽签接口，或只保留一个 worker。
- 上线下前务必改掉 `ADMIN_PASSWORD` 与演示账号密码。
- 二维码地址由 `PUBLIC_BASE_URL` 决定，用 `localhost` 手机扫不出来，要换成局域网 IP 或域名。

## 常见问题

- **端口被占用**：`uvicorn app.main:app --port 8001`，同时把 `PUBLIC_BASE_URL` 的端口改成一致。
- **手机扫码打不开**：`PUBLIC_BASE_URL` 还是 `localhost`，改成局域网 IP 后重启。
- **`database is locked`**：SQLite 只允许单进程写入，确认没有同时跑多个实例。
- **切到 MySQL**：只改 `DATABASE_URL`，再 `pip install pymysql cryptography`，然后 `python init_db.py` 与 `python seed.py`。
- **改了 `.env` 不生效**：配置带缓存，重启服务即可。
- **想重置演示数据**：停止服务，删除 `app.db`、`app.db-shm`、`app.db-wal`，再执行 `python seed.py`。

## 参与贡献

欢迎提交改进，见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

## 许可

[MIT](LICENSE) —— 可自由用于个人与商业项目，保留版权声明即可。
