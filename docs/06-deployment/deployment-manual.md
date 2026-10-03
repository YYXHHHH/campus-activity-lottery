# 校园活动报名抽签与签到系统 —— 部署运行手册
> **所属阶段**：部署运维　|　**版本**：v1.0　|　**整理日期**：2026-10-02

> 文档性质：**开发完成后产出**的运行/部署/排障手册，面向「换一台 Windows 机器 5 分钟内跑起来」的验收目标（开发文档 R12、A12）。
> 与 `README.md` 的分工：README 面向使用者的快速开始，本手册面向部署与故障定位，含端口/密钥/数据库/并发/日志的具体核对项。

## 1. 环境要求与核对

| 项 | 要求 | 核对命令 |
| --- | --- | --- |
| 操作系统 | Windows 10/11（Linux/macOS 同命令，去掉 `.venv\Scripts` 反斜杠） | `ver` |
| Python | 3.11 推荐（实测 3.10 亦可），安装时勾选 Add Python to PATH | `python --version` |
| 磁盘 | 项目 < 50 MB + `.venv` 约 150 MB + `app.db` | — |
| 端口 | 8000（可改） | `netstat -ano \| findstr :8000` |
| 浏览器 | Chrome / Edge 最新版 | — |

依赖清单固定于 `requirements.txt`（与开发文档 §1.4 一致）。**不要单独升级 `passlib` 或 `bcrypt`**（R5：两者版本耦合，升级会导致历史密码哈希失配/告警）。

## 2. 首次部署（推荐：一键脚本）

```bat
cd /d D:\path\to\Practice_1
run.bat
```

`run.bat` 顺序执行且每一步幂等，可重复运行：

1. 无 `.venv` 则 `python -m venv .venv`，并 `activate`
2. `pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`
3. 无 `.env` 则由 `.env.example` 复制，并自动用 `secrets.token_hex(32)` 写入随机 `SECRET_KEY`
4. `python seed.py`（附录 C 演示数据，已存在的用户/活动跳过）
5. `uvicorn app.main:app --host 0.0.0.0 --port 8000`（**单进程、无 `--reload`**）

开发模式：`run.bat dev` → 带 `--reload` 且脚本内 `set AUTO_LOTTERY_ENABLED=false`。
原因：`--reload` 会加载两次应用、产生两个调度器实例，导致重复抽签（R2）。演示与验收**禁止**使用 dev 模式。

## 3. 手动部署（脚本不可用时的等价步骤）

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
copy .env.example .env
python -c "import secrets;print(secrets.token_hex(32))"     :: 输出粘贴到 .env 的 SECRET_KEY
python init_db.py                                           :: 建表（可跳过，启动时自动建）
python seed.py
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

启动核对（四项全绿即成功）：

```bat
curl http://127.0.0.1:8000/api/health
```

```json
{"code":0,"message":"ok","data":{"app":"校园活动抽签系统","status":"up"}}
```

2. 浏览器打开 `http://localhost:8000/login.html`，用 `org1 / 123456` 能进「活动管理」；
3. `app.log` 末尾出现 `[main] 自动抽签调度已启动，周期 30 秒`；
4. 首次运行出现的一行 `trapped error reading bcrypt version`（passlib 1.7.4 读 bcrypt 4.1.3 版本号的已知告警，**已被 passlib 捕获，哈希与登录功能正常**，可忽略 —— R5）。

## 4. 配置项详解（`.env`）

| 键 | 默认 | 作用 | 改动后必须 |
| --- | --- | --- | --- |
| `APP_NAME` | 校园活动抽签系统 | 标题与健康检查字段 | 重启 |
| `SECRET_KEY` | 无（**必填**） | JWT HS256 密钥 | 长度 ≥16 且不能是示例值，否则启动即 `RuntimeError`（R9）；改值会使全部旧 token 失效 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 1440 | token 有效期（分钟） | 重启 |
| `DATABASE_URL` | `sqlite:///./app.db` | 数据库连接 | 见 §5 |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | 二维码内容前缀 | **手机扫码必须改为局域网 IP**，见 §6 |
| `AUTO_LOTTERY_INTERVAL_SECONDS` | 30 | 调度扫描周期 | 重启；截止后最多延迟该秒数出结果 |
| `AUTO_LOTTERY_ENABLED` | true | 是否注册调度任务 | 开发用 `--reload` 时设为 false |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | admin / admin123 | `seed.py` 创建的管理员 | 改名后旧 admin 不会自动出现（按用户名幂等） |
| `BCRYPT_ROUNDS` | 12 | 密码哈希强度 | 仅在压测/造数时调低（测试用 4）；生产保持 12 |

