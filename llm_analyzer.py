import os
from dotenv import load_dotenv

load_dotenv()

class LLMAnalyzer:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai").lower()
        self.strategy_content = self._load_strategy()

    def _load_strategy(self):
        strategy_path = os.path.join(os.path.dirname(__file__), "my_strategy.md")
        if os.path.exists(strategy_path):
            with open(strategy_path, "r", encoding="utf-8") as f:
                return f.read()
        return "请分析以下A股数据并给出操作建议。"

    def _load_board_strategy(self):
        strategy_path = os.path.join(os.path.dirname(__file__), "my_board_strategy.md")
        if os.path.exists(strategy_path):
            with open(strategy_path, "r", encoding="utf-8") as f:
                return f.read()
        return "请分析以下A股板块数据并给出操作建议。"

    def analyze(self, data_context: str) -> str:
        """调用选定的大模型进行总结分析"""
        system_prompt = (
            "你是我的专业级 A 股分析助理。请严格根据下方我的个人投资策略与铁律进行判读。\n\n"
            f"=== 个人炒股策略与经验铁律 ===\n{self.strategy_content}\n"
            "==============================\n"
        )
        
        user_prompt = (
            f"以下是该股的最新全维度数据（含量价走势、财务估值、新闻面、资金流向、"
            f"十大股东、盈利预测、主营构成、融资融券、龙虎榜、股东户数、长波段历史记忆、大宗与回购、个股热度等）：\n\n"
            f"{data_context}\n\n"
            "请输出你的结论结构：\n"
            "1. 行情与盘面趋势诊断（请务必结合K线均线、【第11点的长线历史缩影】以及【静默技术指标榜单】分析股价面临的极值变盘点）\n"
            "2. 资金与情绪面（必须结合资金流向、游资龙虎榜、【第13点的全市场散户热度排行】来推演多空博弈）\n"
            "3. 基本面深度解读（结合估值、主营、盈利预测、股东变化及大宗回购动作）\n"
            "4. 消息面提炼\n"
            "5. 最终评级建议（必须在规则限定词内）\n\n"
            "## 🔮 短线盘感预测 (Next T+3)\n"
            "### 1. ⚡️ 下一交易日（明日）瞻望\n"
            "   - **方向预测**：[📈 看多 / 📉 看空 / ↔️ 震荡]\n"
            "   - **预期走势**：[例如：低开高走、缩量回踩、冲高回落等]\n"
            "   - **明日博弈核心**：[指出明天最重要的支撑位/压力位或资金关注点]\n"
            "### 2. 📅 T+3 趋势合力推演\n"
            "   - **方向与胜率**：[📈/📉/↔️ (置信度 %)]\n"
            "   - **未来三日逻辑**：[简述支撑此趋势的宏观/产业/大逻辑]\n"
            "### 3. 🛡️ 风控与止盈建议\n"
            "   - **参考止损位**：[具体价格]\n"
            "   - **期望止盈位**：[具体价格]"
        )

        if self.provider == "anthropic":
            return self._call_anthropic(system_prompt, user_prompt)
        elif self.provider == "gemini":
            return self._call_gemini(system_prompt, user_prompt)
        else:
            # 默认均走 openai 标准格式 (支持 OpenAI, DeepSeek, 月之暗面 等等)
            return self._call_openai_compatible(system_prompt, user_prompt)

    def _call_openai_compatible(self, system_prompt: str, user_prompt: str) -> str:
        from openai import OpenAI
        
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        model = os.getenv("OPENAI_MODEL", "gpt-4o")

        client = OpenAI(api_key=api_key, base_url=base_url)
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"OpenAI/DeepSeek 调用失败: {e}"

    def _call_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        from anthropic import Anthropic
        
        api_key = os.getenv("ANTHROPIC_API_KEY")
        model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

        client = Anthropic(api_key=api_key)
        try:
            response = client.messages.create(
                model=model,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=2048,
                temperature=0.3
            )
            # Claude python sdk returns a list of text blocks
            return response.content[0].text
        except Exception as e:
            return f"Anthropic 调用失败: {e}"

    def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
        try:
            # 使用较新的 google-genai 库
            from google import genai
            from google.genai import types
            
            api_key = os.getenv("GEMINI_API_KEY")
            model = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
            
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.3,
                )
            )
            return response.text
        except Exception as e:
            return f"Gemini 调用失败: {e}"

    def analyze_board(self, data_context: str, board_name: str) -> str:
        """专门用于板块分析的方法，带有板块拆解推理链路的提示词"""
        # 加载板块专属策略文件
        board_strategy = self._load_board_strategy()
        
        system_prompt = (
            "你是我的专业级 A 股板块轮动分析师。请严格根据下方我的个人板块分析策略与铁律进行判读。\n\n"
            f"=== 个人板块分析策略与经验铁律 ===\n{board_strategy}\n"
            "==============================\n"
        )

        user_prompt = (
            f"以下是关于【{board_name}】板块的最新数据（含主板块走势、成分股数据、今日龙虎榜席位活跃度、**板块技术极值统计**、以及通过成分股重叠度"
            f"反向发现的关联细分子板块）：\n\n{data_context}\n\n"
            "请严格按照以下结构输出你的【深度硬核】分析报告：\n\n"
            "## 🔴 一、板块拆解推理链（核心部分）\n"
            f"请展示你极为详细、充满逻辑深度的推理思维过程。**拒绝泛泛而谈，禁止使用‘板块向好’、‘值得关注’等废话**。请必须从【{board_name}】这个大板块出发，进行“剥洋葱”式的层层递进拆解。具体要求如下：\n"
            "1. **大逻辑梳理**：详细剖析当前该大板块炒作的底层核心驱动力（如：重仓该板块的某全球龙头业绩超预期、核心国产替代节点被攻克、某项颠覆性技术的物理局限被突破等）。\n"
            "2. **产业链全景映射**：必须按上、中、下游或不同技术流派（如：HBM 与 CoWoS 封装、低空飞行器主机厂与空管系统等）进行全方位的扫描评估。\n"
            "3. **逻辑与资金的共振点**：根据实时数据中发现的关联子板块（看重叠比例和规模）和成分股异动，并结合你庞大的 A 股历史炒作记忆库，找出本轮博弈逻辑最硬、资金承接力最强的 1-2 条‘真命天子’支线。\n"
            "4. **剥洋葱式推导过程展现**（请务必按照下方的箭头结构，展现你每一层的演进推理）：\n"
            f"   - **顶级层**：【{board_name}】总闸门开启（详细说明启动的信号是什么）\n"
            "     → **[进入中层细分产业链]**（深度推演：为什么资金要在此处切换？是基本面确定性最高，还是估值弹性最大？请给出毛利率或量产进度层面的充分逻辑支撑）\n"
            "     → **[进入底层最小可投资单元]**（绝杀推演：资金最终锁定哪个细分节点？是因为它属于‘独家供应’的喉咙位，还是属于‘逻辑外推性’最强的卡位点？）\n\n"
            "## 🔵 二、主板块走势深度诊断\n"
            "结合今日的技术面极值统计数据，分析板块整体是在‘加速冲顶’还是‘缩量洗盘’。请明确指出板块是否存在集体性质的技术陷阱或整体性溢价机会。\n\n"
            "## 🟣 三、细分方向横向赛马\n"
            "对比上述关联子板块的实时表现，指出哪个赛道具有‘领涨气质’，哪个赛道存在‘补涨预期’，哪个赛道目前是‘存量博弈下的诱多陷阱’。\n\n"
            "## 🟢 四、终极操作决议\n"
            "给出确定性的操作立场（极度看好/谨慎潜伏/清仓回避），并点出 1-2 只最值得放入‘猛龙观察池’的实战成分股以及推荐它们的硬核心逻辑。\n\n"
            "## 🔮 板块短线轮动预测\n"
            "### 1. ⚡️ 明日（次日）轮动瞻望\n"
            "   - **活跃度预判**：[🔥 走强 / ❄️ 走弱 / ⏳ 蓄势]\n"
            "   - **明日博弈核心**：[指出明天该板块是否会受到大盘影响，或者有特定的分时博弈点]\n"
            "### 2. 📅 T+3 轮动节奏推演\n"
            "   - **方向与胜率**：[📈/📉/↔️ (置信度 %)]\n"
            "   - **未来三日逻辑**：[简述该板块在接下来三个交易日内的轮动地位（是主线延续还是超跌反弹？）]"
        )

        if self.provider == "anthropic":
            return self._call_anthropic(system_prompt, user_prompt)
        elif self.provider == "gemini":
            return self._call_gemini(system_prompt, user_prompt)
        else:
            return self._call_openai_compatible(system_prompt, user_prompt)

if __name__ == "__main__":
    analyzer = LLMAnalyzer()
    print("模型已配置为:", analyzer.provider)
