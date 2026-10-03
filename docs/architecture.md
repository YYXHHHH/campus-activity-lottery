# 架构说明

## 分层

```
static/*.html + js/api.js + js/app.js     浏览器：原生 JS，无构建
        │  fetch /api/*  （Bearer token）
        ▼
app/routers/*        路由层：参数校验、权限依赖、组装响应
        │
app/services/*       业务层：抽签、报名与候补、签到、统计、导出
        │
app/models.py        数据层：SQLAlchemy 2.0 声明式模型
        │
SQLite / MySQL
```

横切关注点：

- `app/config.py`：配置与品牌设置，启动时校验 `SECRET_KEY`；
- `app/branding.py`：界面术语表与模板注入上下文；
- `app/deps.py`：`get_current_user`、`require_role`、`assert_activity_owner` 等权限依赖；
- `app/errors.py`：`BizError` 异常族 + 统一 `{code, message, data}` 响应包装；
- `app/database.py`：引擎、会话、分页工具（`build_page`、`clamp_page`）、`utcnow`；
- `app/scheduler.py`：APScheduler 周期扫描到期活动，逐个委托抽签，单个失败不影响其他。

## 响应约定

所有接口统一返回信封：

```json
{ "code": 0, "message": "ok", "data": {} }
```

`code` 非 0 表示业务错误，HTTP 状态码同步设置（如 401 未登录、403 无权限、409 冲突）。前端 `static/js/api.js` 统一解包：`code === 0` 取 `data`，`40101` 自动清理登录态并跳登录页。

## 抽签的公平性与幂等

`app/services/lottery.py` 的三条关键设计：

1. **状态前置校验**：仅 `PUBLISHED` 且已过报名截止的活动可抽签，手动强制抽签仅管理员可用；
2. **原子占位**：用条件 `UPDATE` 把活动从 `PUBLISHED` 改为 `LOTTERY_DONE`，只有抢到这次更新的请求才会继续抽签，天然防并发重复抽签；
3. **可复现随机**：`lottery_seed` 落库，用「种子 + 报名 ID」派生的固定顺序打乱，任何人拿同一份数据都能复算出同一结果，便于事后审计与争议复核。

候补递补（`app/services/registration.py`）与抽签共用同一事务，退出或增加名额时立即按 `lottery_rank` 递补，避免出现名额空置。

## 时间与时区

- 数据库统一存 **UTC 朴素时间**（`utcnow()`）；
- 前端 `<input type="datetime-local">` 取本地时间，提交前由 `App.toUtcIso()` 转成带 `Z` 的 ISO 字符串；
- 展示时用 `App.fmtTime()` 转回本地时间。

## 签到防重

`Checkin` 表对 `registration_id` 建唯一约束，重复签到不报错而是返回首次签到时间（幂等）；二维码内容为 `{PUBLIC_BASE_URL}/checkin.html?code=<qr_token>`，接口同时接受完整 URL 与裸码值。

## 测试策略

- 用例基于内存 SQLite（`StaticPool`）+ `TestClient`，不触碰本地 `app.db`；
- `tests/helpers.py` 提供 `make_user` / `login` / `admin_session` / `register` 等构造器，让用例聚焦业务断言；
- 覆盖点包括：权限矩阵、抽签分布与幂等、候补递补、签到防重、统计口径、导出内容、分页边界，以及 1000 人抽签的性能回归（< 1 秒）。
