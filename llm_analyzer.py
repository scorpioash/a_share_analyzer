import os
import time
import logging
from datetime import datetime
from typing import Iterator, Optional
from dotenv import load_dotenv

load_dotenv()

# -----------------------------------------------------------------------
# 日志配置：打印 token 使用量、重试、错误
# -----------------------------------------------------------------------
logger = logging.getLogger("LLMAnalyzer")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# -----------------------------------------------------------------------
# 自定义异常：调用方可据此区分是真正的错误还是正常输出
# -----------------------------------------------------------------------
class LLMCallError(Exception):
    "「」大模型调用失败异常「」"
    pass


class LLMAnalyzer:
    # 默认配置
    DEFAULT_MAX_TOKENS = 8192
    DEFAULT_TEMPERATURE_STRATEGY = 0.3   # 策略/估值分析 —— 求稳
    DEFAULT_TEMPERATURE_PREDICT = 0.5    # 盘感预测 —— 放一点创造性
    MAX_RETRIES = 3
    RETRY_BACKOFF_BASE = 1.5             # 指数退避 1.5s, 2.25s, 3.37s ...

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai").lower()
        self.strategy_content = self._load_strategy()
        logger.info(f"LLMAnalyzer 初始化完成，Provider = {self.provider}")

    # ------------------------------------------------------------------
    # 策略文件加载
    # ------------------------------------------------------------------
    def _load_strategy(self) -> str:
        strategy_path = os.path.join(os.path.dirname(__file__), "my_strategy.md")
        if os.path.exists(strategy_path):
            with open(strategy_path, "r", encoding="utf-8") as f:
                return f.read()
        return "请分析以下A股数据并给出操作建议。"

    def _load_board_strategy(self) -> str:
        strategy_path = os.path.join(os.path.dirname(__file__), "my_board_strategy.md")
        if os.path.exists(strategy_path):
            with open(strategy_path, "r", encoding="utf-8") as f:
                return f.read()
        return "请分析以下A股板块数据并给出操作建议。"

    # ------------------------------------------------------------------
    # Prompt 构造
    # ------------------------------------------------------------------
    def _build_stock_system_prompt(self) -> str:
        return (
            "你是我的专业级 A 股分析助理。请严格根据下方我的个人投资策略与铁律进行判读。\n\n"
            "### 🚨 避雷红线（最高优先级）：\n"
            "1. **严禁推荐 ST 或 *ST 股票**：如果在数据中看到股票名称带有 ST 标识，或我标记了 ⚠️，"
            "必须将其视为「极高风险」标的，严禁将其作为买入或观察建议。\n"
            "2. **垃圾股隔离与认知修正**：如果你根据内部知识认为某股票很有潜力，但当前数据标注为 ST，"
            "**请不要怀疑数据，必须判定你的内部知识已过时**，该股已沦为地雷，必须在结论中明确拒绝推荐并点出退市风险。\n\n"
            "### 📅 时间锚点与数据处理原则：\n"
            f"**今日确切日期是 {datetime.now().strftime('%Y-%m-%d %H:%M')}**。\n\n"
            "**第一原则：有什么数据用什么数据，不因部分缺失而全面拒绝分析。**\n"
            "数据包里 `## 0.` 节会告知你当前数据可用性状态:\n"
            "  - `🚨 实时极值通告`: 实时盘口可用,按数据做盘中分析\n"
            "  - `ℹ️ 实时盘口不可用 (K线/资讯等其他数据正常)`: 实时缺失,但 **K 线、资讯、板块仍可信**,"
            "应基于 K 线完整分析趋势/均线/形态/基本面,仅回避今日具体价位\n"
            "  - `❌ 数据抓取全面失败`: 此时才大幅降级,给出风险提示框架\n\n"
            "**第二原则:明确区分盘中实时数据与历史 K 线数据,两者状态独立。**\n"
            "  - K 线由腾讯源提供,几乎总是可用;实时盘口由东财/新浪提供,可能短时抖动\n"
            "  - 即使实时盘口缺失,你依然可以基于 K 线给出:多头/空头排列判断、"
            "均线位置(MA5/10/20 数据包里已算好)、阻力/支撑位、趋势结构、变盘点识别\n"
            "  - **你必须给出明确的操作结论**,不得以『数据不全』为由全面拒绝分析。这是我的硬性要求。\n\n"
            "**第三原则:盘中时段的表述规范**\n"
            "  - 若有实时数据: 按数据包给出的『当前价』分析,用『截至 XX:XX 现价 X.XX』\n"
            "  - 若实时数据缺失: 用『最近一个交易日收盘 X.XX』或『截至最近收盘』,"
            "**不要凭空编造今日价格/涨跌幅/分时节奏**\n"
            "  - 均线/阻力/支撑位数值**必须**使用数据包 `## 0.` 节给出的动态计算值,不得凭记忆给\n\n"
            "**第四原则:数据可用时,强制使用**\n"
            "  - `## 0.` 节若提供了『动态阻力位/支撑位/MA5/MA10/MA20』等具体数值,"
            "你必须在分析中直接引用这些数值,不得说『均线数据未知』\n"
            "  - K 线表最后一行若带 `(今日最新实盘)` 标识,其数据即是今日盘中真实峰值,优先权高于任何记忆\n\n"
            "**第五原则:【最高指令】严格遵守内置量化模型信号**\n"
            "  - 数据包中会提供【内置量化动能策略打分】或类似板块周期判定。\n"
            "  - 你的结论方向（看多/看空/空仓）必须 100% 服从量化信号。若量化建议清仓，你绝不能建议逢低买入。\n"
            "  - **关键红线：在输出报告时，绝对禁止出现“锋泽”、“锋泽策略”、“外部模型”等词汇。必须将这些量化结果包装为“本系统测算”或自然融合在你的分析中。**\n\n"
            f"=== 个人炒股策略与经验铁律 ===\n{self.strategy_content}\n"
            "==============================\n"
        )

    def _build_stock_user_prompt(self, data_context: str) -> str:
        return (
            f"以下是该股的数据包(含量价走势、今日分时采样、财务估值、新闻面、资金流向、龙虎榜、"
            f"股东户数、长波段历史记忆、大宗与回购、个股热度等,**部分数据可能缺失,以数据包实际内容为准**):\n\n"
            f"{data_context}\n\n"
            "请输出你的结论结构。**每一节都必须给出明确判断,即便某些数据缺失也要基于可得数据给出专业分析**,"
            "只在完全没有任何相关数据时才说明『此维度数据不可得』。\n\n"
            "1. **行情与盘面趋势诊断**: 结合 K 线均线(数据包已给 MA5/10/20 数值),"
            "分析股价的趋势结构与极值变盘点。如有今日分时则一并分析盘中节奏,没有则跳过不提。\n"
            "2. **资金与情绪面**: 基于数据包里的资金流向、龙虎榜、热度排行等可得数据推演多空博弈,"
            "数据缺失时可从成交量变化、K 线形态侧面推断。\n"
            "3. **基本面深度解读**: 结合数据包里的估值、主营、股东变化等数据。数据缺失时可基于行业"
            "与公司基本画像给出定性判断,并明确标注『需补充最新财报数据验证』。\n"
            "4. **消息面提炼**: 基于数据包里的资讯。\n"
            "5. **最终评级建议**(必须给出,在规则限定词内): 基于以上综合可得数据做结论。\n\n"
            "## 🔮 短线盘感预测 (Next T+3)\n"
            "### 1. ⚡️ 下一交易日(明日)瞻望\n"
            "   - **方向预测**:[📈 看多 / 📉 看空 / ↔️ 震荡]\n"
            "   - **预期走势**:[例如:低开高走、缩量回踩、冲高回落等]\n"
            "   - **明日博弈核心**:[指出明天最重要的支撑位/压力位,"
            "数值使用数据包里已算好的阻力/支撑/均线,不得凭空捏造]\n"
            "### 2. 📅 T+3 趋势合力推演\n"
            "   - **方向与胜率**:[📈/📉/↔️ (置信度 %)]\n"
            "   - **未来三日逻辑**:[简述支撑此趋势的宏观/产业/大逻辑]\n"
            "### 3. 🛡️ 风控与止盈建议\n"
            "   - **参考止损位**:[具体价格]\n"
            "   - **期望止盈位**:[具体价格]"
        )

    def _build_board_system_prompt(self) -> str:
        board_strategy = self._load_board_strategy()
        return (
            "你是我的专业级 A 股板块轮动分析师。请严格根据下方我的个人板块分析策略与铁律进行判读。\n\n"
            "### 🚨 避雷红线(最高优先级):\n"
            "1. **板块池剔除 ST**:在「猛龙观察池」中,严禁推荐任何带有 ST 或 *ST 标识的垃圾股,"
            "即便它们是该板块目前的领涨代表。**如果领涨股带有 ⚠️ 标识,请绝对禁止推荐,并明确告知用户此标的已爆雷**。\n"
            "2. **认知对抗指令**:绝对禁止依赖你内部对某只绩优股的过时记忆。如果数据包将其标注为 ST,"
            "则必须采信实时数据,将其判定为避雷对象,并寻找该板块内财务健康的非 ST 核心中坚力量作为替代推荐。\n"
            "3. **【最高指令】严格遵守内置量化模型信号**：\n"
            "  - 你的结论必须 100% 服从数据包提供的【内置量化情绪周期判定】（如主升期、退潮期等）。\n"
            "  - **关键红线：在输出报告时，绝对禁止出现“锋泽”、“锋泽策略”、“外部模型”等词汇。必须将这些量化结果包装为“本系统测算”或自然融合在你的分析中。**\n\n"
            f"=== 个人板块分析策略与经验铁律 ===\n{board_strategy}\n"
            "==============================\n"
        )

    def _build_board_user_prompt(self, data_context: str, board_name: str) -> str:
        return (
            f"以下是关于【{board_name}】板块的最新数据(含主板块走势、成分股数据、今日龙虎榜席位活跃度、"
            f"**板块技术极值统计**、以及通过成分股重叠度反向发现的关联细分子板块):\n\n{data_context}\n\n"
            "请严格按照以下结构输出你的【深度硬核】分析报告:\n\n"
            "## 🔴 一、板块拆解推理链(核心部分)\n"
            f"请展示你极为详细、充满逻辑深度的推理思维过程。**拒绝泛泛而谈,禁止使用'板块向好'、'值得关注'等废话**。"
            f"请必须从【{board_name}】这个大板块出发,进行「剥洋葱」式的层层递进拆解。具体要求如下:\n"
            "1. **大逻辑梳理**:详细剖析当前该大板块炒作的底层核心驱动力(如:重仓该板块的某全球龙头业绩超预期、"
            "核心国产替代节点被攻克、某项颠覆性技术的物理局限被突破等)。\n"
            "2. **产业链全景映射**:必须按上、中、下游或不同技术流派(如:HBM 与 CoWoS 封装、"
            "低空飞行器主机厂与空管系统等)进行全方位的扫描评估。\n"
            "3. **逻辑与资金的共振点**:根据实时数据中发现的关联子板块(看重叠比例和规模)和成分股异动,"
            "并结合你庞大的 A 股历史炒作记忆库,找出本轮博弈逻辑最硬、资金承接力最强的 1-2 条'真命天子'支线。\n"
            "4. **剥洋葱式推导过程展现**(请务必按照下方的箭头结构,展现你每一层的演进推理):\n"
            f"   - **顶级层**:【{board_name}】总闸门开启(详细说明启动的信号是什么)\n"
            "     → **[进入中层细分产业链]**(深度推演:为什么资金要在此处切换?"
            "是基本面确定性最高,还是估值弹性最大?请给出毛利率或量产进度层面的充分逻辑支撑)\n"
            "     → **[进入底层最小可投资单元]**(绝杀推演:资金最终锁定哪个细分节点?"
            "是因为它属于'独家供应'的喉咙位,还是属于'逻辑外推性'最强的卡位点?)\n\n"
            "## 🔵 二、主板块走势深度诊断\n"
            "结合今日的技术面极值统计数据,分析板块整体是在'加速冲顶'还是'缩量洗盘'。"
            "请明确指出板块是否存在集体性质的技术陷阱或整体性溢价机会。\n\n"
            "## 🟣 三、细分方向横向赛马\n"
            "对比上述关联子板块的实时表现,指出哪个赛道具有'领涨气质',哪个赛道存在'补涨预期',"
            "哪个赛道目前是'存量博弈下的诱多陷阱'。\n\n"
            "## 🟢 四、终极操作决议\n"
            "给出确定性的操作立场(极度看好/谨慎潜伏/清仓回避),"
            "并点出 1-2 只最值得放入'猛龙观察池'的实战成分股以及推荐它们的硬核心逻辑。\n\n"
            "## 🔮 板块短线轮动预测\n"
            "### 1. ⚡️ 明日(次日)轮动瞻望\n"
            "   - **活跃度预判**:[🔥 走强 / ❄️ 走弱 / ⏳ 蓄势]\n"
            "   - **明日博弈核心**:[指出明天该板块是否会受到大盘影响,或者有特定的分时博弈点]\n"
            "### 2. 📅 T+3 轮动节奏推演\n"
            "   - **方向与胜率**:[📈/📉/↔️ (置信度 %)]\n"
            "   - **未来三日逻辑**:[简述该板块在接下来三个交易日内的轮动地位"
            "(是主线延续还是超跌反弹?)]"
        )

    # ------------------------------------------------------------------
    # 对外 API —— 一次性返回
    # ------------------------------------------------------------------
    def analyze(self, data_context: str) -> str:
        "「」个股分析,一次性返回完整结果「」"
        sys_p = self._build_stock_system_prompt()
        usr_p = self._build_stock_user_prompt(data_context)
        return self._dispatch(sys_p, usr_p, temperature=self.DEFAULT_TEMPERATURE_PREDICT)

    def analyze_board(self, data_context: str, board_name: str) -> str:
        "「」板块分析,一次性返回完整结果「」"
        sys_p = self._build_board_system_prompt()
        usr_p = self._build_board_user_prompt(data_context, board_name)
        return self._dispatch(sys_p, usr_p, temperature=self.DEFAULT_TEMPERATURE_PREDICT)

    # ------------------------------------------------------------------
    # 对外 API —— 流式返回(在 Streamlit 里配合 st.write_stream 使用)
    # ------------------------------------------------------------------
    def analyze_stream(self, data_context: str) -> Iterator[str]:
        sys_p = self._build_stock_system_prompt()
        usr_p = self._build_stock_user_prompt(data_context)
        yield from self._dispatch_stream(sys_p, usr_p, temperature=self.DEFAULT_TEMPERATURE_PREDICT)

    def analyze_board_stream(self, data_context: str, board_name: str) -> Iterator[str]:
        sys_p = self._build_board_system_prompt()
        usr_p = self._build_board_user_prompt(data_context, board_name)
        yield from self._dispatch_stream(sys_p, usr_p, temperature=self.DEFAULT_TEMPERATURE_PREDICT)

    # ------------------------------------------------------------------
    # 内部调度
    # ------------------------------------------------------------------
    def _dispatch(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        if self.provider == "anthropic":
            return self._retry(self._call_anthropic, system_prompt, user_prompt, temperature)
        elif self.provider == "gemini":
            return self._retry(self._call_gemini, system_prompt, user_prompt, temperature)
        else:
            return self._retry(self._call_openai_compatible, system_prompt, user_prompt, temperature)

    def _dispatch_stream(self, system_prompt: str, user_prompt: str, temperature: float) -> Iterator[str]:
        "「」流式调度 —— 不做重试(流式中断后续接语义已经乱了,直接暴露错误让用户再点一次)「」"
        try:
            if self.provider == "anthropic":
                yield from self._stream_anthropic(system_prompt, user_prompt, temperature)
            elif self.provider == "gemini":
                yield from self._stream_gemini(system_prompt, user_prompt, temperature)
            else:
                yield from self._stream_openai_compatible(system_prompt, user_prompt, temperature)
        except Exception as e:
            logger.error(f"流式调用失败: {e}", exc_info=True)
            yield f"\n\n❌ 流式调用失败: {e}"

    def _retry(self, fn, *args, **kwargs) -> str:
        "「」带指数退避的重试,仅用于非流式调用「」"
        last_err = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return fn(*args, **kwargs)
            except LLMCallError as e:
                last_err = e
                if attempt < self.MAX_RETRIES:
                    wait = self.RETRY_BACKOFF_BASE ** attempt
                    logger.warning(f"调用失败(第 {attempt}/{self.MAX_RETRIES} 次),{wait:.1f}s 后重试: {e}")
                    time.sleep(wait)
                else:
                    logger.error(f"重试 {self.MAX_RETRIES} 次仍失败: {e}")
        return f"❌ 大模型调用失败(已重试 {self.MAX_RETRIES} 次): {last_err}"

    # ==================================================================
    # OpenAI 兼容接口 (OpenAI / DeepSeek / 月之暗面 / 零一 / SiliconFlow 等)
    # ==================================================================
    def _get_openai_client(self):
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        if not api_key:
            raise LLMCallError("未配置 OPENAI_API_KEY")
        return OpenAI(api_key=api_key, base_url=base_url)

    def _call_openai_compatible(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        client = self._get_openai_client()
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=self.DEFAULT_MAX_TOKENS,
            )
            # token 使用量日志
            usage = getattr(resp, "usage", None)
            if usage:
                logger.info(f"[OpenAI/{model}] tokens => prompt {usage.prompt_tokens} / "
                            f"completion {usage.completion_tokens} / total {usage.total_tokens}")
            return resp.choices[0].message.content or ""
        except Exception as e:
            raise LLMCallError(f"OpenAI/兼容接口 调用失败: {e}") from e

    def _stream_openai_compatible(self, system_prompt: str, user_prompt: str,
                                  temperature: float) -> Iterator[str]:
        client = self._get_openai_client()
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        stream = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=self.DEFAULT_MAX_TOKENS,
            stream=True,
            stream_options={"include_usage": True},  # 让最后一块带 usage
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
            # 最后一块的 usage
            usage = getattr(chunk, "usage", None)
            if usage:
                logger.info(f"[OpenAI-Stream/{model}] tokens => prompt {usage.prompt_tokens} / "
                            f"completion {usage.completion_tokens} / total {usage.total_tokens}")

    # ==================================================================
    # Anthropic Claude (支持 Opus 4.7 / Sonnet 4.6 等新模型)
    # ==================================================================
    def _get_anthropic_client(self):
        from anthropic import Anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMCallError("未配置 ANTHROPIC_API_KEY")
        return Anthropic(api_key=api_key)

    @staticmethod
    def _extract_anthropic_text(content_blocks) -> str:
        "「」健壮解析 Anthropic 返回的 content blocks,跳过 thinking / tool_use 块「」"
        parts = []
        for block in content_blocks:
            # block.type == "text" 是最常见情况
            btype = getattr(block, "type", None)
            if btype == "text":
                parts.append(getattr(block, "text", ""))
            # 其他类型(thinking / tool_use)忽略
        return "".join(parts)

    def _call_anthropic(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        client = self._get_anthropic_client()
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        try:
            resp = client.messages.create(
                model=model,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=self.DEFAULT_MAX_TOKENS,
                temperature=temperature,
            )
            # 打印 usage
            usage = getattr(resp, "usage", None)
            if usage:
                logger.info(f"[Anthropic/{model}] tokens => input {usage.input_tokens} / "
                            f"output {usage.output_tokens}")
            return self._extract_anthropic_text(resp.content)
        except Exception as e:
            raise LLMCallError(f"Anthropic 调用失败: {e}") from e

    def _stream_anthropic(self, system_prompt: str, user_prompt: str,
                          temperature: float) -> Iterator[str]:
        client = self._get_anthropic_client()
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        with client.messages.stream(
            model=model,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=self.DEFAULT_MAX_TOKENS,
            temperature=temperature,
        ) as stream:
            for text in stream.text_stream:
                if text:
                    yield text
            # 流结束后打印 usage
            try:
                final = stream.get_final_message()
                usage = getattr(final, "usage", None)
                if usage:
                    logger.info(f"[Anthropic-Stream/{model}] tokens => input {usage.input_tokens} / "
                                f"output {usage.output_tokens}")
            except Exception:
                pass

    # ==================================================================
    # Google Gemini (google-genai 新 SDK, 支持 Gemini 3.1)
    # ==================================================================
    def _get_gemini_client(self):
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise LLMCallError("未配置 GEMINI_API_KEY")
        # 显式传入 api_key,避免环境变量不被识别
        return genai.Client(api_key=api_key)

    def _build_gemini_config(self, system_prompt: str, temperature: float):
        "「」构造 Gemini 的 GenerateContentConfig,自适应是否是 Gemini 3 系列「」"
        from google.genai import types
        model = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")

        cfg_kwargs = dict(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=self.DEFAULT_MAX_TOKENS,
        )

        # Gemini 3 / 3.1 支持 thinking_level —— 分析任务开 high
        if model.startswith("gemini-3"):
            try:
                cfg_kwargs["thinking_config"] = types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.HIGH
                )
            except Exception:
                # SDK 版本较旧没有 ThinkingLevel 枚举,改传字符串
                try:
                    cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level="high")
                except Exception:
                    pass

        return model, types.GenerateContentConfig(**cfg_kwargs)

    def _log_gemini_usage(self, response, model: str, tag: str = ""):
        try:
            meta = getattr(response, "usage_metadata", None)
            if meta:
                logger.info(f"[Gemini{tag}/{model}] tokens => prompt {meta.prompt_token_count} / "
                            f"candidates {meta.candidates_token_count} / total {meta.total_token_count}")
        except Exception:
            pass

    def _call_gemini(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        try:
            client = self._get_gemini_client()
            model, config = self._build_gemini_config(system_prompt, temperature)
            resp = client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=config,
            )
            self._log_gemini_usage(resp, model)
            # 优先 resp.text;如果因为 thinking/part 结构取不到,降级遍历 parts
            text = getattr(resp, "text", None)
            if text:
                return text
            parts_text = []
            try:
                for cand in resp.candidates or []:
                    for part in cand.content.parts or []:
                        # 跳过思考块
                        if getattr(part, "thought", False):
                            continue
                        t = getattr(part, "text", None)
                        if t:
                            parts_text.append(t)
            except Exception:
                pass
            return "".join(parts_text) or "(Gemini 返回空)"
        except LLMCallError:
            raise
        except Exception as e:
            raise LLMCallError(f"Gemini 调用失败: {e}") from e

    def _stream_gemini(self, system_prompt: str, user_prompt: str,
                       temperature: float) -> Iterator[str]:
        client = self._get_gemini_client()
        model, config = self._build_gemini_config(system_prompt, temperature)
        last_chunk = None
        for chunk in client.models.generate_content_stream(
            model=model,
            contents=user_prompt,
            config=config,
        ):
            last_chunk = chunk
            # chunk.text 是 SDK 封装好的便捷字段;不存在时走 parts 兜底
            text = getattr(chunk, "text", None)
            if text:
                yield text
                continue
            try:
                for cand in chunk.candidates or []:
                    for part in cand.content.parts or []:
                        if getattr(part, "thought", False):
                            continue
                        t = getattr(part, "text", None)
                        if t:
                            yield t
            except Exception:
                pass
        # 结束后打印最后一个 chunk 的 usage
        if last_chunk is not None:
            self._log_gemini_usage(last_chunk, model, tag="-Stream")


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    analyzer = LLMAnalyzer()
    print("模型已配置为:", analyzer.provider)
    print("当前时间:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("默认模型映射:")
    print("  - OpenAI/兼容     :", os.getenv("OPENAI_MODEL", "gpt-4o"))
    print("  - Anthropic Claude:", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"))
    print("  - Google Gemini   :", os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview"))