`.env` 含密钥，已在 `.gitignore` 中排除；仓库只提交 `.env.example`。

## 5. 数据库

### 5.1 SQLite（默认）

- 文件：`app.db`（+ `app.db-wal`、`app.db-shm`），已在 `.gitignore`。
- 首次连接自动执行 `PRAGMA journal_mode=WAL` 与 `PRAGMA busy_timeout=30000`（§5.9-1）。
- 备份 = 复制 `app.db`（建议先停服务，或复制三件套）。
- 重置演示数据：停服务 → 删 `app.db*` → `python seed.py`。
- 迁移 MySQL 后 SQLite 文件即废弃，不发生自动数据迁移。

### 5.2 切换 MySQL 8（代码零改动）

```ini
DATABASE_URL=mysql+pymysql://root:yourpass@127.0.0.1:3306/activity_lottery?charset=utf8mb4
```

```bat
pip install pymysql cryptography
```

建库：`CREATE DATABASE activity_lottery DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;`
然后 `python init_db.py` + `python seed.py`。

迁移注意（开发文档 R7、§4.2）：
- `CHECK (quota >= 1)` 在部分 MySQL 版本不生效 → 应用层 `quota < 1` 校验已兜底（40001）。
- `SMALLINT`/`BOOLEAN`：`is_active`/`accept_waitlist` 由 SQLAlchemy 统一映射，无需改数据。
- 枚举列使用 `native_enum=False`（存 VARCHAR(20)），换库不会出现残留的 MySQL ENUM 类型。
- 字符集必须 `utf8mb4`，否则中文活动名/姓名截断。
- 切库后跑全量回归：`python -m pytest tests\`。
- `promote_waitlist` 的 `with_for_update()` 仅在 MySQL 方言下附加（§5.3 的行锁语义在 SQLite 由写锁串行替代）。

## 6. 局域网访问与手机扫码（高频踩坑）

1. 查本机 IPv4：`ipconfig`（取 `192.168.x.x`，不要选 `127.0.0.1`）。
2. 改 `.env`：`PUBLIC_BASE_URL=http://192.168.1.20:8000`，**重启服务**。
3. 学生端「我的报名 → 二维码」重新打开页面获取新码（二维码内容带前缀，改前生成的截图仍指向 localhost）。
4. 手机与电脑需同一网段；Windows 首次监听 0.0.0.0 会弹防火墙提示，允许「专用网络」入站，或手动放行 8000 端口：
   `netsh advfirewall firewall add rule name="activity8000" dir=in action=allow protocol=TCP localport=8000`
5. 组织者签到台在同一页面显示姓名/学号，供人工核对防止转发代签（R4）。

排障：扫码 404 → `PUBLIC_BASE_URL` 与实际访问地址不一致；扫码打不开 → 防火墙或不同网段；签到页显示「签到码无效」→ 该生已退出/被取消（`qr_token` 已置 NULL）。

## 7. 并发与进程模型（部署红线）

| 规则 | 原因 |
| --- | --- |
| **单进程、单 worker、不加 `--reload`** | 多实例 → APScheduler 多份 → 重复抽签风险（R2）；SQLite 写锁竞争（R1） |
| 不做多机负载均衡 | 状态存于本地 SQLite；扩容需先切 MySQL 并考虑调度器独占 |
| 压测时保持单进程 | 100 并发报名的正确性依赖 `UNIQUE(activity_id,user_id)` + WAL，应用层前置查询只是友好提示（§4.5） |

已实现的并发保护：抽签条件 UPDATE 原子占位；报名/签到 `IntegrityError → 40901`；`retry_on_locked`（50/100/200ms 退避，最多 3 次）用于报名、扫码签到、手动补签。

