# 使用轻量级 Python 镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 设置时区为上海，确保系统时间正确
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 复制依赖配置并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 把整个项目拷贝进容器
COPY . .

# 暴露 Streamlit 的默认端口
EXPOSE 8501

# 启动网页端分析界面
ENTRYPOINT ["streamlit", "run", "web_ui.py", "--server.port=8501", "--server.address=0.0.0.0"]
