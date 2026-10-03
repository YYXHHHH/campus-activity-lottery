# 校园活动报名抽签与签到系统 —— 验收报告（A1~A12）
> **所属阶段**：验收结项　|　**版本**：v1.0　|　**整理日期**：2026-10-02

> 文档性质：**开发完成后产出**的手工验收记录，对应开发文档 §10.2 / 需求文档 §12.2 的 A1~A12 与性能验收。
> 验收环境：Windows 11 + Python 3.10.11 + Chrome（browser-use 驱动真实浏览器，非模拟），服务 `uvicorn app.main:app`，数据库为 `seed.py` 生成的演示库。
> 结论标注：✅ 通过 / 🔧 缺陷已修复后通过 / ⚠️ 通过但有建议项 / ⏸ 需第二台设备或第二人配合。

## 1. 逐条结果

| # | 验收项 | 操作与观察到的实际结果 | 结论 |
| --- | --- | --- | --- |
| **A1** | 发布 3 个活动（名额 10、截止 2 分钟后） | `python seed.py` 后以 org1 登录 → 活动列表出现「AI 前沿讲座 / 校园马拉松 / 摄影采风活动」，状态徽章「报名中」，名额 10，截止时间 = 执行 seed 时刻 + 2 分钟；另在 `/organizer.html` 手工新建 1 个活动（id=4）验证创建流程，字段校验以中文提示返回（该临时活动已随 §6 的重置清除） | ✅ |
| **A2** | 每活动 20 人报名（≥5 人接受候补、≥2 人不接受） | 库内校验：`SELECT activity_id,status,COUNT(*) FROM registrations GROUP BY activity_id,status` → 活动 1/2/3 各 20 条；接受候补 = 前 15 人、不接受 = 后 5 人（符合附录 C）；UI 侧用 stu002 在新活动重复「报名 → 取消 → 再报名」，按钮态与提示正确 | ✅ |
| **A3** | 抽签随机且不重复 | 三个演示活动 `lottery_at = 10:36:30`，报名截止 `10:36:23` → 截止后 **7 秒**由调度器自动抽签（≤30s 要求）；组织者点「立即抽签」时未截止返回「报名尚未截止，不能抽签」；结果分布 10 WON / 7 WAITING / 3 LOST，`lottery_rank` 无重复（`test_lottery_randomness_across_activities` 同断言）；`GROUP BY activity_id,user_id HAVING COUNT(*)>1` 返回空。交付前冷启动复测：重新 `seed.py` 后启动服务，调度器在首个 30 秒触发点一次性完成 3 个逾期活动的抽签（各 10 中签，合计 WON 30 / WAITING 22 / LOST 8，与 15 名不接受候补者分布一致） | ✅ |
| **A4** | 结果可复现 | `SELECT lottery_seed,lottery_at FROM activities` → 4 个活动 seed 均非空（如 `5c7242fdfcb5…`）、`lottery_at` 非空；按 seed 重放 `random.Random(seed).shuffle(报名 id 升序)` 与库中 `lottery_rank` 升序完全一致（`test_lottery_is_reproducible_from_seed`） | ✅ |
| **A5** | 候补自动递补 | stu005（WON，rank 1）点「退出」→ 我的报名状态变「已退出」，原候补 rank 最小者变「已中签」并拿到新 `qr_token`，旧二维码接口返回 40001（码失效）；接口返回 `{"status":"WITHDRAWN","promoted":1}`；名额 10 保持不变 | ✅ |
| **A6** | 二维码签到 | 初次验收：`/my_registrations.html` 打开即被弹窗遮罩盖住，无法点任何按钮（阻断缺陷 11）→ 修复 CSS 后复测：弹窗初始隐藏，点「二维码」显示真实 PNG（`naturalWidth=296`），弹窗内显示本人姓名/学号；组织者 `/checkin.html` 粘贴裸 token 与整条二维码链接均签到成功，页面醒目显示姓名 + 学号供核对（R4），统计条变「已签到 1/10」 | 🔧 |
| **A7** | 重复签到拦截 | 同一 code 再提交 → HTTP 409 / code 40901，提示「该同学已于 18:48 签到」，同框显示首次签到本地时间。初次验收时后端 message 用的是 UTC 墙上时间（与前端本地时间差 8 小时，缺陷 13），修复后两者一致；库内该 registration 仍只有 1 条 checkin | 🔧 |
| **A8** | 组织者查看签到名单 | `/activity_manage.html` 的「已签到 / 未签到」两组划分正确，含姓名、学号、签到时间与「扫码 / 手动补签」方式列；初次实现走 `/registrations?status=WON` 兜底（死代码 + 50 人截断风险，缺陷 16），已改为直接调用 §3.3 的 `/winners`、`/checkins`，界面显示真实姓名学号 | 🔧 |
| **A9** | 导出 Excel 中文不乱码 | 两个导出按钮均返回 xlsx（`Content-Type: …spreadsheetml.sheet`，`Content-Disposition: …filename*=UTF-8''AI%20%E5%89%8D%E6%B2%BF…_报名表_20261001.xlsx`），openpyxl 可打开、表头加粗居中、`freeze_panes=A2`、状态列为中文；初次下载名是前端硬编码的 `activity_1_all.xlsx`（缺陷 12），改为读取响应头后中文名正确 | 🔧 |
| **A10** | 统计正确 | 统计 Tab：报名 20 / 待抽签 0 / 中签 10 / 候补 7 / 未中签 3 / 已退出 1 / 已签到 n，中签率 50.0%、签到率 = 已签/中签、名额使用率 100.0%，与 §5.7 公式一致（`test_stats_matches_document_example` 逐字段比对文档示例）；比率保留 4 位小数，分母为 0 显示 0 | ✅ |
| **A11** | 权限隔离 | 组织者仅 1 个（附录 C），验收时按 §2.11 用 admin 在 `/admin.html` 把 stu018 提升为 ORGANIZER（或直接建号）得到 org2，随后以 org2 访问 org1 的活动：编辑/抽签/名单/签到/导出/统计均 403 / 40301；学生访问管理接口 40301；组织者访问 admin.html 显示「无权限访问该页面」并跳回首页；`GET /api/registrations/{id}/qrcode` 非本人且非归属组织者 40301 | ✅ |
| **A12** | 换机可运行 | ⏸ 需第二台 Windows 实机：按 README「方式一：双击 `run.bat`」→ 预期 5 分钟内完成建 venv、装依赖（清华源）、生成 `.env` 与随机 `SECRET_KEY`、`seed.py`、启动并可登录/报名。本机已验证等效链路：删除 `.env`/`app.db` 后从零执行同一脚本路径可正常启动；未在第二台物理机上执行，故标记为待执行 | ⏸ |