## 8. 日志与可观测

- 位置：控制台 + 项目根 `app.log`（UTF-8）；只读目录自动降级为仅控制台。
- 格式：`{时间} {级别} [{模块}] {事件} key=value`（§7.3）。
- 必记 INFO：`[lottery] 抽签完成 activity_id/seed/won/waiting/lost`、`[lottery] 候补递补 activity_id/promoted_user_ids/count`、`[checkin] 签到成功 activity_id/user_id/operator_id/method`、`[export] 导出 activity_id/type/row_count/operator_id`、`[admin] 修改用户`、`[main] 自动抽签调度已启动`。
- 异常一律 `logger.exception`（含堆栈），响应仍走统一 `500/50001`。
- 观察抽签是否完成：`GET /api/activities/{id}/stats` 的 `lottery_at`，或活动详情 `status/lottery_status_cn`。
- 抽签审计复现：取 `activities.lottery_seed`，按 `registration.id` 升序列表 + `random.Random(seed).shuffle` 即可重放名单（§4.3，测试 `test_lottery_is_reproducible_from_seed` 已验证）。

## 9. 定时抽签的时间语义

- 判定式：`utcnow() < signup_deadline` 为「仍可报名」（S4），等于即截止。
- 触发路径三条，全部收敛到 `run_lottery`：调度器每 `AUTO_LOTTERY_INTERVAL_SECONDS`（默认 30s）、组织者手动、活动详情兜底（I-2）。
- 因此「截止后最多 30 秒出结果」，即使调度器异常，任何人打开该活动详情页都会同步补上（幂等，重复调用返回 `executed=false`）。
- 全链路 UTC（R3）：服务器时钟须为正确本地时间（换算由系统完成），代码不使用 `datetime.utcnow()`。

## 10. 故障排查速查表

| 症状 | 首查 | 处理 |
| --- | --- | --- |
| 启动即 `RuntimeError: SECRET_KEY 缺失或为示例值` | `.env` 是否存在、值是否被替换 | `python -c "import secrets;print(secrets.token_hex(32))"` 写入后重启 |
| `Address already in use` | `netstat -ano \| findstr :8000` | 换端口 `--port 8001`（同步改 `PUBLIC_BASE_URL`），或结束旧进程 |
| 登录 500 / `unknown CryptContext keyword` | 是否单独升级了 passlib/bcrypt | 重装：`pip install -r requirements.txt --force-reinstall` |
| `trapped error reading bcrypt version` 一行告警 | 已知 R5 现象 | 可忽略，功能正常；勿升级 bcrypt |
| 报名偶发 500 `database is locked` | 是否多进程共享 `app.db` | 保证单进程；确认 WAL 生效（`app.db-wal` 存在）；仍复现则切 MySQL |
| 活动到点不抽签 | `AUTO_LOTTERY_ENABLED`、`app.log` 有无 job 运行记录 | 重启服务；或组织者手动点「抽签」（幂等安全） |
| 中签名单/候补显示空白 | 前端是否用了 `/winners`、`/checkins` | 见 `acceptance-report.md` 缺陷记录 |
| 导出文件名乱码 | 浏览器地址栏/下载名 | 已由 `filename*=UTF-8''` 处理（R6）；IE 系走 `filename=export.xlsx` 兜底 |
| 手机打不开二维码 | `PUBLIC_BASE_URL` | 见 §6 |
| 换机装不上依赖 | pip 源与 Python 版本 | 用脚本内的清华源；离线环境先 `pip download -r requirements.txt -d wheels` |

## 11. 停止与升级

- 停止：服务窗口 `Ctrl+C`（触发 `scheduler.shutdown(wait=False)`）。
- 升级代码：备份 `app.db` 与 `.env` → 覆盖代码 → `.venv\Scripts\activate && pip install -r requirements.txt` → `python seed.py`（幂等）→ `python -m pytest tests\` 回归 → `run.bat`。
- 表结构变更（MVP 未引入迁移工具）：开发文档 §4 未要求 Alembic。新增列时需手工 `ALTER TABLE` 或备份后重建库再导入数据。
