"""
上下文压缩管理器模块

监控 LLM 上下文长度，触发阈值时按优先级重组消息，确保关键信息永不丢失。
"""

from typing import List, Dict, Any, Optional
import json

from ...utils.logger import setup_logger


logger = setup_logger("agent")


class ContextManager:
    """
    上下文压缩管理器
    
    负责监控 LLM 上下文长度，当超过阈值时按优先级重组消息：
    1. System message（永不压缩）
    2. TaskState（永不丢弃）
    3. MILESTONE 记录（永不丢弃）
    4. 压缩后的 NORMAL 记录摘要
    5. 最新的感知状态和用户输入
    
    Attributes:
        threshold_ratio: 触发压缩的阈值比例（默认 0.8）
        model_max_tokens: 模型最大 token 数（默认 128000）
    """
    
    def __init__(self, threshold_ratio: float = 0.8, model_max_tokens: int = 128000):
        """
        初始化上下文压缩管理器
        
        Args:
            threshold_ratio: 触发压缩的阈值比例（0-1 之间）
            model_max_tokens: 模型最大 token 数
        """
        self.threshold_ratio = threshold_ratio
        self.model_max_tokens = model_max_tokens
        self.compression_threshold = int(model_max_tokens * threshold_ratio)
        logger.debug(f"✓ ContextManager 已初始化: 阈值={self.compression_threshold} tokens")
    
    def estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """
        粗估消息列表的 token 数量
        
        使用简单规则：len(text) / 2（中英文混合场景够用）
        不引入 tiktoken 等第三方依赖。
        
        Args:
            messages: 消息列表
            
        Returns:
            int: 估算的 token 数量
        """
        total_chars = 0
        
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                # 多模态消息（包含图像）
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text", "")
                        total_chars += len(text)
        
        # 粗估：字符数 / 2
        estimated_tokens = total_chars // 2
        return estimated_tokens
    
    def should_compress(self, messages: List[Dict[str, Any]]) -> bool:
        """
        判断是否需要压缩上下文
        
        Args:
            messages: 消息列表
            
        Returns:
            bool: 是否需要压缩
        """
        estimated_tokens = self.estimate_tokens(messages)
        should_compress = estimated_tokens > self.compression_threshold
        
        if should_compress:
            logger.info(f"🔄 上下文压缩触发: {estimated_tokens} tokens > {self.compression_threshold} tokens")
        else:
            logger.debug(f"✓ 上下文未超限: {estimated_tokens} tokens <= {self.compression_threshold} tokens")
        
        return should_compress
    
    async def compress(
        self,
        messages: List[Dict[str, Any]],
        task_state: Optional[Any],
        action_history: List[Dict[str, Any]],
        llm_client: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        压缩上下文消息列表
        
        按优先级重组消息：
        1. System message（原封不动）
        2. TaskState 快照
        3. MILESTONE 记录
        4. 压缩后的 NORMAL 记录摘要
        5. 最新的 2 条消息（感知状态 + 用户输入）
        
        Args:
            messages: 原始消息列表
            task_state: 任务状态对象（TaskState）
            action_history: 动作历史列表
            llm_client: LLM 客户端（用于压缩 NORMAL 记录）
            
        Returns:
            List[Dict[str, Any]]: 压缩后的消息列表
        """
        logger.info("开始压缩上下文...")
        
        compressed_messages = []
        
        # ========== 优先级 1: System message（原封不动保留） ==========
        system_message = None
        for msg in messages:
            if msg.get("role") == "system":
                system_message = msg
                break
        
        if system_message:
            compressed_messages.append(system_message)
            logger.debug("✓ 保留 System message")
        
        # ========== 优先级 2: TaskState 快照（永不丢弃） ==========
        if task_state:
            task_state_text = task_state.serialize_for_prompt()
            compressed_messages.append({
                "role": "user",
                "content": f"[任务状态快照 - 压缩恢复]\n\n{task_state_text}"
            })
            logger.debug("✓ 注入 TaskState 快照")
        
        # ========== 优先级 3: MILESTONE 记录（永不丢弃） ==========
        milestones = [h for h in action_history if h.get("tag") == "MILESTONE"]
        if milestones:
            milestone_text = self._format_milestones(milestones)
            compressed_messages.append({
                "role": "user",
                "content": f"[关键里程碑 - 压缩恢复]\n\n{milestone_text}"
            })
            logger.debug(f"✓ 注入 {len(milestones)} 条 MILESTONE 记录")
        
        # ========== 优先级 4: 压缩 NORMAL 记录 ==========
        normals = [h for h in action_history if h.get("tag") == "NORMAL"]
        if normals:
            normal_summary = await self._compress_normals(normals, llm_client)
            compressed_messages.append({
                "role": "user",
                "content": f"[普通操作摘要 - 压缩恢复]\n\n{normal_summary}"
            })
            logger.debug(f"✓ 压缩 {len(normals)} 条 NORMAL 记录为摘要")
        
        # ========== 优先级 5: 最新的 2 条消息 ==========
        # 保留最新的感知状态和用户输入
        latest_messages = [msg for msg in messages if msg.get("role") != "system"][-2:]
        compressed_messages.extend(latest_messages)
        logger.debug(f"✓ 保留最新的 {len(latest_messages)} 条消息")
        
        # 统计压缩效果
        original_tokens = self.estimate_tokens(messages)
        compressed_tokens = self.estimate_tokens(compressed_messages)
        compression_ratio = (1 - compressed_tokens / original_tokens) * 100 if original_tokens > 0 else 0
        
        logger.info(
            f"✓ 上下文压缩完成: {original_tokens} tokens → {compressed_tokens} tokens "
            f"(压缩率: {compression_ratio:.1f}%)"
        )
        
        return compressed_messages
    
    def _format_milestones(self, milestones: List[Dict[str, Any]]) -> str:
        """
        格式化 MILESTONE 记录为文本
        
        Args:
            milestones: MILESTONE 记录列表
            
        Returns:
            str: 格式化后的文本
        """
        lines = []
        
        for i, entry in enumerate(milestones, 1):
            if "decision" in entry:
                decision = entry["decision"]
                result = entry.get("result", {})
                action_type = decision.get("action", "unknown")
                success = result.get("success", False)
                message = result.get("message", "")
                
                status = "✓" if success else "✗"
                lines.append(f"{i}. {status} {action_type}")
                
                if message:
                    short_message = message[:100] + "..." if len(message) > 100 else message
                    lines.append(f"   {short_message}")
            else:
                # 旧格式兼容
                action_type = entry.get("action", "unknown")
                lines.append(f"{i}. {action_type}")
        
        return "\n".join(lines) if lines else "（无里程碑记录）"
    
    async def _compress_normals(
        self,
        normals: List[Dict[str, Any]],
        llm_client: Optional[Any]
    ) -> str:
        """
        使用 LLM 压缩 NORMAL 记录为摘要
        
        Args:
            normals: NORMAL 记录列表
            llm_client: LLM 客户端
            
        Returns:
            str: 压缩后的摘要文本
        """
        if not normals:
            return "（无普通操作记录）"
        
        # 格式化 NORMAL 记录为文本
        normals_text = self._format_normals(normals)
        
        # 如果没有 LLM 客户端，降级为直接截断
        if not llm_client:
            logger.warning("⚠️  未提供 LLM 客户端，降级为直接截断 NORMAL 记录")
            return self._fallback_compress_normals(normals)
        
        # 调用 LLM 压缩
        try:
            logger.debug("调用 LLM 压缩 NORMAL 记录...")
            
            system_prompt = "你是一个文本摘要专家。请用2-3句话总结以下 Agent 操作历史，只保留关键信息。"
            user_input = f"请总结以下操作历史：\n\n{normals_text}"
            
            # 调用 LLM（使用压缩模型）
            response = await llm_client.chat(
                system_prompt=system_prompt,
                user_input=user_input,
                temperature=0.3,
                max_tokens=200,
                image_path=None,
                valid_element_ids=None,
                # 关键：不传入 context_manager，避免递归压缩
                context_manager=None
            )
            
            # 提取摘要文本
            if isinstance(response, dict):
                summary = response.get("thought", "") or response.get("summary", "") or str(response)
            else:
                summary = str(response)
            
            logger.debug(f"✓ LLM 压缩成功: {len(normals)} 条 → {len(summary)} 字符")
            return summary
            
        except Exception as e:
            logger.warning(f"⚠️  LLM 压缩失败: {e}，降级为直接截断")
            return self._fallback_compress_normals(normals)
    
    def _format_normals(self, normals: List[Dict[str, Any]]) -> str:
        """
        格式化 NORMAL 记录为文本
        
        Args:
            normals: NORMAL 记录列表
            
        Returns:
            str: 格式化后的文本
        """
        lines = []
        
        for i, entry in enumerate(normals, 1):
            if "decision" in entry:
                decision = entry["decision"]
                result = entry.get("result", {})
                action_type = decision.get("action", "unknown")
                success = result.get("success", False)
                
                status = "✓" if success else "✗"
                lines.append(f"{i}. {status} {action_type}")
            else:
                # 旧格式兼容
                action_type = entry.get("action", "unknown")
                lines.append(f"{i}. {action_type}")
        
        return "\n".join(lines) if lines else "（无普通操作记录）"
    
    def _fallback_compress_normals(self, normals: List[Dict[str, Any]]) -> str:
        """
        降级压缩策略：直接截断 NORMAL 记录
        
        Args:
            normals: NORMAL 记录列表
            
        Returns:
            str: 截断后的文本
        """
        # 只保留最近 5 条
        recent_normals = normals[-5:] if len(normals) > 5 else normals
        omitted = len(normals) - len(recent_normals)
        
        lines = []
        if omitted > 0:
            lines.append(f"（已省略 {omitted} 条普通操作，保留最近 {len(recent_normals)} 条）")
            lines.append("")
        
        lines.append(self._format_normals(recent_normals))
        
        return "\n".join(lines)
