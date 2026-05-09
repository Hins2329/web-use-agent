"""
死循环监控器模块

基于信息熵算法实现防死循环逻辑，监控 Agent 的动作模式并在检测到循环时触发熔断。
"""

import math
from collections import deque, Counter
from typing import Optional, Dict, Any, List, Tuple


class LoopMonitor:
    """
    死循环监控器
    
    基于滑动窗口监控 Agent 的动作模式，计算动作熵、状态熵和震荡分数，
    当检测到循环模式时触发熔断并返回警告信息。
    
    核心指标：
    - Action Entropy（动作熵）：衡量动作的多样性
    - State Entropy（状态熵）：衡量认知状态的多样性
    - Oscillation Score（震荡分数）：检测 A-B-A-B 模式的震荡行为
    
    触发条件：
    1. (Action Entropy < 0.5 and State Entropy < 0.3)
    2. Oscillation Score >= 2
    """
    
    # 认知状态分类
    EXPLORATION_ACTIONS = {"read_file", "scroll", "wait"}
    INTERACTION_ACTIONS = {
        "click", "type", "upload_file", "select_option", 
        "navigate", "done", "human_intervene"
    }
    
    # 熵阈值
    ACTION_ENTROPY_THRESHOLD = 0.5
    STATE_ENTROPY_THRESHOLD = 0.3
    OSCILLATION_THRESHOLD = 2
    
    def __init__(self, window_size: int = 3):
        """
        初始化死循环监控器
        
        Args:
            window_size: 滑动窗口大小，默认为 3（连续 3 次相同动作触发熔断）
        """
        self.window_size = window_size
        # 使用 deque 实现固定长度的滑动窗口
        self.action_signatures: deque = deque(maxlen=window_size)
        self.cognitive_states: deque = deque(maxlen=window_size)
    
    def check_and_add(self, decision: Dict[str, Any]) -> Optional[str]:
        """
        检查决策并添加到滑动窗口，如果检测到循环则返回警告信息
        
        Args:
            decision: LLM 的决策字典，包含 action, target, input, options 等字段
        
        Returns:
            Optional[str]: 如果检测到循环，返回格式化的警告信息；否则返回 None
        """
        # 提取动作签名和认知状态
        signature = self._extract_signature(decision)
        state = self._classify_cognitive_state(decision)
        
        # 添加到滑动窗口
        self.action_signatures.append(signature)
        self.cognitive_states.append(state)
        
        # 只有当窗口已满时才进行检测
        if len(self.action_signatures) < self.window_size:
            return None
        
        # 计算熵和震荡分数
        action_entropy = self._calculate_entropy(list(self.action_signatures))
        state_entropy = self._calculate_entropy(list(self.cognitive_states))
        oscillation_score = self._calculate_oscillation(list(self.action_signatures))
        
        # 检查是否触发熔断条件
        entropy_triggered = (
            action_entropy < self.ACTION_ENTROPY_THRESHOLD and 
            state_entropy < self.STATE_ENTROPY_THRESHOLD
        )
        oscillation_triggered = oscillation_score >= self.OSCILLATION_THRESHOLD
        
        if entropy_triggered or oscillation_triggered:
            return self._format_warning(
                action_entropy, 
                state_entropy, 
                oscillation_score,
                list(self.action_signatures)
            )
        
        return None
    
    def clear(self):
        """
        清空滑动窗口
        
        当页面导航发生变化时应调用此方法，因为页面刷新代表死循环破除。
        """
        self.action_signatures.clear()
        self.cognitive_states.clear()
    
    def _extract_signature(self, decision: Dict[str, Any]) -> str:
        """
        提取动作签名
        
        签名格式：action_type_{element_id}_{text/url/file_path}
        
        Args:
            decision: LLM 的决策字典
        
        Returns:
            str: 动作签名字符串
        """
        action_type = decision.get("action", "unknown")
        target = decision.get("target", {})
        input_data = decision.get("input", {})
        
        # 提取核心参数
        element_id = target.get("element_id", "") if isinstance(target, dict) else ""
        
        # 根据动作类型提取不同的输入参数
        if isinstance(input_data, dict):
            param = (
                input_data.get("text") or 
                input_data.get("url") or 
                input_data.get("file_path") or 
                ""
            )
        else:
            param = ""
        
        # 构造签名（截断长参数以避免签名过长）
        if param and len(str(param)) > 20:
            param = str(param)[:20]
        
        signature = f"{action_type}_{element_id}_{param}"
        return signature
    
    def _classify_cognitive_state(self, decision: Dict[str, Any]) -> str:
        """
        分类认知状态
        
        Args:
            decision: LLM 的决策字典
        
        Returns:
            str: 认知状态 ("Exploration" 或 "Interaction")
        """
        action_type = decision.get("action", "unknown")
        
        if action_type in self.EXPLORATION_ACTIONS:
            return "Exploration"
        elif action_type in self.INTERACTION_ACTIONS:
            return "Interaction"
        else:
            # 未知动作默认归类为 Interaction
            return "Interaction"
    
    def _calculate_entropy(self, items: List[str]) -> float:
        """
        计算 Shannon 熵
        
        H(X) = -Σ p(x) * log2(p(x))
        
        Args:
            items: 项目列表（动作签名或认知状态）
        
        Returns:
            float: 信息熵值，范围 [0, log2(n)]
        """
        if not items:
            return 0.0
        
        # 统计频率
        counter = Counter(items)
        total = len(items)
        
        # 计算熵
        entropy = 0.0
        for count in counter.values():
            if count > 0:  # 防止 log2(0)
                probability = count / total
                entropy -= probability * math.log2(probability)
        
        return entropy
    
    def _calculate_oscillation(self, signatures: List[str]) -> int:
        """
        计算震荡分数
        
        检测 A-B-A-B 模式的震荡行为，统计相邻动作对的反向重复次数。
        
        Args:
            signatures: 动作签名列表
        
        Returns:
            int: 震荡分数
        """
        if len(signatures) < 2:
            return 0
        
        # 统计唯一签名数量
        unique_count = len(set(signatures))
        
        # 如果唯一签名数量 > 2，不太可能是简单震荡
        if unique_count > 2:
            return 0
        
        # 检测相邻动作对的反向重复
        oscillation_count = 0
        for i in range(len(signatures) - 3):
            # 检测 A-B-A-B 模式
            if (signatures[i] == signatures[i+2] and 
                signatures[i+1] == signatures[i+3] and 
                signatures[i] != signatures[i+1]):
                oscillation_count += 1
        
        return oscillation_count
    
    def _format_warning(
        self, 
        action_entropy: float, 
        state_entropy: float, 
        oscillation_score: int,
        recent_signatures: List[str]
    ) -> str:
        """
        格式化警告信息
        
        Args:
            action_entropy: 动作熵
            state_entropy: 状态熵
            oscillation_score: 震荡分数
            recent_signatures: 最近的动作签名列表
        
        Returns:
            str: 格式化的警告信息
        """
        # 构造醒目的血红警告
        warning_lines = [
            "",
            "=" * 80,
            "⚠️  【死循环警告】你已陷入循环模式！",
            "=" * 80,
            "",
            f"📊 监控指标：",
            f"  • 动作熵 (Action Entropy): {action_entropy:.2f} (阈值: {self.ACTION_ENTROPY_THRESHOLD})",
            f"  • 状态熵 (State Entropy): {state_entropy:.2f} (阈值: {self.STATE_ENTROPY_THRESHOLD})",
            f"  • 震荡分数 (Oscillation Score): {oscillation_score} (阈值: {self.OSCILLATION_THRESHOLD})",
            "",
            f"🔄 最近 {len(recent_signatures)} 步动作签名：",
        ]
        
        # 添加最近的动作签名
        for i, sig in enumerate(recent_signatures, 1):
            warning_lines.append(f"  {i}. {sig}")
        
        warning_lines.extend([
            "",
            "💡 建议策略：",
            "  1. 尝试不同的动作（避免重复相同操作）",
            "  2. 切换到不同的页面或元素",
            "  3. 使用 scroll 探索页面其他区域",
            "  4. 如果确实无法继续，请使用 human_intervene 请求人工介入",
            "",
            "=" * 80,
            ""
        ])
        
        return "\n".join(warning_lines)
