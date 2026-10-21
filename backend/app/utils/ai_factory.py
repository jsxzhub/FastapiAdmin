import threading
from dataclasses import dataclass, field
from typing import Any

from agno.agent import Agent
from agno.models.openai.like import OpenAILike
from agno.team import Team

from app.config.setting import settings


@dataclass
class AgentDefinition:
    """智能体定义（注册表项）：一次定义、按 agent_id 解析复用，贴近 AgentOS 的 agent 注册机制。"""

    name: str
    role: str
    description: str
    instructions: list[str] | None = None
    tools: list[Any] = field(default_factory=list)


# 自定义智能体注册表：agent_id -> 定义。运行时按 agent_id 解析，避免每次内联重复定义。
CUSTOM_AGENT_REGISTRY: dict[str, AgentDefinition] = {
    "custom_assistant": AgentDefinition(
        name="乐于助人的助手",
        role="助手",
        description="你是一个乐于助人的助手",
    ),
}
DEFAULT_CUSTOM_AGENT_ID = "custom_assistant"


class AgnoFactory:
    """Agno 工厂类 - 统一管理 Agent、Team 创建逻辑"""

    # 配置常量
    AGENT_DESCRIPTION = "你是一个有用的AI助手，可以帮助用户回答问题和提供帮助。"
    AGENT_INSTRUCTIONS = ["保持回答简洁明了", "如果不确定，请说明"]
    AGENT_EXPECTED_OUTPUT = "中文回答"
    AGENT_TEMPERATURE = 0.7
    NUM_HISTORY_RUNS = 3
    REQUEST_TIMEOUT = 60.0  # LLM 请求总超时（秒），流式响应需放长
    CONNECT_TIMEOUT = 10.0  # TCP 连接超时（秒）

    # 自定义智能体实例缓存：agent_id -> Agent（首次构建后常驻，run 时复用，类似 AgentOS 的 os.agents 注册表）。
    # 仅“静态系统配置”路径复用；若运行时传入 model_config 覆盖，则每次现建以避免模型串用。
    _custom_agent_cache: dict[str, Agent] = {}
    _custom_agent_lock = threading.Lock()

    def create_agent(
        self,
        user_id: str,
        team_id: str,
        session_id: str,
        db: Any | None = None,
        model_config: dict[str, Any] | None = None,
        tools: list[Any] | None = None,
    ) -> Team:
        """创建带 Agent 的 Team 实例。

        参数:
        - user_id (str): 用户标识。
        - team_id (str): 团队标识。
        - session_id (str): 会话 ID。
        - db (Any | None): Agno 持久化数据库实例，可选。
        - model_config (dict | None): 运行时模型配置，覆盖系统默认。
            支持字段：base_url, api_key, model_id, temperature。
        - tools (list[Any] | None): 需要注入给 Agent 的工具（**只读工具**，由调用方按开关决定）。

        返回:
        - Team: 配置好的 Team。
        """
        # 优先使用运行时配置，否则 fallback 到系统 settings
        base_url = settings.OPENAI_BASE_URL
        api_key = settings.OPENAI_API_KEY
        model_id = settings.OPENAI_MODEL
        temperature = self.AGENT_TEMPERATURE

        if model_config:
            base_url = model_config.get("base_url") or base_url
            api_key = model_config.get("api_key") or api_key
            model_id = model_config.get("model_id") or model_id
            if isinstance(model_config.get("temperature"), (int, float)):
                temperature = float(model_config["temperature"])

        # 创建 Agent
        fastapiadmin_agent = Agent(
            id=user_id,
            name="fastapiadmin_agent",
            role="You are a helpful AI assistant",
            description=self.AGENT_DESCRIPTION,
            tools=list(tools or []),
        )

        # 创建 Team
        fastapiadmin_team = Team(
            id=team_id,
            user_id=user_id,
            session_id=session_id,
            model=OpenAILike(
                id=model_id,
                api_key=api_key,
                base_url=base_url,
                temperature=temperature,
                timeout=self.REQUEST_TIMEOUT,
            ),
            members=[fastapiadmin_agent],
            instructions=self.AGENT_INSTRUCTIONS,
            expected_output=self.AGENT_EXPECTED_OUTPUT,
            add_datetime_to_context=True,
            add_history_to_context=True,
            markdown=True,
            num_history_runs=self.NUM_HISTORY_RUNS,
            input_schema=None,
            output_schema=None,
            parse_response=True,
            read_chat_history=True,
            db=db,
        )

        return fastapiadmin_team

    def _build_openai_like(self, model_config: dict[str, Any] | None) -> OpenAILike:
        """按系统配置（或运行时覆盖）构造 OpenAILike 客户端。"""
        base_url = settings.OPENAI_BASE_URL
        api_key = settings.OPENAI_API_KEY
        model_id = settings.OPENAI_MODEL
        temperature = self.AGENT_TEMPERATURE
        if model_config:
            base_url = model_config.get("base_url") or base_url
            api_key = model_config.get("api_key") or api_key
            model_id = model_config.get("model_id") or model_id
            if isinstance(model_config.get("temperature"), (int, float)):
                temperature = float(model_config["temperature"])
        return OpenAILike(
            id=model_id,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            timeout=self.REQUEST_TIMEOUT,
        )

    def _build_custom_agent(self, agent_id: str, model: OpenAILike, db: Any) -> Agent:
        """按注册定义 + 给定 model/db 构造自定义 Agent 运行期对象。"""
        definition = CUSTOM_AGENT_REGISTRY.get(agent_id) or CUSTOM_AGENT_REGISTRY[DEFAULT_CUSTOM_AGENT_ID]
        # user_id/session_id 不在此固化：每次 arun(user_id=..., session_id=...) 显式传入，
        # 这样同一个常驻实例可被多个会话/用户安全复用（与 AgentOS 一致）。
        return Agent(
            id=agent_id,
            user_id=None,
            session_id=None,
            name=definition.name,
            role=definition.role,
            description=definition.description,
            instructions=definition.instructions,
            tools=definition.tools,
            model=model,
            add_history_to_context=True,
            num_history_runs=self.NUM_HISTORY_RUNS,
            db=db,
        )

    def _resolve_cached_custom_agent(self, agent_id: str, db: Any) -> Agent:
        """解析自定义智能体的常驻实例（首次构建后缓存复用，类似 AgentOS 启动建一次）。

        - 静态系统配置路径：缓存 Agent 实例，后续请求直接复用，避免每请求重建。
        - db 为进程级单例（_get_agno_db），每次取用时刷新到实例上（无会话状态，安全）。
        """
        # 双重检查锁定（double-checked locking）：保证每个 agent_id 的实例只构建一次、之后常驻复用
        cached = AgnoFactory._custom_agent_cache.get(agent_id)
        if cached is not None:
            # 快路径：实例已存在，无锁直返（避免每次请求争抢锁，绝大多数请求走这里）
            cached.db = db  # db 为进程级单例、不含会话状态，刷新到共享实例上是安全的
            return cached
        # 未命中：加锁进入构建临界区（仅在首调或并发首次构建时发生，属低频路径）
        with AgnoFactory._custom_agent_lock:
            # 锁内二次检查：防止“首次检查”到“拿到锁”之间已有别的线程把实例建好，避免重复构建
            cached = AgnoFactory._custom_agent_cache.get(agent_id)
            if cached is None:
                # 用系统默认模型（None）构建一次，并缓存到 agent_id 名下（静态路径复用，建一次后不再重建）
                cached = self._build_custom_agent(agent_id, self._build_openai_like(None), db)
                AgnoFactory._custom_agent_cache[agent_id] = cached
        # 锁外统一收尾：刷新 db 并返回（锁内新建或锁内重查命中都走到这里）
        cached.db = db
        return cached

    def create_agent_custom(
        self,
        agent_id: str,
        db: Any,
        model_config: dict[str, Any] | None = None,
    ) -> Agent:
        """创建/获取定制化 Agent（按 agent_id 从注册表解析定义，贴近 AgentOS 的注册/复用）。

        参数:
        - agent_id (str): 智能体定义 ID（见 CUSTOM_AGENT_REGISTRY）。
        - db (Any): Agno 持久化数据库实例（进程级单例）。
        - model_config (dict | None): 运行时模型配置，覆盖系统默认。
            支持字段：base_url, api_key, model_id, temperature。

        返回:
        - Agent: 配置好的 Agent

        注意: 返回实例的 user_id/session_id 不固化，调用方必须在
        agent.arun(input, session_id=..., user_id=...) 显式传入以区分会话/用户。
        """
        if model_config:
            # 运行时覆盖模型：必须按覆盖现建（含覆盖后的 model），不复用缓存实例，避免模型串用。
            return self._build_custom_agent(agent_id, self._build_openai_like(model_config), db)
        # 静态配置：复用常驻实例（首次调用构建一次，之后每次 run 复用，类似 AgentOS）。
        return self._resolve_cached_custom_agent(agent_id, db)



