"""
智谱 GLM 客户端实现

实现 BaseLLMClient 接口，支持：
- 纯文本对话 (chat) - 使用 GLM-4.7-Flash
- 文本+图像对话 (chat_with_vision) - 使用 GLM-4.6V-Flash
"""

import json
import os
import base64
from pathlib import Path
from typing import Dict, Any, Optional

import aiohttp
from aiohttp import TCPConnector
import ssl

from ..base import BaseLLMClient
from ....utils.logger import setup_logger
from ....utils.exceptions import LLMError
from ...utils.parser import parse_llm_response


logger = setup_logger("agent")


class ZhipuClient(BaseLLMClient):
    """
    智谱 GLM 客户端

    支持智谱 API 的所有操作，包括：
    - 纯文本推理
    - 视觉理解
    """

    # 智谱官方默认 Base URL
    _DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"

    def __init__(self, api_key: str, base_url: str, model: str):
        """
        初始化智谱客户端

        Args:
            api_key: 智谱 API 密钥，为空时自动从环境变量 ZHIPU_API_KEY 读取
            base_url: 智谱 API 基础 URL，若为空则使用官方默认地址
            model: 模型名称（由工厂传入，支持不同的模型）
        """
        # api_key 兜底：配置未提供 → 从环境变量 ZHIPU_API_KEY 读取
        resolved_api_key: str = api_key or os.getenv("ZHIPU_API_KEY", "")
        if not resolved_api_key:
            raise LLMError("缺少 ZHIPU_API_KEY 配置或环境变量")

        # base_url 兜底：配置未提供 → Provider 层默认地址
        resolved_url = base_url or self._DEFAULT_BASE_URL
        super().__init__(resolved_api_key, resolved_url, model)
        self.ssl_context = self._create_ssl_context()

    def _create_ssl_context(self) -> ssl.SSLContext:
        """创建忽略 SSL 验证的上下文"""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context

    async def chat(
        self,
        system_prompt: str,
        user_input: str,
        temperature: float = 0.1,
        max_tokens: int = 4000,
    ) -> Dict[str, Any]:
        """
        纯文本对话 (使用 GLM-4.7-Flash)

        Args:
            system_prompt: 系统提示词
            user_input: 用户输入
            temperature: 采样温度
            max_tokens: 最大令牌数

        Returns:
            Dict[str, Any]: 包含 "thought" 和 "action" 的响应

        Raises:
            LLMError: 请求失败时抛出
        """
        try:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            }

            endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
            headers = self._build_headers()

            logger.debug(f"LLM 请求: system_prompt={system_prompt[:100]}...")
            logger.debug(f"user_input={user_input[:200]}...")

            connector = TCPConnector(ssl=self.ssl_context)
            async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
                async with session.post(endpoint, json=payload, timeout=60) as response:
                    if response.status >= 400:
                        body = await response.text()
                        raise LLMError(
                            f"LLM API 请求失败 ({response.status}): {body[:200]}"
                        )
                    result = await response.json()

            parsed = self._parse_chat_response(result)
            logger.info(f"LLM 响应: {json.dumps(parsed, ensure_ascii=False)}")
            return parsed

        except LLMError:
            raise
        except Exception as exc:
            error_msg = f"LLM 请求异常: {str(exc)}"
            logger.error(error_msg)
            raise LLMError(error_msg)

    async def chat_with_vision(
        self,
        system_prompt: str,
        user_input: str,
        image_path: str,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> Dict[str, Any]:
        """
        文本+图像对话

        Args:
            system_prompt: 系统提示词
            user_input: 用户输入（关于图像的指令）
            image_path: 图像文件的本地路径
            temperature: 采样温度
            max_tokens: 最大令牌数

        Returns:
            Dict[str, Any]: 包含 "thought" 和 "action" 等标准 Action 字段的响应

        Raises:
            LLMError: 请求失败时抛出
        """
        image_file = Path(image_path)
        if not image_file.exists():
            raise LLMError(f"图像文件不存在: {image_path}")

        try:
            # 读取和编码图像
            image_bytes = image_file.read_bytes()
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")

            # 构建智谱格式的多模态消息
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_input},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                            },
                        ],
                    },
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
            headers = self._build_headers()

            logger.debug(f"VLM 请求: user_input={user_input[:100]}...")
            logger.debug(f"图像路径: {image_path}")

            connector = TCPConnector(ssl=self.ssl_context)
            async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
                async with session.post(endpoint, json=payload, timeout=60) as response:
                    if response.status >= 400:
                        body = await response.text()
                        raise LLMError(
                            f"VLM API 请求失败 ({response.status}): {body[:200]}"
                        )
                    result = await response.json()

            parsed = self._parse_vision_response(result)
            logger.info(f"VLM 响应: {json.dumps(parsed, ensure_ascii=False)[:200]}...")
            return parsed

        except LLMError:
            raise
        except Exception as exc:
            error_msg = f"VLM 请求异常: {str(exc)}"
            logger.error(error_msg)
            raise LLMError(error_msg)

    def _build_headers(self) -> Dict[str, str]:
        """构建 HTTP 请求头"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _parse_chat_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析纯文本对话响应

        Args:
            response: 原始 API 响应

        Returns:
            Dict[str, Any]: 包含标准格式的解析结果

        Raises:
            LLMError: 响应格式不合法
        """
        try:
            content = None

            if "choices" in response and len(response["choices"]) > 0:
                choice = response["choices"][0]
                if "message" in choice:
                    content = choice["message"].get("content")
            elif "output" in response:
                output = response["output"]
                if isinstance(output, list) and len(output) > 0:
                    content = output[0].get("content")
                elif isinstance(output, str):
                    content = output

            if not content:
                raise LLMError(f"无法从 LLM 响应中提取内容: {response}")

            # 使用 parser 进行标准化规范化，确保输出统一格式
            parsed = parse_llm_response(content)
            return parsed

        except LLMError:
            raise
        except Exception as exc:
            error_msg = f"LLM 响应解析失败: {str(exc)}"
            logger.error(error_msg)
            raise LLMError(error_msg)

    def _parse_vision_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析视觉对话响应

        VLM 作为主决策引擎，提取大模型回复的 content 文本后，
        调用 parse_llm_response 工具进行解析，确保输出符合标准格式。

        Args:
            response: 原始 API 响应

        Returns:
            Dict[str, Any]: 包含 "thought" 和 "action" 等标准 Action 字段的响应

        Raises:
            LLMError: 响应格式不合法或解析失败
        """
        try:
            content = None

            if "choices" in response and len(response["choices"]) > 0:
                choice = response["choices"][0]
                if "message" in choice:
                    content = choice["message"].get("content")
            elif "output" in response:
                output = response["output"]
                if isinstance(output, list) and len(output) > 0:
                    content = output[0].get("content")
                elif isinstance(output, str):
                    content = output

            if not content:
                raise LLMError(f"无法从 VLM 响应中提取内容: {response}")

            # 使用 parser 进行标准化规范化，确保输出统一格式
            parsed = parse_llm_response(content)
            return parsed

        except LLMError:
            raise
        except Exception as exc:
            error_msg = f"VLM 响应解析失败: {str(exc)}"
            logger.error(error_msg)
            raise LLMError(error_msg)
