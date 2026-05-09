"""
LLM 客户端基础类（抽象）

定义所有 LLM 客户端（包括文本和视觉版本）需要实现的接口。
支持不同的 LLM 提供者（智谱、OpenAI、Claude 等）。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseLLMClient(ABC):
    """
    LLM 客户端抽象基类

    定义 LLM 客户端的统一接口，支持：
    1. 纯文本对话 (chat)
    2. 文本+图像多模态对话 (chat_with_vision)
    """

    def __init__(self, api_key: str, base_url: str, model: str):
        """
        初始化客户端

        Args:
            api_key: API 密钥
            base_url: API 基础 URL
            model: 模型名称
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    @abstractmethod
    async def chat(
        self,
        system_prompt: str,
        user_input: str,
        temperature: float = 0.1,
        max_tokens: int = 4000,
    ) -> Dict[str, Any]:
        """
        纯文本对话

        Args:
            system_prompt: 系统提示词
            user_input: 用户输入
            temperature: 采样温度
            max_tokens: 最大生成令牌数

        Returns:
            Dict[str, Any]: LLM 响应，应包含 "thought" 和 "action" 字段

        Raises:
            Exception: LLM 请求失败时抛出
        """
        pass

    @abstractmethod
    async def chat_with_vision(
        self,
        system_prompt: str,
        user_input: str,
        image_path: str,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> Dict[str, Any]:
        """
        文本+图像多模态对话

        Args:
            system_prompt: 系统提示词
            user_input: 用户输入（包含关于图像的指令）
            image_path: 图像文件的本地路径
            temperature: 采样温度
            max_tokens: 最大生成令牌数

        Returns:
            Dict[str, Any]: VLM 响应，应包含 "thought" 和 "action" 等标准 Action 字段

        Raises:
            Exception: VLM 请求失败时抛出
        """
        pass
