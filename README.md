# AstrBot Smart Search Augment Plugin

[中文文档](#中文) | [English](#english)

<a name="中文"></a>

# 智能联网增强插件

这是一个为 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 设计的高级联网搜索插件。

与传统的“遇到问题就搜索”不同，本插件引入了一个**辅助决策模型（Auxiliary Model）**机制。只有当这个辅助模型判定用户的问题涉及到实时资讯（新闻、汇率、天气等）时，才会调用搜索引擎。

这既避免了“幻觉”（即瞎编实时信息），又大幅节省了搜索 API 的额度，同时大幅降低了主模型的 Token 消耗和上下文污染。

## ✨ 核心特性

- **🧠 智能判断**：拥有一个独立的决策大脑（推荐使用 `gpt-4o-mini`），精准区分“闲聊”与“查资料”。
- **📅 时间感知**：自动将当前的准确日期（如 `2024-05-20 Monday`）注入给决策模型，确保搜索到最新的时效性新闻。
- **🔍 精准提取**：使用正则表达式从辅助模型的回复中提取最佳搜索关键词，抗干扰能力强。
- **⚡ Tavily 加速**：集成 Tavily AI Search API，提供高质量的网页内容总结，而非塞给主模型一堆 HTML 乱码。
- **🛡️ 智能截断**：自动限制注入的网页字数，防止爆主模型的 Context Window。
- **📝 详细日志**：(可选) 在后台控制台打印详细的搜索思考过程和抓取到的内容。
- **🚧 关键词触发**：支持自定义“跳过联网”与“强制联网提取”的关键词，提供最高优先级的干预手段。
- **✂️ 自定义片段字数**：不再固定截断，可自由在配置项中调整单个网页返回的内容字数上限。

## ⚙️ 配置说明

安装插件后，请在 AstrBot 管理面板或 `data/plugins/astrbot_plugin_smart_search/config.json` 中配置：

### 1. 辅助模型配置 (Auxiliary Model)
这是用来做“裁判”的模型，建议使用便宜、速度快的模型。

- **API Base**: OpenAI 格式的接口地址（例如 `https://api.openai.com/v1` 或各类中转地址）。
- **API Key**: 该模型的 Key。
- **Model**: 推荐 `gpt-4o-mini`, `gpt-3.5-turbo`, `gemini-flash` 等。
- **System Prompt**: 插件已内置最佳 Prompt，通常无需修改。

### 2. 搜索引擎配置 (Search Engine)
负责执行搜索任务。

- **Enable Tavily**: 开启后使用 Tavily 搜索（强烈推荐）。
- **Tavily Key**: 前往 [Tavily](https://tavily.com/) 免费申请 API Key (格式 `tvly-...`)。
- **Max Results**: 建议设置为 `2` 或 `3`，表示每次搜索引用几个网页。
- **Include Summary**: 是否包含 Tavily 生成的智能一句话总结。
- **Per Page Chars**: 单个搜索结果片段最多保留的字数（默认 200），防止单网页内容过多。

### 3. 通用设置
- **Ignore Prefixes**: 忽略以 `/` 或 `#` 开头的指令消息。
- **Skip Keywords**: 自定义跳过词库。当用户输入包含这些词时，完全不调用辅助模型和搜索，节约资源。
- **Force Search Keywords**: 强制搜索词库。当用户输入包含这些词时，要求辅助模型强制提取搜索词并进行联网搜索业务。
- **Show Log**: 是否在控制台打印 `[SmartSearch]` 的调试大日志。

## 🛠️ 工作原理

1. **拦截**：用户发送消息（例如：“现在的伊朗局势”）。
2. **感知**：插件获取当前系统时间，连同用户消息一起发送给**辅助模型**。
3. **决策**：辅助模型判断需要联网，生成关键词 `SEARCH:2024年5月xx日 伊朗局势`。
4. **执行**：插件正则提取关键词，调用 **Tavily API**。
5. **注入**：将 Tavily 返回的“智能总结”+“网页正文片段”格式化后，注入到主模型的 System Prompt 中。
6. **回答**：主模型结合实时资料，给出准确回答。

---

<a name="english"></a>

# Smart Search Augment

An advanced web search plugin for AstrBot that uses an auxiliary LLM to intelligently decide when to search.

## Features

- **Smart Decision**: Uses a cheaper, faster LLM (e.g., `gpt-4o-mini`) to decide if a search is necessary.
- **Time Awareness**: Automatically injects the current system date/time into the context, ensuring search queries are time-accurate.
- **Tavily Integration**: Fetches AI-optimized search results and summaries using the Tavily API.
- **Robustness**: Uses Regex to extract search queries reliably.
- **Configurable**: Fully customizable log settings, model endpoints, and context length limits.
- **Keyword Triggers**: Define custom keywords to either completely skip the search process or force the search regardless of the context.
- **Custom Snippet Length**: Configurable max character limit for each search result snippet.