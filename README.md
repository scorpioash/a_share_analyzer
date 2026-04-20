# 📈 A 股全维度智能投研终端

覆盖 **行情 · 资金 · 板块 · 基本面 · 资讯 · 情绪** 六大维度，辅以 AI 深度推演，为你打造一站式 A 股投研决策中枢。

## 📌 核心功能一览

| 模块 | 说明 |
|------|------|
| 🔍 智能诊股 | 输入股票名称或代码，AI 自动拉取全维度数据，结合你的个人策略给出深度研判 |
| 📊 板块分析 | 搜索行业/概念板块，自动拆解子板块，AI 推演板块轮动机会 |
| 📈 行情中心 | 主板、创业板、科创板、北交所全市场实时行情数据 |
| 🔥 盘口异动 | 涨跌停股池、盘中异动信号捕捉、板块异动监控 |
| 📋 财务数据 | 业绩快报/预告、机构调研详情 |
| 📰 资讯中心 | 7×24 全球财经快讯（可点击跳转原文）、个股新闻查询 |
| 🐉 龙虎榜 | 每日龙虎榜全量数据、全市场资金流向排行 |
| 👥 股东研究 | 十大流通股东变动、股东户数趋势 |
| 🏷️ 板块大盘 | 全量行业/概念板块实时排名 |
| 🌡️ 市场情绪 | 股票热度排行榜、全市场赚钱效应温度计 |

> [!TIP]
> **💡 模型选择建议**：金融市场犹如没有硝烟的战场，盘面研判极其考验 AI 的逻辑推理深度。为了让本系统输出最敏锐、最准确的操作建议，**强烈建议搭配使用 Claude4.6 或 ChatGPT5.4 等顶级旗舰模型**。
> 
> **⚠️ 免责声明**：本系统所有的行情推演及 AI 回复仅仅作为技术的代码测试与个人的逻辑复盘，完全不构成任何投资建议，切莫盲从盲信。股市有风险，交易需谨慎！

---

## 🚀 从零开始部署（保姆级教程）

### 第一步：安装 Python 环境

本项目需要 Python 3.8 或更高版本。如果你的电脑上还没有安装 Python，请按以下步骤操作：

