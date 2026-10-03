# 贡献指南

欢迎提交改进：修 bug、补测试、完善文档、把模板适配到更多场景都算。

## 开发环境

```bash
git clone https://github.com/YYXHHHH/campus-activity-lottery.git
cd campus-activity-lottery
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # 填入随机 SECRET_KEY
python seed.py
uvicorn app.main:app --reload --port 8000
```

## 提交前自检

```bash
python -m pytest                   # 78 项用例应全部通过
```

- 改了接口或模型 → 同步更新 `tests/` 与 README 的「关键实现约定」；
- 改了术语或品牌 → 同步更新 `app/branding.py` 与 README 的「可覆盖的术语键名」表；
- 新增配置项 → 补进 `.env.example` 与 README 的配置项说明表；
- 保持「零构建前端」的约束：不引入 npm 依赖与打包步骤。

## 代码约定

- 面向用户的一切文案走术语表（`LABELS` / `UI_LABELS`），不在 HTML、JS 里写死站名；
- 业务规则放 `app/services/`，路由层只做参数、权限与响应组装；
- 时间统一 UTC 存储、本地展示；错误统一抛 `app/errors.py` 的异常族；
- 数据库变更后删除本地 `app.db*` 重建（模板不含迁移工具）。

## 提交信息

用一句话说清"改了什么、为什么"，例如：

```
fix(lottery): 修复名额增加时未递补候补的问题
docs: 补充 MySQL 切换步骤
```

## 提交 PR

1. Fork 后从 `main` 切出分支，命名如 `fix/lottery-waitlist`；
2. 确保 `python -m pytest` 全绿；
3. PR 描述里写清动机、改动范围与验证方式（附截图更好）。
