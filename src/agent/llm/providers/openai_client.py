"""
OpenAI 客户端实现

支持 GPT-4, GPT-3.5-Turbo 等模型的客户端。
"""

from typing import Dict, Any

from ..base import BaseLLMClient
from ....utils.logger import setup_logger
from ....utils.exceptions import LLMError


logger = setup_logger("agent")


class OpenAIClient(BaseLLMClient):
    """
    OpenAI API 客户端
    
    TODO: 实现 OpenAI API 集成
    """

    def __init__(self, api_key: str, base_url: str = "", model: str = "gpt-4"):
        """
        初始化 OpenAI 客户端

        Args:
            api_key: OpenAI API 密钥
            base_url: API 基础 URL（可选）
            model: 模型名称
        """
        super().__init__(api_key, base_url or "https://api.openai.com/v1/", model)

    async def chat(
        self,
        system_prompt: str,
        user_input: str,
        temperature: float = 0.1,
        max_tokens: int = 4000,
    ) -> Dict[str, Any]:
        """
        纯文本对话

        TODO: 实现 OpenAI 对话
        """
        raise NotImplementedError("OpenAI 客户端尚未实现")

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

        TODO: 实现 OpenAI Vision API
        """
        raise NotImplementedError("OpenAI Vision 尚未实现")