**Windows 用户：**
1. 打开浏览器，访问 [Python 官方下载页](https://www.python.org/downloads/)
2. 点击黄色的 **"Download Python 3.x.x"** 按钮下载安装包
3. 双击运行安装包，**⚠️ 一定要勾选底部的 "Add Python to PATH"（把 Python 添加到环境变量）**
4. 然后一路点 "Next"、"Install" 直到安装完成

**Mac 用户：**
1. 打开「终端」应用（在启动台搜索"终端"即可找到）
2. 输入以下命令安装 Homebrew（如果已安装可跳过）：
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```
3. 然后输入：
   ```bash
   brew install python
   ```

**如何验证安装成功？**
- Windows：按 `Win + R`，输入 `cmd` 回车，在黑框中输入 `python --version`
- Mac：打开终端，输入 `python3 --version`
- 如果显示 `Python 3.x.x` 就说明安装成功了

---

### 第二步：下载本项目

**方法 A（推荐新手）：直接下载压缩包**
1. 在本项目的 GitHub 页面，点击绿色的 **"Code"** 按钮
2. 选择 **"Download ZIP"**
3. 下载完成后，右键解压到你喜欢的目录（比如桌面）

**方法 B：使用 Git 克隆**
```bash
git clone <本项目的 GitHub 地址>
```

---

### 第三步：一键启动！

**Windows 用户：**
1. 打开解压后的项目文件夹
2. 找到 `start.bat` 文件，**双击运行**
3. 第一次运行会自动安装所有依赖（需要等待 1-2 分钟，期间不要关闭黑框窗口）
4. 如果黑框中出现 `Email:` 提示，**直接按回车键跳过**即可
5. 安装完成后，浏览器会自动打开 `http://localhost:8501`

**Mac / Linux 用户：**
1. 打开终端，`cd` 进入项目目录
2. 执行以下命令：
   ```bash
   chmod +x start.sh
   ./start.sh
   ```
3. 同样等待依赖安装完成，浏览器会自动打开

---

### 第四步：配置你的 AI 模型

启动成功后，你会看到网页界面。接下来需要配置一个 AI 模型才能使用诊股功能：

1. 点击左侧边栏的 **"🔑 快捷配置 API"** 展开配置面板
2. 在 **"选择驱动引擎"** 中选择你的模型厂商：
   - **ChatGPT (OpenAI)**：需要 [OpenAI 官网](https://platform.openai.com/api-keys) 注册并生成 API Key
   - **Claude (Anthropic)**：需要 [Anthropic 官网](https://console.anthropic.com/) 注册并获取 Key
   - **Gemini (Google)**：需要 [Google AI Studio](https://aistudio.google.com/apikey) 获取 Key
   - **自定义 (OpenAI 协议)**：适用于 DeepSeek、OneAPI 中转站等所有兼容 OpenAI 格式的服务商。需要手动填入 API URL 和模型名
3. 填入 **API KEY** 和 **模型名**
4. 点击 **"保存配置并重载"**
5. 配置完成！现在可以前往「智能诊股」或「板块分析」页面开始使用了

---

### 第五步（可选）：定制你的投资策略

项目根目录下有两个策略文件，你可以用任何文本编辑器打开并编写你的投资经验和纪律：

- **`my_strategy.md`**：个股分析策略。AI 诊股时会严格参照这里的经验给出评级
- **`my_board_strategy.md`**：板块分析策略。AI 分析板块时会参照这里的方法论

> 写得越详细、越贴合你自己的交易风格，AI 给出的建议就越"懂你"。

---

## 🐳 Docker 部署（适合有服务器的用户）

如果你想挂在 NAS 或云服务器上做 24 小时私人投研工作站：

```bash
# 1. 克隆项目
git clone <本项目的 GitHub 地址>
cd a_share_analyzer

# 2. 一键后台启动
docker-compose up -d

# 3. 浏览器访问
# http://<你的服务器IP>:8501
```

然后同样在网页左侧边栏配置 API 即可。修改策略文件后无需重启容器，AI 会自动读取最新内容。

---

## 🤖 GitHub Actions 自动推送（无需服务器）

如果你希望每天收盘后自动分析并推送到飞书/微信：

1. Fork 本仓库到你的 GitHub 账号
2. 进入你 Fork 后的仓库 → `Settings` → `Secrets and variables` → `Actions`
3. 添加以下配置变量：
   - `OPENAI_API_KEY`：你的模型 API Key
   - `FEISHU_WEBHOOK_URL`：飞书机器人的 Webhook 地址
   - `STOCK_LIST`：想跟踪的股票代码，如 `600519`
4. 搞定！每个交易日下午 16:00 会自动运行诊断并推送结果

---

## 📁 项目结构

```
a_share_analyzer/
├── 首页.py                  # 主入口文件（启动后的首页）
├── data_fetcher.py          # 数据抓取引擎（AkShare 接口封装）
├── llm_analyzer.py          # AI 分析引擎（多模型适配）
├── my_strategy.md           # 你的个股投资策略（可自定义）
├── my_board_strategy.md     # 你的板块分析策略（可自定义）
├── pages/                   # 各功能页面
│   ├── 1_🔍_智能诊股.py
│   ├── 2_📊_板块分析.py
│   ├── 3_📈_行情中心.py
│   ├── 4_🔥_盘口异动.py
│   ├── 5_📋_财务数据.py
│   ├── 6_📰_资讯中心.py
│   ├── 7_🐉_龙虎榜与资金流.py
│   ├── 8_👥_股东研究.py
│   ├── 9_🏷️_板块大盘.py
│   └── 10_🌡️_市场情绪与热度.py
├── start.bat                # Windows 一键启动脚本
├── start.sh                 # Mac/Linux 一键启动脚本
├── requirements.txt         # Python 依赖清单
├── .env                     # API 配置文件（自动生成）
└── .env.example             # 配置文件模板
```
