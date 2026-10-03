# 定制指南

把模板改成你自己的系统，通常只需要四步。按改动成本从低到高排列。

## 一、换站名与主题色（只改 `.env`）

```dotenv
APP_NAME=会议室预约系统
BRAND_NAME=会议室预约系统
BRAND_SHORT_NAME=会议室预约
BRAND_COLOR=#0f766e          # 任意 #rrggbb，hover 深色自动派生
```

改完**重启服务**即生效（配置有缓存）。生效位置：

| 位置 | 取值来源 |
| --- | --- |
| 浏览器标题、登录页大标题、接口文档标题 | `BRAND_NAME` |
| 导航栏左侧站名 | `BRAND_SHORT_NAME` |
| 按钮 / 链接 / 选中态颜色 | `BRAND_COLOR`（由 `/api/brand.css` 覆盖 `--primary`） |

## 二、换界面术语（只改 `.env`，无需动 HTML）

术语表定义在 [`app/branding.py`](../app/branding.py) 的 `LABELS`，可用 `UI_LABELS` 覆盖任意项：

```dotenv
UI_LABELS={"activity.list_title":"会议室列表","activity.unit":"会议室","user.student":"申请人"}
```

常用键名：

| 键 | 默认值 | 出现位置 |
| --- | --- | --- |
| `app.tagline` | 报名 · 抽签 · 签到 | 登录页副标题 |
| `activity.list` | 活动列表 | 导航栏、页面标题 |
| `activity.list_title` | 校园活动 | 首页大标题 |
| `activity.unit` | 活动 | 各处文案 |
| `activity.mine_registrations` | 我的报名 | 导航栏、页面标题 |
| `activity.mine_managed` | 我的活动 | 导航栏、页面标题 |
| `activity.manage` | 活动管理 | 导航栏、页面标题 |
| `activity.detail` | 活动详情 | 页面标题 |
| `checkin.title` / `checkin.onsite` | 扫码签到 / 现场签到 | 签到页 |
| `user.list` | 用户管理 | 导航栏、页面标题 |
| `user.student` / `user.organizer` / `user.admin` | 学生 / 组织者 / 管理员 | 角色下拉框、导航栏身份 |

状态徽章文案单独定义在 `app/branding.py` 的 `STATUS_LABELS`、`REGISTRATION_STATUS_LABELS`、`ROLE_LABELS`，键名与 `app/models.py` 的枚举值一致。

### 品牌注入的三条通道

改品牌时不需要自己接线，三条通道已打通：

1. **服务端渲染**：`app/main.py` 的 `TemplateStaticFiles` 让所有 `.html` 走 Jinja2，页面里可直接写 `{{BRAND_NAME}}`、`{{BRAND_SHORT}}`、`{{LABELS['activity.unit']}}`；
2. **前端运行时**：`/api/brand.js` 注入 `window.__BRAND__`（含 `labels`、`status_labels`、`role_labels`），`static/js/app.js` 据此渲染导航栏、徽章与角色下拉框；
3. **外部接口**：`GET /api/meta` 返回同一份 JSON，供小程序、App 或第三方前端调用。

> Windows 上静态文件路径会带反斜杠，`TemplateStaticFiles.get_path()` 已统一归一为 `/`，并为根路径补上 `index.html`。

## 三、改数据模型（改业务的核心）

以「把活动改成会议室预约」为例：

1. **模型**：编辑 `app/models.py`。比如给 `Activity` 加 `room_id`、`capacity`，或新增 `Room` 表与该表的关联；
2. **校验与出入参**：同步改 `app/schemas.py`（Pydantic 模型负责字段长度、取值范围等校验）；
3. **接口**：改 `app/routers/*.py`。业务规则尽量下沉到 `app/services/`（`lottery` / `registration` / `checkin` / `stats` / `exporter`），路由只做参数与权限编排；
4. **重建数据库**：模板**不含迁移工具**。开发期直接删除 `app.db`、`app.db-shm`、`app.db-wal`，重启后由 `create_all()` 重建；已有线上数据再考虑引入 Alembic；
5. **演示数据**：改 `seed.py`，保持幂等（先查后插），方便反复执行；
6. **测试**：改 `tests/helpers.py` 的公共构造器，再逐个修 `tests/test_*.py`。

改模型时容易漏的三处：`app/schemas.py` 的字段约束、`app/services/stats.py` 的统计口径、`static/js/app.js` 里状态徽章到 CSS 类的映射。

## 四、加减页面

新增一个页面：

1. 在 `static/` 新建 `xxx.html`，头部照抄现有页面：`css/style.css` + `api/brand.css` + `api/brand.js`；
2. 页面脚本里调用 `App.initPage({ page: 'xxx.html', roles: ['ADMIN'] })`，它会渲染导航栏、校验登录态与角色；
3. 若要在导航栏出现，编辑 `static/js/app.js` 的 `NAV_ITEMS`，填 `href`、`labelKey`（术语键）与 `roles`；
4. 需要新接口就在 `app/routers/` 加路由，并在 `app/main.py` 里 `include_router`。

不需要的页面直接删除文件，同时从 `NAV_ITEMS` 里去掉对应项即可。

## 五、去掉演示内容

- `seed.py`：演示账号与三个演示活动，改成你自己的初始数据，或直接不执行；
- `examples/`：与模板核心无关的参考实现，可整目录删除；
- `tests/`：建议保留框架（`conftest.py`、`helpers.py`）后按业务重写断言；
- `.env` 里的 `ADMIN_PASSWORD` 与演示密码：上线前必须改掉。

## 六、切换到 MySQL / 生产部署

```dotenv
DATABASE_URL=mysql+pymysql://root:password@127.0.0.1:3306/activity_lottery?charset=utf8mb4
```

```bash
pip install pymysql cryptography
python init_db.py
python seed.py
```

生产注意：**单进程单 worker**（调度器在进程内，多进程会重复抽签）；更稳妥的做法是设 `AUTO_LOTTERY_ENABLED=false`，用系统定时任务在服务外触发抽签接口。
