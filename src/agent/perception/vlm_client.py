"""
VLM 客户端模块

负责对接视觉语言模型，用于图像级页面理解与语义建议。
"""

import os
import base64
import json
from pathlib import Path
from typing import Dict, Any

import aiohttp
from aiohttp import TCPConnector
import ssl

from ...config.settings import get_config
from ...utils.exceptions import PerceptionError


class VLMClient:
    """
    视觉语言模型客户端

    负责调用智谱 ZhipuAI 原生接口，分析页面截图并返回语义建议。
    """

    def __init__(self):
        self.config = get_config().vlm

    async def analyze_page(self, screenshot_path: str, user_goal: str) -> Dict[str, Any]:
        """
        分析页面截图并生成语义建议。

        Args:
            screenshot_path: 页面截图的本地路径
            user_goal: 用户当前目标描述

        Returns:
            Dict[str, Any]: VLM 返回结果，包含建议文本和原始响应

        Raises:
            PerceptionError: 调用失败或响应不可用时抛出
        """
        screenshot_file = Path(screenshot_path)
        if not screenshot_file.exists():
            raise PerceptionError(f"截图文件不存在: {screenshot_path}")

        if not self.config.api_key:
            raise PerceptionError("VLM API Key 未配置，请在环境变量或配置文件中设置 VLM api_key")

        try:
            payload = self._build_payload(screenshot_file, user_goal)
            endpoint = self._build_endpoint()
            headers = self._build_headers()

            # 创建忽略 SSL 验证的连接器
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connector = TCPConnector(ssl=ssl_context)

            async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
                async with session.post(endpoint, json=payload, timeout=60) as response:
                    if response.status >= 400:
                        body = await response.text()
                        raise PerceptionError(f"VLM 请求失败: {response.status} {body}")
                    result = await response.json()

            return self._parse_response(result)
        except PerceptionError:
            raise
        except Exception as exc:
            raise PerceptionError(f"VLM 请求失败: {exc}")

    def _build_endpoint(self) -> str:
        """构建智谱 API 端点"""
        base_url = self.config.base_url.rstrip("/")
        return f"{base_url}/chat/completions"

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(self, screenshot_file: Path, user_goal: str) -> Dict[str, Any]:
        """构建智谱 API 请求负载（原生格式）"""
        screenshot_bytes = screenshot_file.read_bytes()
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        prompt = (
            f"请根据页面截图和用户目标执行视觉理解。用户目标：{user_goal}。"
            "如果 DOM 无法解析出关键操作元素，请返回可能的按钮位置、语义建议和可点击目标。"
        )

        return {
            "model": self.config.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{screenshot_base64}"}
                        },
                    ],
                }
            ],
            "temperature": 0.2,
            "max_tokens": 800,
        }

    def _parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(response, dict):
            raise PerceptionError("VLM 响应格式不合法")

        # 尝试从常见返回结构中提取文本结果
        content = []
        if "choices" in response:
            for choice in response.get("choices", []):
                message = choice.get("message") or {}
                if isinstance(message, dict):
                    text = message.get("content")
                    if text:
                        content.append(text)
        elif "output" in response:
            output = response.get("output")
            if isinstance(output, list):
                for item in output:
                    if isinstance(item, dict):
                        text = item.get("content")
                        if text:
                            content.append(text)
            elif isinstance(output, str):
                content.append(output)

        if not content:
            content.append(json.dumps(response, ensure_ascii=False)[:2048])

        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "recommendation": "\n".join(content).strip(),
            "raw_response": response,
        }
