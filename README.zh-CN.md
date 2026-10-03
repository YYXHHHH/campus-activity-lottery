# 校园活动报名抽签与签到系统

面向校园场景的活动报名、随机抽签、候补递补、二维码签到与数据统计系统。
后端 FastAPI + SQLAlchemy + SQLite（可切 MySQL），前端原生 HTML/CSS/JS，免构建工具。
实现依据：`docs/03-design/detailed-design.md`（由开发文档整理），本 README 对应其 §11 部署章节。

## 环境要求

- Windows 10 / 11（其他系统按「手动方式」执行等价命令即可）
- Python 3.10 / 3.11，安装时勾选 **Add Python to PATH**（开发文档规定运行环境为 3.11；本项目实测 3.10.11 下依赖安装、服务运行与 78 个测试用例全部通过）
- 浏览器 Chrome / Edge 最新版

## 快速开始

### 方式一：一键脚本（推荐）

1. 解压 / 克隆项目，进入目录
2. 双击 `run.bat`（演示与验收模式：单进程、无 `--reload`、自动抽签开启）
   - 开发改代码时用 `run.bat dev`（`--reload` 热重载，脚本会自动关闭定时抽签，避免调度器双实例）
3. 浏览器打开 <http://localhost:8000>

脚本会自动完成：创建 `.venv` → 安装依赖（清华源）→ 由 `.env.example` 生成 `.env` 并写入随机 `SECRET_KEY` → `python seed.py` → 启动服务。

### 方式二：手动执行

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
copy .env.example .env
python -c "import secrets;print(secrets.token_hex(32))"   :: 用输出替换 .env 里的 SECRET_KEY
python seed.py
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 默认账号（`seed.py` 生成，附录 C）

| 角色 | 用户名 | 密码 | 说明 |
| --- | --- | --- | --- |
| 管理员 | `admin` | `admin123` | 取自 `.env` 的 `ADMIN_USERNAME/ADMIN_PASSWORD`，可管理用户角色与启用状态 |
| 组织者 | `org1` | `123456` | 拥有 3 个演示活动 |
| 学生 | `stu001` ~ `stu020` | `123456` | 每个活动 20 条报名，前 15 人接受候补 |

演示活动的报名截止时间 = **执行 `seed.py` 的时刻 + 2 分钟**，截止后 30 秒内由调度器自动抽签；也可用组织者账号在「活动管理」页手动点击抽签。

## 页面入口

| 页面 | 地址 | 角色 |
| --- | --- | --- |
| 登录 / 注册 | `/login.html`、`/register.html` | 公开 |
| 活动列表、活动详情与报名 | `/index.html`、`/activity_detail.html?id=<id>` | 学生 |
| 我的报名（含二维码） | `/my_registrations.html` | 学生 |
| 创建活动 | `/organizer.html` | 组织者 / 管理员 |
| 活动管理（名单 / 抽签 / 递补 / 签到 / 统计 / 导出） | `/activity_manage.html?id=<id>` | 组织者本人 / 管理员 |
| 签到台（扫码结果 / 按学号补签） | `/checkin.html` | 组织者本人 / 管理员 |
| 用户管理 | `/admin.html` | 管理员 |

接口在线文档：<http://localhost:8000/api/docs>（Swagger）、<http://localhost:8000/redoc>。

## 局域网访问与手机扫码

启动后同网段电脑用 `http://<本机IP>:8000` 访问。
**手机扫二维码要能打开签到页**，必须把 `.env` 中的 `PUBLIC_BASE_URL` 改为局域网可达地址后重启：

```ini
PUBLIC_BASE_URL=http://192.168.1.20:8000
```

二维码内容为 `{PUBLIC_BASE_URL}/checkin.html?code=<qr_token>`，二维码接口返回 PNG 且带 `Cache-Control: no-store`（签到码不得缓存）。

## 运行测试

```bat
.venv\Scripts\activate
python -m pytest tests\
```

78 个用例基于内存 SQLite（`StaticPool`）运行，不触碰 `app.db`；覆盖开发文档 §10.1 全部清单，
并额外包含 §4.5 数据库唯一约束、§4.3 seed 复现抽签、§10.2「1000 条报名抽签 < 1s」性能验收。

## 常见问题

- **端口被占用**：`uvicorn app.main:app --host 0.0.0.0 --port 8001`（同时把 `PUBLIC_BASE_URL` 端口改成一致）。
- **扫出来的二维码打不开**：`PUBLIC_BASE_URL` 仍是 `http://localhost:8000`，手机访问不到本机，改为局域网 IP。
- **启动报 `SECRET_KEY 未配置或使用了示例值`**：`SECRET_KEY` 长度不足 16 或仍为示例值，用
  `python -c "import secrets;print(secrets.token_hex(32))"` 生成后写入 `.env`（R9）。
- **不要用 `--reload` 或多 worker 做演示/验收**：会导致 APScheduler 双实例重复抽签。单进程单 worker 是部署红线（R2）；
  代码层已有条件 UPDATE 原子占位作为最后防线，但仍应遵守部署规范。
- **`database is locked`**：已启用 WAL + `timeout=30` + 退避重试装饰器；若仍出现，确认没有多进程同时写同一个 `app.db`（R1）。
- **passlib 关于 bcrypt 的告警**：`passlib==1.7.4` 与 `bcrypt==4.1.3` 已双锁定，**禁止单独升级任一**，否则历史密码哈希失配（R5）。
- **切换 MySQL**：只改 `.env`，代码零改动（R7 注意 `CHECK(quota>=1)` 在旧 MySQL 不生效，应用层已校验）：

  ```ini
  DATABASE_URL=mysql+pymysql://root:password@127.0.0.1:3306/activity_lottery?charset=utf8mb4
  ```

  然后 `pip install pymysql cryptography`、`python init_db.py`、`python seed.py`。
- **重置演示数据**：停止服务，删除 `app.db`（及 `-shm/-wal`），再执行 `python seed.py`。
- **日志**：控制台 + 同目录 `app.log`，抽签 / 递补 / 签到 / 导出均写 INFO（§7.3）。

## 目录结构

```
app/                # 后端（config/database/models/schemas/security/deps/errors/main + routers + services + scheduler）
static/             # 前端页面（原生 HTML/CSS/JS）
tests/              # pytest 用例（§10.1）
docs/               # 软件开发过程文档集（按阶段分目录，总索引见 docs/README.md）
scripts/            # 文档构建工具（Markdown → Word）
seed.py             # 演示数据初始化（幂等）
init_db.py          # 独立建表脚本
run.bat             # Windows 一键启动（demo / dev 两种模式）
.env.example        # 配置模板（.env 不入库）
```

## 文档索引

文档按软件开发生命周期分阶段存放，仅保留 Markdown 源（Word 版按需由 `scripts/md_to_docx.py` 生成）；总索引见 [docs/README.md](docs/README.md)：

- 项目计划：`docs/01-project-plan/`（项目开发计划、软件质量保证计划、软件配置管理计划）
- 需求分析：`docs/02-requirements/`（需求规格说明书）
- 系统设计：`docs/03-design/`（概要设计、详细设计、数据库设计、接口设计说明书）
- 编码实现：`docs/04-implementation/`（实现说明）
- 测试验证：`docs/05-testing/`（测试计划、测试报告）
- 部署运维：`docs/06-deployment/`（部署运行手册、用户操作手册）
- 验收结项：`docs/07-acceptance/`（验收报告、项目总结报告）
- 过程归档：`docs/99-archive/`（过程记录）
- 文档构建：`scripts/md_to_docx.py`、`scripts/verify_docx.py`
