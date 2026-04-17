#!/bin/bash
# 跨平台启动脚本 (Linux / macOS)

echo "======================================"
echo "    启动 极简 A股 智能分析器 (Web)"
echo "======================================"

# 1. 检查 Python 环境
if ! command -v python3 &> /dev/null
then
    echo "[!] 错误: 未找到 Python3，请先安装 Python 3.8+环境"
    exit 1
fi

# 2. 创建隔离的虚拟环境 (如果不存在)
if [ ! -d "venv" ]; then
    echo "[+] 正在为您创建 Python 虚拟环境..."
    python3 -m venv venv
fi

# 3. 激活虚拟环境
source venv/bin/activate

# 4. 安装/更新依赖
echo "[+] 正在安装或校验依赖环境..."
pip install --upgrade pip -q
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple -q

# 5. 配置文件预处理
if [ ! -f ".env" ]; then
    echo "[+] 未检测到 .env，自动从模板创建..."
    cp .env.example .env
    echo "[!] 请注意: 初次启动！请确保稍后在 .env 文件中填入您的 API KEY"
fi

# 6. 启动 Web 界面
echo "[+] 正在启动 Web 服务器，端口 8501 待命..."
streamlit run web_ui.py
