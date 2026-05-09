"""
小米 (Xiaomi MIMO) 大模型 API 客户端实现

小米 MIMO API 完全兼容 OpenAI API 协议，因此可以直接复用 OpenAI 标准的
请求/响应格式。Endpoint 为 chat/completions，支持纯文本对话和视觉理解。

实现 BaseLLMClient 接口，支持：
- 纯文本对话 (chat)
- 文本+图像多模态对话 (chat_with_vision)
"""

import base64
import os
import ssl
from pathlib import Path
from typing import Dict, Any

import aiohttp
from aiohttp import TCPConnector

from ..base import BaseLLMClient
from ....utils.logger import setup_logger
from ....utils.exceptions import LLMError
from ...utils.parser import parse_llm_response


logger = setup_logger("agent")

# 小米 MIMO API 默认 Base URL
# DEFAULT_XIAOMI_BASE_URL = "https://api.xiaomimimo.com/v1"
DEFAULT_XIAOMI_BASE_URL = "https://token-plan-sgp.xiaomimimo.com/v1"
class XiaomiClient(BaseLLMClient):
    """
    小米 MIMO 大模型客户端

    基于 OpenAI 兼容协议实现，支持：
    - 纯文本推理
    - 视觉理解（多模态）

    核心特性：
    - 使用 aiohttp 进行原生异步网络请求
    - 全 OpenAI 标准 Payload 结构
    - 统一的 parse_llm_response 解析器输出
    - 异常统一包装为 LLMError
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
    ):
        """
        初始化小米客户端

        Args:
            api_key: 小米 MIMO API 密钥，为空时自动从环境变量 XIAOMI_API_KEY 读取
            base_url: API 基础 URL，若为空则使用官方兼容地址
            model: 模型名称
        """
        # api_key 兜底：配置未提供 → 从环境变量 XIAOMI_API_KEY 读取
        resolved_api_key: str = api_key or os.getenv("XIAOMI_API_KEY", "")
        if not resolved_api_key:
            raise LLMError("缺少 XIAOMI_API_KEY 配置或环境变量")

        # base_url 兜底：配置未提供 → Provider 层默认地址
        resolved_base_url = base_url or DEFAULT_XIAOMI_BASE_URL
        super().__init__(resolved_api_key, resolved_base_url, model)
        self.ssl_context = self._create_ssl_context()

    def _create_ssl_context(self) -> ssl.SSLContext:
        """创建忽略 SSL 证书验证的上下文（针对 macOS 环境兼容）"""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def _build_headers(self) -> Dict[str, str]:
        """
        构建 HTTP 请求头

        使用标准的 Bearer Token 鉴权方式，符合 OpenAI 协议规范。

        Returns:
            Dict[str, str]: 包含 Authorization 和 Content-Type 的请求头字典
        """
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_endpoint(self) -> str:
        """
        构建请求 Endpoint URL

        拼接 Base URL 与 OpenAI 标准的 chat/completions 路径，
        确保不出现双斜杠。

        Returns:
            str: 完整的 API Endpoint URL
        """
        return f"{self.base_url.rstrip('/')}/chat/completions"

    async def _make_request(
        self,
        payload: Dict[str, Any],
        timeout: int = 90,
    ) -> Dict[str, Any]:
        """
        发起异步 HTTP POST 请求并返回 JSON 响应

        封装 aiohttp 的调用逻辑，统一处理 HTTP 错误。

        Args:
            payload: OpenAI 标准的请求体
            timeout: 请求超时时间（秒）

        Returns:
            Dict[str, Any]: API 返回的原始 JSON 字典

        Raises:
            LLMError: 网络错误或 HTTP 状态码 >= 400 时抛出
        """
        endpoint = self._build_endpoint()
        headers = self._build_headers()

        try:
            connector = TCPConnector(ssl=self.ssl_context)
            async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
                async with session.post(
                    endpoint,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    # 检查 HTTP 状态码
                    if response.status >= 400:
                        body = await response.text()
                        raise LLMError(
                            f"小米 API 请求失败 ({response.status}): "
                            f"{body[:300]}"
                        )

                    result: Dict[str, Any] = await response.json()
                    return result

        except LLMError:
            # 已经是 LLMError，直接向上抛出
            raise
        except aiohttp.ClientError as exc:
            raise LLMError(f"小米 API 网络请求异常: {str(exc)}")
        except Exception as exc:
            raise LLMError(f"小米 API 请求未知异常: {str(exc)}")

    @staticmethod
    def _extract_content(response: Dict[str, Any]) -> str:
        """
        从 OpenAI 兼容响应中提取大模型返回的文本内容

        兼容标准的 OpenAI chat/completions 响应结构：
        response.choices[0].message.content

        Args:
            response: API 原始响应字典

        Returns:
            str: 大模型生成的文本内容

        Raises:
            LLMError: 无法从响应中提取内容时抛出
        """
        content: str = ""

        # 标准的 OpenAI 响应格式
        if "choices" in response and len(response["choices"]) > 0:
            choice = response["choices"][0]
            if "message" in choice:
                content = choice["message"].get("content", "")

        if not content:
            raise LLMError(
                f"无法从小米 API 响应中提取内容: "
                f"{str(response)[:300]}"
            )

        return content

    # ------------------------------------------------------------------
    # 公开接口：chat / chat_with_vision
    # ------------------------------------------------------------------

    async def chat(
        self,
        system_prompt: str,
        user_input: str,
        temperature: float = 0.1,
        max_tokens: int = 8000,  # 从 4000 增加到 8000
    ) -> Dict[str, Any]:
        """
        纯文本对话（文本推理）

        使用 OpenAI 标准的 chat/completions 接口进行纯文本推理，
        响应经 parse_llm_response 解析后返回标准化字典。

        Args:
            system_prompt: 系统提示词
            user_input: 用户输入文本
            temperature: 采样温度（默认 0.1）
            max_tokens: 最大生成令牌数（默认 4000）

        Returns:
            Dict[str, Any]: 经 parse_llm_response 解析后的标准响应字典，
                           包含 thought 和 action 等字段

        Raises:
            LLMError: 网络异常或解析失败时统一抛出
        """
        # 构建 OpenAI 标准 Payload
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        logger.debug(
            f"小米 LLM 请求: system_prompt={system_prompt[:100]}..., "
            f"user_input={user_input[:200]}..."
        )

        try:
            # 发起请求
            result = await self._make_request(payload)

            # 提取内容文本
            content = self._extract_content(result)

            # 统一解析为标准字典格式
            parsed = parse_llm_response(content)
            logger.debug(f"小米 LLM 响应已解析: keys={list(parsed.keys())}")
            return parsed

        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"小米文本推理异常: {str(exc)}")

    async def chat_with_vision(
        self,
        system_prompt: str,
        user_input: str,
        image_path: str,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> Dict[str, Any]:
        """
        文本+图像多模态对话（视觉推理）

        将本地图像文件读取为 base64 编码后，按照 OpenAI Vision API 的
        image_url 格式嵌入到 messages 中发送给小米 MIMO API。
        响应经 parse_llm_response 解析后返回标准化字典。

        Args:
            system_prompt: 系统提示词
            user_input: 用户输入文本（包含关于图像的指令）
            image_path: 本地图像文件的路径
            temperature: 采样温度（默认 0.2）
            max_tokens: 最大生成令牌数（默认 800）

        Returns:
            Dict[str, Any]: 经 parse_llm_response 解析后的标准响应字典，
                           包含 thought 和 action 等字段

        Raises:
            LLMError: 图像文件不存在、网络异常或解析失败时统一抛出
        """
        # 校验图像文件是否存在
        image_file = Path(image_path)
        if not image_file.exists():
            raise LLMError(f"图像文件不存在: {image_path}")

        try:
            # 读取并编码图像为 Base64
            image_bytes = image_file.read_bytes()
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")

            # 构建 OpenAI Vision 兼容 Payload
            # content 使用多模态数组格式：文本 + 图像
            payload: Dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": user_input,
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}"
                                },
                            },
                        ],
                    },
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            logger.debug(
                f"小米 VLM 请求: user_input={user_input[:100]}..., "
                f"image_path={image_path}"
            )

            # 发起请求
            result = await self._make_request(payload)

            # 提取内容文本
            content = self._extract_content(result)

            # 统一解析为标准字典格式
            parsed = parse_llm_response(content)
            logger.debug(f"小米 VLM 响应已解析: keys={list(parsed.keys())}")
            return parsed

        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"小米视觉推理异常: {str(exc)}")
