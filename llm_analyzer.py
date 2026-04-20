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
            "5. 最终评级建议（必须在规则限定词内）。"
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
            f"以下是关于【{board_name}】板块的最新数据（含主板块走势、成分股、以及通过成分股重叠度"
            f"反向发现的关联细分子板块）：\n\n{data_context}\n\n"
            "请严格按照以下结构输出你的分析报告：\n\n"
            "## 一、板块拆解推理链\n"
            f"请展示你的推理思维过程：从【{board_name}】这个大板块出发，根据上述数据中发现的"
            "关联子板块和成分股的交叉关系，**逐步推导出最值得关注的 2-3 个细分子板块**，"
            "并说明每一步推理的逻辑依据。\n"
            "格式示例：\n"
            f"  {board_name} → [子板块A]（因为xxx） → [更细分方向]（因为xxx）\n\n"
            "## 二、主板块走势诊断\n"
            "分析主板块近期的量价趋势、强弱信号。\n\n"
            "## 三、细分方向对比\n"
            "对比各个关联子板块的走势强弱，指出哪个细分赛道当前最具爆发潜力或最危险。\n\n"
            "## 四、操作建议\n"
            "给出最终的板块级别操作策略（关注/观望/回避），并指出最值得重点跟踪的 1-2 只成分股标的。"
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
