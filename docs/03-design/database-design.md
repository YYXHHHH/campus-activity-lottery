# 校园活动报名抽签与签到系统 —— 数据库设计说明书（DBD）

> **所属阶段**：系统设计（数据）　|　**版本**：v1.0　|　**整理日期**：2026-10-02
> **内容来源**：《开发文档》§4 数据结构设计；《需求与设计文档》§8.3、§8.5。
> **编号说明**：本文章节编号沿用来源文档，以便与《开发文档》《需求与设计文档》交叉检索。

---
## 4. 数据结构设计

### 4.1 实体关系

```
users 1───N activities       (organizer_id)
users 1───N registrations
activities 1───N registrations  (ON DELETE CASCADE)
registrations 1───1 checkins    (registration_id UNIQUE, CASCADE)
users 1───N checkins            (operator_id，可为空)
```

### 4.2 表结构 DDL（SQLite 方言，MySQL 迁移注意项见 §8）

```sql
CREATE TABLE users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  username      VARCHAR(50)  NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  real_name     VARCHAR(50)  NOT NULL,
  role          VARCHAR(20)  NOT NULL DEFAULT 'STUDENT',
  email         VARCHAR(120) NULL,
  phone         VARCHAR(20)  NULL,
  is_active     SMALLINT     NOT NULL DEFAULT 1,
  created_at    DATETIME     NOT NULL,
  updated_at    DATETIME     NOT NULL
);
CREATE INDEX ix_users_role ON users(role);

CREATE TABLE activities (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  organizer_id    INTEGER      NOT NULL REFERENCES users(id),
  title           VARCHAR(100) NOT NULL,
  description     TEXT         NULL,
  location        VARCHAR(200) NOT NULL,
  start_time      DATETIME     NOT NULL,
  end_time        DATETIME     NULL,
  signup_deadline DATETIME     NOT NULL,
  quota           INTEGER      NOT NULL,
  status          VARCHAR(20)  NOT NULL DEFAULT 'DRAFT',
  lottery_seed    VARCHAR(64)  NULL,
  lottery_at      DATETIME     NULL,
  created_at      DATETIME     NOT NULL,
  updated_at      DATETIME     NOT NULL,
  CHECK (quota >= 1)
);
CREATE INDEX ix_act_status_deadline ON activities(status, signup_deadline);
CREATE INDEX ix_act_organizer ON activities(organizer_id);

CREATE TABLE registrations (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  activity_id     INTEGER     NOT NULL
                  REFERENCES activities(id) ON DELETE CASCADE,
  user_id         INTEGER     NOT NULL REFERENCES users(id),
  status          VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  accept_waitlist SMALLINT    NOT NULL DEFAULT 1,
  lottery_rank    INTEGER     NULL,
  qr_token        VARCHAR(64) NULL UNIQUE,
  created_at      DATETIME    NOT NULL,
  updated_at      DATETIME    NOT NULL,
  UNIQUE (activity_id, user_id)
);
CREATE INDEX ix_reg_act_status ON registrations(activity_id, status);
CREATE INDEX ix_reg_user       ON registrations(user_id);
CREATE INDEX ix_reg_rank ON registrations(activity_id, status, lottery_rank);

CREATE TABLE checkins (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  registration_id INTEGER     NOT NULL UNIQUE
                  REFERENCES registrations(id) ON DELETE CASCADE,
  activity_id     INTEGER     NOT NULL REFERENCES activities(id),
  user_id         INTEGER     NOT NULL REFERENCES users(id),
  operator_id     INTEGER     NULL REFERENCES users(id),
  checkin_code    VARCHAR(64) NULL,
  method          VARCHAR(20) NOT NULL DEFAULT 'SCAN',
  checked_in_at   DATETIME    NOT NULL
);
CREATE INDEX ix_checkin_act  ON checkins(activity_id);
CREATE INDEX ix_checkin_user ON checkins(user_id);
```

可选表（P1，建议预留表结构但 MVP 不写数据）：`audit_logs`（id/user_id/action/target_type/target_id/detail JSON/created_at），在抽签、递补、导出、签到四处埋点。

### 4.3 字段设计要点

| 字段 | 设计意图 |
| --- | --- |
| `registrations.qr_token` UNIQUE | 退出/取消即置 NULL 使码失效；UNIQUE 防止重复签发的碰撞被静默接受 |
| `registrations (activity_id, user_id)` UNIQUE | 防重复报名的最终防线，并发下的唯一正确保证 |
| `registrations.lottery_rank` | 同一活动内唯一（应用层保证）；同时是候补递补顺序依据 |
| `checkins.registration_id` UNIQUE | 数据库层防重复签到 |
| `activities.lottery_seed` + `lottery_at` | 审计复现：用同 seed 重建 `random.Random(seed).shuffle` 可得到相同名单 |
| `checkins.checkin_code` | 存实际提交的码（截断 64），便于排查"贴错码"问题 |

### 4.4 ORM 实现要点

1. 枚举用 `str, enum.Enum`（`ActivityStatus`、`RegistrationStatus`），`mapped_column(SAEnum(...), native_enum=False, length=20)`——MySQL 关闭原生 ENUM，便于迁移。
2. `utcnow` 为模块级函数（`datetime.now(timezone.utc)`），作 `default=` / `onupdate=`；**禁止** `default=datetime.utcnow`（Python 3.12+ 已弃用且为 naive 时间）。
3. 关系：`Registration.checkin`（`relationship(uselist=False, cascade="all, delete-orphan")`）、`Activity.registrations`；列表接口必须用 `joinedload/selectinload` 预加载，禁止循环内再查询。
4. `Boolean` 映射 `accept_waitlist`（SQLite 落 SMALLINT 0/1，MySQL 落 TINYINT(1)）。

### 4.5 数据完整性保障汇总

| 保障目标 | 机制 | 层级 |
| --- | --- | --- |
| 防重复报名 | UNIQUE(activity_id, user_id) + 前置查询 + IntegrityError→40901 | DB+应用 |
| 抽签只生效一次 | 条件 UPDATE `WHERE status='PUBLISHED'`，rowcount=0 即放弃 | DB+应用 |
| 防重复签到 | checkins.registration_id UNIQUE + 前置查询 | DB+应用 |
| 退出与递补原子 | 同一事务 commit/rollback | 应用事务 |
| 名额不被超发 | 名额改小校验 + 递补以 `quota - won_count` 差额为限 | 应用 |

---

## 附录　可选表与时间约定（来源：需求与设计文档 §8.3、§8.5）

### 8.3 可选表（P1，建议预留）
```sql
-- 操作审计日志
CREATE TABLE audit_logs (
id         INTEGER PRIMARY KEY AUTOINCREMENT,
user_id    INTEGER NULL,
action     VARCHAR(50) NOT NULL,   -- LOTTERY / PROMOTE / CHECKIN / EXPORT ...
target_type VARCHAR(30) NULL,      -- ACTIVITY / REGISTRATION
target_id  INTEGER NULL,
detail     TEXT NULL,              -- JSON 字符串
created_at DATETIME NOT NULL
);
```

### 8.5 时间与时区约定
- 后端统一使用 **UTC** 存储（`datetime.now(timezone.utc)`）；
- API 出入参使用 ISO 8601 字符串（带 `Z` 或 `+00:00`）；
- 前端展示时通过 `new Date(iso).toLocaleString('zh-CN')` 转本地时间；
- 所有「是否截止」判断在服务端进行，不信任前端时间。
---
