"""
LLM 客户端模块

提供统一的 LLM 接口入口，内部根据配置走不同路径：
1. manual 路径：终端手动输入
2. auto 路径：占位的自动实现入口（当前委托现有 provider）

对外仅暴露一个入口：
    client = LLMClient()
    result = await client.chat(...)
"""

import asyncio
import json
import sys
from typing import Dict, Any, Optional

from .factory import LLMFactory
from ..utils.parser import normalize_llm_response
from ...config.settings import get_config
from ...utils.logger import setup_logger
from ...utils.exceptions import LLMError


logger = setup_logger("agent")


class LLMClient:
    """
    大语言模型客户端（统一抽象层）

    对外只暴露 chat()，内部根据 llm.mode 选择执行路径。
    """

    def __init__(self):
        """
        初始化 LLMClient
        """
        self._config = get_config().llm
        mode = (self._config.mode or "auto").lower()
        self._mode = mode if mode in {"manual", "auto"} else "auto"
        self._auto_impl = None

        # auto 路径占位：当前先复用已有 provider 实现
        if self._mode == "auto":
            self._auto_impl = LLMFactory.get_instance(role="logic")

        logger.debug(f"LLMClient 已初始化: mode={self._mode}")

    async def chat(
        self,
        system_prompt: str,
        user_input: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        image_path: Optional[str] = None,
        valid_element_ids: Optional[list] = None,
        context_manager: Optional[Any] = None,
        task_state: Optional[Any] = None,
        action_history: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        调用 LLM/VLM 进行推理（双模态路由 + 自我修正 + 上下文压缩）。

        该方法实现了"AI 幻觉拦截"机制：当 LLM 返回的 element_id 不在有效列表中时，
        自动触发一次重试，并在用户提示中追加系统反馈，让大模型重新选择。
        
        同时支持上下文压缩：当上下文超过阈值时，自动压缩历史记录。

        Args:
            system_prompt: 系统提示词
            user_input: 用户输入
            temperature: 调节采样温度（可选，使用配置默认值）
            max_tokens: 最大生成令牌数（可选，使用配置默认值）
            image_path: 图像文件的本地路径（可选，若提供则走视觉路线）
            valid_element_ids: 有效的 element_id 列表（可选，若提供则启用 ID 幻觉拦截）
            context_manager: 上下文压缩管理器（可选）
            task_state: 任务状态对象（可选，用于上下文压缩）
            action_history: 动作历史列表（可选，用于上下文压缩）

        Returns:
            Dict[str, Any]: 返回结构化结果 {"thought": "...", "action": {...}}

        Raises:
            LLMError: 请求失败或响应格式不合法时抛出；多次重试均未获取合法 element_id 时抛出
        """
        temperature = temperature or self._config.temperature
        max_tokens = max_tokens or self._config.max_tokens
        
        # 【上下文压缩】构建消息列表
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]
        
        # 【上下文压缩】检查是否需要压缩
        if context_manager and context_manager.should_compress(messages):
            if task_state is not None and action_history is not None:
                logger.info("触发上下文压缩...")
                messages = await context_manager.compress(
                    messages=messages,
                    task_state=task_state,
                    action_history=action_history,
                    llm_client=self  # 传入自身用于压缩 NORMAL 记录
                )
                # 压缩后重新提取 system_prompt 和 user_input
                system_prompt = ""
                user_input = ""
                for msg in messages:
                    if msg.get("role") == "system":
                        system_prompt = msg.get("content", "")
                    elif msg.get("role") == "user":
                        # 合并所有 user 消息
                        user_input += msg.get("content", "") + "\n\n"
                user_input = user_input.strip()
            else:
                logger.warning("⚠️  上下文需要压缩，但缺少 task_state 或 action_history，跳过压缩")
        
        # ========== 重试循环：最多 3 次 ==========
        max_retries = 3
        current_user_input = user_input
        
        for attempt in range(max_retries):
            logger.debug(f"LLMClient 执行第 {attempt + 1}/{max_retries} 次推理请求...")
            
            try:
                # 选择调用路径：manual 或 auto
                if self._mode == "manual":
                    result = await self._chat_manual(
                        system_prompt=system_prompt,
                        user_input=current_user_input,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                else:
                    result = await self._chat_auto(
                        system_prompt=system_prompt,
                        user_input=current_user_input,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        image_path=image_path,
                    )
                
                # ========== 拦截逻辑：检查 element_id 有效性 ==========
                # 尝试从结果中提取 element_id
                element_id = self._extract_element_id(result)
                
                # 如果配置了有效 ID 列表，则验证
                if valid_element_ids is not None and element_id is not None:
                    if element_id not in valid_element_ids:
                        # 【幻觉检测】ID 不在有效列表中
                        logger.warning(
                            f"⚠️  【AI 幻觉检测】LLM 返回的 element_id={element_id} "
                            f"不在有效 ID 列表中 {valid_element_ids}，触发重试..."
                        )
                        
                        # 构造系统反馈消息
                        valid_ids_str = ", ".join(str(id) for id in sorted(valid_element_ids))
                        feedback = (
                            f"\n\n[系统反馈]: 你选择的 element_id {element_id} 不存在。"
                            f"请重新观察图片，并仅从以下有效 ID 中选择: [{valid_ids_str}]"
                        )
                        
                        # 追加反馈到用户输入，准备下一次重试
                        current_user_input = user_input + feedback
                        logger.debug(f"已追加系统反馈，准备第 {attempt + 2}/{max_retries} 次重试...")
                        continue  # 继续下一轮循环
                
                # ========== ID 有效或不需要验证，返回结果 ==========
                normalized = normalize_llm_response(result)
                logger.debug(
                    f"LLMClient 推理成功 (第 {attempt + 1} 次): "
                    f"action={normalized.get('action')}, element_id={element_id}"
                )
                return normalized
                
            except LLMError as e:
                # 如果是最后一次重试，直接抛出
                if attempt == max_retries - 1:
                    logger.error(f"LLMClient 达到最大重试次数，最后异常: {str(e)}")
                    raise
                # 否则继续重试
                logger.warning(f"第 {attempt + 1} 次推理请求失败: {str(e)}, 准备重试...")
                continue
            except Exception as e:
                # 非 LLMError 异常也记录并重试
                if attempt == max_retries - 1:
                    logger.error(f"LLMClient 达到最大重试次数，最后异常: {str(e)}")
                    raise LLMError(f"LLMClient 推理失败: {str(e)}")
                logger.warning(f"第 {attempt + 1} 次推理请求异常: {str(e)}, 准备重试...")
                continue
        
        # ========== 如果所有重试都因为 ID 幻觉而失败 ==========
        raise LLMError(
            f"多次重试均未获取到合法的 element_id (有效 ID 列表: {valid_element_ids})"
        )

    def _extract_element_id(self, result: Any) -> Optional[int]:
        """
        从 LLM 返回的结果中提取 element_id。

        支持多种格式的结果：字典、JSON 字符串等。

        Args:
            result: LLM 返回的结果（字典或 JSON 字符串）

        Returns:
            Optional[int]: 提取到的 element_id，如果不存在则返回 None
        """
        try:
            # 如果是字符串，尝试解析为 JSON
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except json.JSONDecodeError:
                    return None
            
            # 现在 result 应该是字典
            if not isinstance(result, dict):
                return None
            
            # 尝试从 target.element_id 或 action.element_id 提取
            target = result.get("target")
            if isinstance(target, dict):
                element_id = target.get("element_id")
                if element_id is not None and isinstance(element_id, (int, float)):
                    return int(element_id)
            
            # 备选路径：直接从 action 中提取
            action = result.get("action")
            if isinstance(action, dict):
                element_id = action.get("element_id")
                if element_id is not None and isinstance(element_id, (int, float)):
                    return int(element_id)
            
            return None
        except Exception as e:
            logger.debug(f"提取 element_id 时异常: {str(e)}")
            return None

    async def _chat_auto(
        self,
        system_prompt: str,
        user_input: str,
        temperature: float,
        max_tokens: int,
        image_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        自动路径（双模态智能路由）。

        - 如果 image_path 不为空：调用视觉客户端 (role="vision") 执行 chat_with_vision
        - 如果 image_path 为空：调用逻辑文本客户端 (role="logic") 执行 chat
        """
        if image_path:
            # 视觉模态路由
            vision_client = LLMFactory.get_instance(role="vision")
            return await vision_client.chat_with_vision(
                system_prompt=system_prompt,
                user_input=user_input,
                image_path=image_path,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            # 逻辑文本模态路由
            logic_client = LLMFactory.get_instance(role="logic")
            return await logic_client.chat(
                system_prompt=system_prompt,
                user_input=user_input,
                temperature=temperature,
                max_tokens=max_tokens,
            )

    async def _chat_manual(
        self,
        system_prompt: str,
        user_input: str,
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        """
        手动路径（人工输入）：
        - 接收完整的 system_prompt + user_input
        - 读取 JSON 输入
        - 返回可被统一标准化的结构
        """
        del temperature
        del max_tokens

        print("\n" + "=" * 80)
        print("🤖 【手动逻辑推理模式】")
        print("=" * 80)
        print("系统提示词:")
        print(system_prompt)
        print("\n用户提示词:")
        print(user_input)
        print("=" * 80)

        loop = asyncio.get_event_loop()
        try:
            raw_text = await loop.run_in_executor(
                None,
                self._read_multiline_input,
                "请输入JSON决策（包含 thought 和 action）",
            )
        except KeyboardInterrupt:
            raw_text = json.dumps(
                {
                    "thought": "用户中止了推理过程",
                    "action": "wait",
                    "target": {},
                    "input": {"delay": 1000},
                },
                ensure_ascii=False,
            )

        return raw_text

    def _read_multiline_input(self, prompt: str) -> str:
        """
        读取多行输入，连续两次空行提交。
        """
        print(f"\n{prompt}")
        print("[粘贴后按两次回车提交，Ctrl+C 取消]\n")

        lines = []
        empty_count = 0

        while True:
            line = sys.stdin.readline()
            if not line:
                break

            if line.strip() == "":
                empty_count += 1
                if empty_count >= 2:
                    break
                lines.append("")
                continue

            empty_count = 0
            lines.append(line.rstrip("\n"))

        while lines and lines[-1].strip() == "":
            lines.pop()

        return "\n".join(lines)
