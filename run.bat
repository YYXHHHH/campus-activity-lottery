@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem 用法：
rem   run.bat        演示 / 验收模式（单进程、无 --reload，自动抽签开启）
rem   run.bat dev    开发模式（--reload 热重载，自动抽签关闭，避免调度器双实例）
set MODE=%1
if "%MODE%"=="" set MODE=demo

if not exist .venv (
  echo [1/5] 创建虚拟环境 .venv ...
  python -m venv .venv
)
call .venv\Scripts\activate.bat

echo [2/5] 安装 / 校验依赖（清华镜像源）...
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

if not exist .env (
  echo [3/5] 首次运行：由 .env.example 生成 .env，并写入随机 SECRET_KEY ...
  copy .env.example .env >nul
  python -c "import re,secrets,pathlib;p=pathlib.Path('.env');s=re.sub(r'SECRET_KEY=.*','SECRET_KEY='+secrets.token_hex(32),p.read_text(encoding='utf-8'));p.write_text(s,encoding='utf-8')"
) else (
  echo [3/5] 已存在 .env，沿用本地配置
)

echo [4/5] 初始化数据库与演示数据（幂等，可重复执行）...
python seed.py

if /I "%MODE%"=="dev" (
  echo [5/5] 开发模式启动：http://localhost:8000  （--reload 会加载两次应用，已关闭自动抽签）
  set AUTO_LOTTERY_ENABLED=false
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
) else (
  echo [5/5] 演示 / 验收模式启动：http://localhost:8000  （Ctrl+C 停止）
  uvicorn app.main:app --host 0.0.0.0 --port 8000
)

endlocal
