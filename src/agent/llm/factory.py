"""
通用 LLM 客户端工厂

提供统一的工厂方法来创建和管理 LLM 客户端实例。
根据 config.yaml 中的 provider 字段动态实例化对应的客户端。

支持的提供者 (Provider)：
1. manual - 手动模式（Human-in-the-Loop）
2. zhipu - 智谱 GLM API
3. openai - OpenAI API（未来支持）
4. claude - Anthropic Claude API（未来支持）
5. xiaomi - 小米 MIMO 大模型 API（兼容 OpenAI 协议）
6. ollama - Ollama 本地大模型 API（兼容 OpenAI 协议）
"""

from typing import Dict, Literal, Optional, Type
from importlib import import_module

from .base import BaseLLMClient
from ...config.settings import get_config
from ...utils.logger import setup_logger
from ...utils.exceptions import LLMError


logger = setup_logger("agent")


class LLMFactory:
    """
    通用 LLM 客户端工厂

    使用动态导入来实例化不同提供者的客户端。
    
    架构：
    - 提供者配置在 config.yaml 中
    - 提供者的实现存放在 src/agent/providers/ 目录
    - 工厂类负责动态导入并缓存实例
    """

    # 提供者到模块和类的映射
    PROVIDER_MAP = {
        "manual": ("providers.manual_client", "ManualVLMClient"),
        "zhipu": ("providers.zhipu_client", "ZhipuClient"),
        "openai": ("providers.openai_client", "OpenAIClient"),
        "claude": ("providers.claude_client", "ClaudeClient"),
        "xiaomi": ("providers.xiaomi_client", "XiaomiClient"),
        "ollama": ("providers.ollama_client", "OllamaClient"),
    }

    # 缓存已创建的实例（使用 role 作为 key）
    _instances: Dict[str, BaseLLMClient] = {}

    @classmethod
    def get_instance(cls, role: Literal["logic", "vision"] = "logic") -> BaseLLMClient:
        """
        获取 LLM 客户端实例

        Args:
            role: 使用场景
                - "logic": 纯文本推理任务
                - "vision": 图像分析任务

        Returns:
            BaseLLMClient: 对应的客户端实例

        Raises:
            LLMError: 无法创建客户端时抛出
        """
        if role not in ("logic", "vision"):
            raise LLMError(f"不支持的 role: {role}，必须为 'logic' 或 'vision'")

        # 检查缓存
        if role in cls._instances:
            logger.debug(f"使用缓存的 {role} 客户端")
            return cls._instances[role]

        # 获取配置
        config = get_config()
        client_config = config.llm if role == "logic" else config.vlm

        # 获取提供者名称
        provider = client_config.provider.lower()

        # 根据 role 和 provider 创建客户端
        try:
            instance = cls._create_client(provider, role, client_config)
            cls._instances[role] = instance
            logger.info(f"✓ 创建 {role} 客户端: provider={provider}, model={client_config.model}")
            return instance
        except Exception as e:
            error_msg = f"无法创建 {provider} 客户端 ({role}): {str(e)}"
            logger.error(error_msg)
            raise LLMError(error_msg)

    @classmethod
    def _create_client(
        cls,
        provider: str,
        role: str,
        config: object,
    ) -> BaseLLMClient:
        """
        动态创建客户端实例

        Args:
            provider: 提供者名称
            role: 使用角色（logic/vision）
            config: 客户端配置

        Returns:
            BaseLLMClient: 创建的客户端实例

        Raises:
            LLMError: 创建失败时抛出
        """
        # 检查提供者是否支持
        if provider not in cls.PROVIDER_MAP:
            raise LLMError(
                f"不支持的提供者: {provider}\n"
                f"支持的提供者: {', '.join(cls.PROVIDER_MAP.keys())}"
            )

        module_name, class_name = cls.PROVIDER_MAP[provider]

        try:
            # 动态导入模块
            module = import_module(f"..{module_name}", package=__name__)
            client_class: Type[BaseLLMClient] = getattr(module, class_name)

            # 根据提供者创建实例
            if provider == "manual":
                # Manual 模式不需要 API Key
                instance = client_class()
            else:
                # api_key 的缺失校验下沉至各 Provider 的 __init__
                # 工厂只负责透传，不再拦截

                # 根据提供者传递相应的参数
                # 注意：base_url 的默认值由各 Provider 的 __init__ 自行兜底，
                # 工厂不再硬编码任何 URL，只透传配置值（缺失时传 None）
                if provider == "zhipu":
                    # Zhipu 客户端的构造函数签名：__init__(api_key, base_url, model)
                    instance = client_class(
                        api_key=getattr(config, "api_key", None),
                        base_url=getattr(config, "base_url", None),
                        model=config.model,
                    )
                elif provider == "openai":
                    # OpenAI 客户端的构造函数签名：__init__(api_key, base_url="...")
                    instance = client_class(
                        api_key=getattr(config, "api_key", None),
                        base_url=getattr(config, "base_url", None),
                    )
                elif provider == "claude":
                    # Claude 客户端的构造函数签名：__init__(api_key, base_url="...")
                    instance = client_class(
                        api_key=getattr(config, "api_key", None),
                        base_url=getattr(config, "base_url", None),
                    )
                elif provider == "xiaomi":
                    # 小米 MIMO 客户端的构造函数签名：__init__(api_key, base_url, model)
                    instance = client_class(
                        api_key=getattr(config, "api_key", None),
                        base_url=getattr(config, "base_url", None),
                        model=config.model,
                    )
                elif provider == "ollama":
                    # Ollama 客户端的构造函数签名：__init__(api_key="", base_url="", model)
                    # api_key 和 base_url 在 Provider 内部有完整兜底
                    instance = client_class(
                        api_key=getattr(config, "api_key", None) or "",
                        base_url=getattr(config, "base_url", None) or "",
                        model=config.model,
                    )
                else:
                    # 通用构造函数
                    instance = client_class(
                        api_key=getattr(config, "api_key", None),
                        base_url=getattr(config, "base_url", None),
                    )

            return instance

        except ImportError as e:
            raise LLMError(f"无法导入提供者模块 '{module_name}': {e}")
        except AttributeError as e:
            raise LLMError(f"提供者模块中不存在类 '{class_name}': {e}")
        except Exception as e:
            raise LLMError(f"创建客户端失败: {e}")

    @classmethod
    def reset(cls) -> None:
        """
        重置工厂，清除所有缓存的实例

        主要用于测试和切换配置场景
        """
        cls._instances.clear()
        logger.debug("LLM 工厂已重置，缓存已清除")

    @classmethod
    def get_supported_providers(cls) -> list:
        """
        获取支持的提供者列表

        Returns:
            list: 支持的提供者名称列表
        """
        return list(cls.PROVIDER_MAP.keys())
