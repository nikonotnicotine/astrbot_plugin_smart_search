import json
import httpx
import re
from datetime import datetime, timedelta
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.provider import ProviderRequest
from astrbot.api import logger, AstrBotConfig

@register("smart_search_augment", "AstrDeveloper", "智能联网增强辅助插件", "1.1.3")
class SmartSearchPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    # 修改方法签名，增加 event 参数
    async def _call_aux_llm(self, user_input: str, event: AstrMessageEvent, force_search: bool = False) -> str:
        """调用辅助 LLM 进行决策"""
        cnf = self.config.get("aux_llm", {})
        api_base = cnf.get("api_base", "https://api.openai.com/v1").rstrip('/')
        api_key = cnf.get("api_key", "")
        model = cnf.get("model", "gpt-4o-mini")
        sys_prompt = cnf.get("system_prompt", "")
        # 获取配置的历史轮数
        context_turns = cnf.get("context_turns", 2)

        if not api_key:
            return "NO_SEARCH"
            
        if force_search:
            sys_prompt += "\n\n【重要指令】检测到必须联网的关键词。请**忽略**之前关于闲聊不搜索的规则，你必须提取用户输入中的核心搜索词，并以 “SEARCH:关键词” 的格式返回。"

        url = f"{api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # 历史上下文获取逻辑
        history_text = ""
        if context_turns > 0:
            try:
                conv_mgr = self.context.conversation_manager
                # 获取当前会话ID
                cid = await conv_mgr.get_curr_conversation_id(event.unified_msg_origin)
                if cid:
                    conversation = await conv_mgr.get_conversation(event.unified_msg_origin, cid)
                    if conversation and conversation.history:
                        # 解析历史记录 (通常是 [{"role": "user", "content": "..."}, ...])
                        history_list = json.loads(conversation.history)
                        # 取最近 N 轮 (乘2是因为一轮包含一问一答)
                        recent_msgs = history_list[-(context_turns * 2):]
                        
                        history_segments = []
                        for msg in recent_msgs:
                            role = msg.get("role", "unknown")
                            content = msg.get("content", "")
                            # 简单过滤掉太长的历史，防止 token 溢出
                            if len(content) > 100: 
                                content = content[:100] + "..."
                            history_segments.append(f"{role}: {content}")
                        
                        if history_segments:
                            history_text = "【Conversation History】:\n" + "\n".join(history_segments) + "\n\n"
            except Exception as e:
                # 历史获取失败不影响主流程
                logger.warning(f"[SmartSearch] 获取历史上下文失败: {e}")
        # ----------------------------

        time_hint = ""
        trigger_words = ["今天", "今日", "现在", "日期", "时间", "周", "星期", "明天", "后天", "昨天", "下周", "上周", "today", "now", "current", "tomorrow", "yesterday", "next week"]
        
        if any(word in user_input.lower() for word in trigger_words):
            # 使用更自然的中文格式
            now_str = datetime.now().strftime("%Y年%m月%d日 %A")
            # 创建一个明确的指令
            time_instruction = (
                f"\n\n【时间感知指令】\n"
                f"1. 当前的准确日期是：{now_str}。\n"
                f"2. 当用户提问包含“明天”、“后天”、“下周”等相对时间时，你必须将这个时间信息明确地包含在搜索词中。\n"
                f"3. 例如：如果用户问“南京明天的天气”，你的搜索词应该是“南京明天天气”或“南京 {datetime.now().day + 1}日 天气”。"
            )
            # 将指令添加到系统提示词中
            sys_prompt += time_instruction
        
        # 将历史记录注入到 content 中
        final_content = f"{history_text}User Input: {user_input}"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": final_content}
            ],
            "temperature": 0.0,
            "max_tokens": 60
        }
        
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                return content
        except Exception as e:
            logger.error(f"[SmartSearch] 辅助模型调用失败: {e}")
            return "NO_SEARCH"

    async def _search_tavily(self, query: str) -> str:
        """调用 Tavily API 搜索"""
        # 已修复：读取正确的配置键 search_engine
        cnf = self.config.get("search_engine", {})
        api_key = cnf.get("tavily_key", "")
        if not api_key: 
            return ""

        url = "https://api.tavily.com/search"
        payload = {
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "include_answer": cnf.get("include_summary", True),
            "max_results": cnf.get("max_results", 3)
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                
                texts = []
                if cnf.get("include_summary", True) and data.get("answer"):
                    texts.append(f"【Tavily 自动总结】: {data['answer']}")
                
                for val in data.get("results", []):
                    title = val.get("title", "No Title")
                    content = val.get("content", "")
                    
                    # 读取配置中的单个网页字数限制，默认 200
                    per_page_chars = cnf.get("per_page_chars", 200)
                    
                    if len(content) > per_page_chars:
                        content = content[:per_page_chars] + "..."
                        
                    url_link = val.get("url", "")
                    texts.append(f"--- 使用来源: {title} ({url_link}) ---\n内容: {content}")
                
                return "\n\n".join(texts)
        except Exception as e:
            logger.error(f"[SmartSearch] Tavily 搜索异常: {e}")
            return ""

    @filter.on_llm_request(priority=100)
    async def augment_search(self, event: AstrMessageEvent, req: ProviderRequest):
        """核心处理逻辑"""
        text = event.message_str.strip()
        settings = self.config.get("settings", {}) 
        
        # 1. 基础过滤：跳过指令
        ignore_prefixes = settings.get("ignore_prefixes", [])
        if any(text.startswith(p) for p in ignore_prefixes):
            return
        
        # 1.1 跳过关键词
        skip_keywords = settings.get("skip_keywords", [])
        if any(kw in text for kw in skip_keywords):
            if settings.get("show_log"):
                logger.debug(f"[SmartSearch] 命中跳过关键词，不执行动作。")
            return
            
        # 1.2 判断是否强制搜索
        force_keywords = settings.get("force_search_keywords", [])
        is_force = any(kw in text for kw in force_keywords)
        
        if is_force and settings.get("show_log"):
            logger.info(f"[SmartSearch] 命中强制搜索关键词，将指示辅助模型提取关键词。")
        # 2. 调用辅助模型决策 (传入 force_search 参数)
        decision = await self._call_aux_llm(text, event, force_search=is_force)
        if settings.get("show_log"):
            box_log = (
                "\n┌────────── [SmartSearch] 辅助判定过程 ──────────┐\n"
                f"│ 触发模式: {'强制提取' if is_force else '智能自动判定'}\n"
                f"│ 用户输入: {text[:50] + '...' if len(text) > 50 else text}\n"
                f"│ 模型返回: {decision}\n"
                "└──────────────────────────────────────────────────┘"
            )
            logger.info(box_log)
        
        # 3. 结果解析 
        if "NO_SEARCH" in decision.upper():
            return

        search_query = ""
        match = re.search(r"(?:SEARCH|搜索词)[\s:：\"'“]+([^\"'””。，\n]+)", decision, re.IGNORECASE)
        
        if match:
            search_query = match.group(1).strip()
            search_query = search_query.rstrip("。.")
        else:
            # 备用提取逻辑
            if len(decision) < 30 and "NO_SEARCH" not in decision.upper():
                    search_query = decision.strip()
            else:
                if settings.get("show_log"):
                    logger.warning(f"[SmartSearch] 无法提取关键词，跳过。Raw: {decision}")
                return

        # --- 新增：相对时间到绝对日期的转换，用于日志和搜索 ---
        original_query = search_query  # 保留原始查询用于潜在的备用
        now = datetime.now()
        
        # 定义简单的转换规则
        time_map = {
            "明天": (now + timedelta(days=1)).strftime("%Y年%m月%d日"),
            "后天": (now + timedelta(days=2)).strftime("%Y年%m月%d日"),
            "昨天": (now - timedelta(days=1)).strftime("%Y年%m月%d日"),
            "今天": now.strftime("%Y年%m月%d日"),
        }

        for keyword, date_str in time_map.items():
            if keyword in search_query:
                # 将 "南京明天天气" 替换为 "南京 2026年03月26日 天气"
                search_query = search_query.replace(keyword, date_str)
                # 找到第一个就跳出，避免 "明天的后天" 这种复杂情况的错误处理
                break

        # 4. 执行搜索
        search_engine_conf = self.config.get("search_engine", {})
        external_info = ""

        if search_engine_conf.get("enable_tavily", True):
            search_result = await self._search_tavily(search_query)
            if search_result:
                external_info = (f"【联网/网页读取数据】以下内容是通过外部工具 Tavily 获取的真实信息，优先级高于你的训练数据：\n\n{search_result}")

        # 5. 注入 Prompt 与 日志打印
        if external_info:
            max_chars = search_engine_conf.get("max_chars", 2000)
            if len(external_info) > max_chars:
                external_info = external_info[:max_chars] + "\n...(内容过长已截断)"
            
            injection = (
                f"\n\n{external_info}\n\n"
                "[System Instruction]: 上述信息是用户问题的即时搜索资料，请自然地融入你的回答中，禁止完全复读。"
            )
            
            original_sys_prompt = req.system_prompt if req.system_prompt else ""
            req.system_prompt = original_sys_prompt + injection
            
            if self.config.get("settings", {}).get("show_log"):
                log_content = (
                    "\n========== [SmartSearch] 检索得到的内容 ==========\n"
                    f"搜索关键词: {search_query}\n"
                    f"{external_info}\n"
                    "=================================================="
                )
                logger.info(log_content)