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

    def analyze(self, data_context: str) -> str:
        """调用选定的大模型进行总结分析"""
        system_prompt = (
            "你是我的专业级 A 股分析助理。请严格根据下方我的个人投资策略与铁律进行判读。\n\n"
            f"=== 个人炒股策略与经验铁律 ===\n{self.strategy_content}\n"
            "==============================\n"
        )
        
        user_prompt = f"以下是该股的最新的量价与基本面数据：\n\n{data_context}\n\n请输出你的结论结构：\n1. 盘面诊断\n2. 基本面/消息面解读\n3. 最终评级建议（必须在规则限定词内）。"

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

if __name__ == "__main__":
    analyzer = LLMAnalyzer()
    print("模型已配置为:", analyzer.provider)