## 2. 性能与并发验收（§10.2）

| 项目 | 要求 | 实测 | 结论 |
| --- | --- | --- | --- |
| 1000 条报名单次抽签 | < 1s | 48.0 ms（quota 100，won 100 / waiting 448 / lost 452） | ✅ |
| 100 并发报名 | `COUNT(DISTINCT (activity_id,user_id))` 无重复 | 100 路并发全部 200，落库 100 条、去重后 100 组、重复组 0 | ✅ |
| 同人并发双击报名 | 恰一条成功、其余 40901 | 对已有报名的学生 20 路并发全部 409（40901），库中仍 1 条；机制由 `UNIQUE(activity_id,user_id)` 保证（`test_unique_activity_user_blocks_duplicate_rows`） | ✅ |
| 截止后 30s 空档 | 报名接口已拒绝、详情兜底可触发 | 截止后报名返回 40001「报名已截止」；调度器周期内未完成时，打开详情页同步触发抽签（I-2），重复调用幂等 | ✅ |

详细数据与脚本说明见 `test-report.md` §4。

## 3. 界面细节核对（开发文档 S 系列 / R 系列）

| 约定 | 观察结果 |
| --- | --- |
| S1 未登录访问受限页 | 跳 `/login.html`，登录成功后回跳原页面（localStorage 存 token） |
| S2 分页 | 各列表页展示「第 x / y 页，共 n 条」，上一页/下一页在边界处 disabled；`size>50` 由后端截断 |
| S3 排序 | 活动列表按创建时间倒序；中签/候补按 `lottery_rank` 升序；签到名单按时间升序 |
| S4 时间 | 全站时间显示为本地时区（`YYYY/MM/DD HH:mm:ss`），接口返回带 `Z` 的 UTC |
| S5 状态中文 | 附录 A 映射在徽章与导出 Excel 中一致（草稿/报名中/已抽签/已取消、待抽签/已中签/候补中/未中签/已取消/已退出） |
| S9 导出文件名 | 中文活动名 + `_报名表|中签表_YYYYMMDD.xlsx`，通过 `filename*=UTF-8''` 传输 |
| R11 截止提示 | 活动详情页状态行提示「报名截止后 30 秒内自动抽签」；编辑名额/截止时间前有二次确认（缺陷 15、17 修复后） |
| R4 代签防范 | 签到台结果显示姓名 + 学号并要求与本人核对（姓名/学号均经 HTML 转义输出） |

