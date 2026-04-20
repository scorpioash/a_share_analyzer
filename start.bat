@echo off
chcp 65001 >nul
echo ======================================
echo     启动 极简 A股 智能分析器 (Web)
echo ======================================

:: 1. 检查 Python 环境
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] 错误: 未找到 Python环境，请先安装 Python 3.8及以上版本并配置环境变量。
    pause
    exit /b
)

:: 2. 创建虚拟环境
if not exist "venv\" (
    echo [+] 正在为您创建 Python 虚拟环境...
    python -m venv venv
)

:: 3. 激活虚拟环境
call venv\Scripts\activate.bat

:: 4. 安装更新依赖
echo [+] 正在安装或校验依赖环境...
python -m pip install --upgrade pip -q -i http://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
pip install -r requirements.txt -i http://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn -q

:: 5. 配置文件预处理
if not exist ".env" (
    echo [+] 未检测到 .env，自动从模板创建...
    copy .env.example .env >nul
    echo [!] 请注意: 初次启动！请务必在生成好的 .env 文件中填入您的 API KEY。
)

:: 6. 启动 Web 界面
echo [+] 正在启动 Web 服务器，请保持此窗口开启...
streamlit run 首页.py
pause