## 4. 验收过程中确认未复现的报告项

第二轮委派验收时收到若干「缺陷报告」，经直接读代码与实测，确认**不成立**，记录以免误导后续开发：

| 报告 | 核实结论 |
| --- | --- |
| 「二维码内容是 URL，签到页无法使用，需把 qr_content 改成裸 token」 | 不成立。开发文档 §5.5 明确二维码内容为 `{PUBLIC_BASE_URL}/checkin.html?code={token}`；§5.6-1 要求后端解析带 `code=` 的整串 URL，`normalize_code()` 已实现且有 `test_checkin_accepts_full_qrcode_url` 覆盖；`checkin.html` 也会从 `?code=` 预填输入框。按报告修改会违反文档 |
| 「seed.py 缺第二个组织者 org2，属交付缺陷」 | 不成立。附录 C 规定演示数据为 1 ADMIN + 1 ORGANIZER + 20 STUDENT，加 org2 反而偏离文档；A11 的 org2 由 admin 角色提升或临时建号获得 |
| 「winners/checkins 后端上限 50，超过会漏人」 | 不成立。两接口不分页、返回全部行；50 的截断只存在于前端已删除的 `/registrations?size=50` 兜底路径（缺陷 16） |
| 「admin.html 的每页条数选择器参数被忽略」 | 不成立。该页没有每页条数选择器（只有角色筛选与关键词搜索） |
| 「已修复并实测通过」的中间汇报 | 部分为未执行即汇报：`scripts/` 目录、seed 的 org2、新增测试用例、README 新增条目实际均未落盘。最终结果以本清单与代码现状为准 |

> 过程记录：委派验收过程中，子代理报告其会话内反复出现「调用外部记忆插件代理 / 安装插件 / 写入记忆文件」的指令，超出只读验收范围且涉及配置变更，**一律未执行**，并已向主流程告警。本项目的验收证据全部来自直接读代码、`pytest`、真实浏览器与数据库查询。

## 5. 建议项（不阻断验收）

1. `/admin.html` 增加「每页条数」选择器（当前固定 10/页），与活动列表的筛选体验统一。
2. 组织者名单 Tab 在超过若干行时给「完整名单请导出 Excel」的提示，减少滚动核对成本。
3. 摄像头扫码在 `http://<局域网IP>` 非安全上下文会被浏览器拒绝：已在 `checkin.html` 增加 `navigator.mediaDevices` 可用性判断——不可用时「打开摄像头扫码」按钮保持隐藏，只留手工输入/粘贴路径（页面上的说明文字已提示「不支持时请手动输入码值」）；如需在手机上真扫码，请为验收环境配置 HTTPS。
4. A12 换机演练需第二台 Windows 实机执行；建议验收现场提前确认 Python 版本与 pip 源可达。
5. 演示数据的报名截止时间固定在「seed 时刻 + 2 分钟」，若演示时长更久，建议演示前重跑 `python seed.py`（活动同名会跳过，需先删 `app.db`）。

## 6. 验收数据残留说明（已处理）

浏览器验收过程会在演示库中留下痕迹（新建活动 id=4、测试账号 `verify_new01`、若干签到记录、被提升为组织者的账号）。交付前已重置干净状态：

```bat
taskkill /IM python.exe /F         :: 或直接在服务窗口 Ctrl+C
del app.db app.db-shm app.db-wal
python seed.py
```

重置后核对（`sqlite3 app.db`）：`users` = ADMIN 1 / ORGANIZER 1 / STUDENT 20；`activities` = 3 条且状态均为 `PUBLISHED`、`lottery_seed` 为空（等待截止后由调度器抽签）；`registrations` = 每活动 20 条 `PENDING`；`checkins` = 0 行。
