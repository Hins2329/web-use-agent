"""
任务状态机模块

维护 Agent 的任务执行状态，包括目标、子目标、里程碑和阻塞项。
TaskState 是 Agent 的工作记忆核心，在上下文压缩时永不丢弃。
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
import json

from ...utils.logger import setup_logger


logger = setup_logger("agent")


@dataclass
class SubGoal:
    """
    子目标数据类
    
    Attributes:
        description: 子目标描述
        status: 子目标状态 ("pending" / "completed" / "blocked")
    """
    description: str
    status: str = "pending"  # "pending" / "completed" / "blocked"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubGoal":
        """从字典创建 SubGoal 实例"""
        return cls(
            description=data.get("description", ""),
            status=data.get("status", "pending")
        )


@dataclass
class TaskState:
    """
    任务状态数据类
    
    TaskState 是 Agent 的工作记忆核心，记录任务执行的完整状态。
    在上下文压缩时，TaskState 永不丢弃。
    
    Attributes:
        task_id: 任务唯一标识（预留多轮对话用，当前单任务填 "task_1"）
        goal: 用户原始目标，永不修改
        sub_goals: 子目标列表，任务开始时由 LLM 生成，可动态追加
        milestones: 已完成的关键里程碑描述列表
        blockers: 当前阻塞项列表
        step_count: 已执行步数
    """
    
    # 子目标数量上限
    MAX_SUB_GOALS = 10
    
    task_id: str
    goal: str
    sub_goals: List[SubGoal] = field(default_factory=list)
    milestones: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    step_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式
        
        Returns:
            Dict[str, Any]: 字典表示
        """
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "sub_goals": [sg.to_dict() for sg in self.sub_goals],
            "milestones": self.milestones.copy(),
            "blockers": self.blockers.copy(),
            "step_count": self.step_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskState":
        """
        从字典创建 TaskState 实例
        
        Args:
            data: 字典数据
            
        Returns:
            TaskState: TaskState 实例
        """
        return cls(
            task_id=data.get("task_id", "task_1"),
            goal=data.get("goal", ""),
            sub_goals=[SubGoal.from_dict(sg) for sg in data.get("sub_goals", [])],
            milestones=data.get("milestones", []).copy(),
            blockers=data.get("blockers", []).copy(),
            step_count=data.get("step_count", 0)
        )
    
    def to_json(self, indent: Optional[int] = None) -> str:
        """
        转换为 JSON 字符串
        
        Args:
            indent: JSON 缩进级别（可选）
            
        Returns:
            str: JSON 字符串
        """
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
    
    def serialize_for_prompt(self) -> str:
        """
        序列化为适合注入 LLM prompt 的文本格式
        
        该方法将 TaskState 转换为紧凑、易读的文本格式，用于注入到 system_prompt 中。
        
        Returns:
            str: 格式化的文本字符串
        """
        lines = [
            "【任务状态】",
            f"任务ID: {self.task_id}",
            f"目标: {self.goal}",
            f"已执行步数: {self.step_count}",
            ""
        ]
        
        # 子目标列表
        if self.sub_goals:
            lines.append("子目标进度:")
            for i, sub_goal in enumerate(self.sub_goals, 1):
                status_icon = {
                    "pending": "⏳",
                    "completed": "✓",
                    "blocked": "🚫"
                }.get(sub_goal.status, "?")
                lines.append(f"  {i}. [{status_icon}] {sub_goal.description} ({sub_goal.status})")
        else:
            lines.append("子目标进度: （无）")
        
        lines.append("")
        
        # 已完成的里程碑
        if self.milestones:
            lines.append("已完成的里程碑:")
            for milestone in self.milestones:
                lines.append(f"  ✓ {milestone}")
        else:
            lines.append("已完成的里程碑: （无）")
        
        lines.append("")
        
        # 当前阻塞项
        if self.blockers:
            lines.append("当前阻塞项:")
            for blocker in self.blockers:
                lines.append(f"  🚫 {blocker}")
        else:
            lines.append("当前阻塞项: （无）")
        
        return "\n".join(lines)
    
    def update_from_llm_response(self, state_update: Dict[str, Any]) -> None:
        """
        根据 LLM 返回的 state_update 字段更新 TaskState
        
        支持的更新操作：
        - complete_sub_goal: 完成指定索引的子目标（索引从 0 开始）
        - add_sub_goal: 添加新的子目标
        - add_milestone: 添加新的里程碑
        - add_blocker: 添加新的阻塞项
        - remove_blocker: 移除指定的阻塞项
        - block_sub_goal: 将指定索引的子目标标记为 blocked
        
        Args:
            state_update: LLM 返回的状态更新字典
        """
        if not state_update or not isinstance(state_update, dict):
            return
        
        # 完成子目标
        complete_idx = state_update.get("complete_sub_goal")
        if complete_idx is not None and isinstance(complete_idx, int):
            if 0 <= complete_idx < len(self.sub_goals):
                self.sub_goals[complete_idx].status = "completed"
        
        # 添加新子目标
        new_sub_goal = state_update.get("add_sub_goal")
        if new_sub_goal and isinstance(new_sub_goal, str):
            self.add_sub_goal(new_sub_goal)
        
        # 添加里程碑
        new_milestone = state_update.get("add_milestone")
        if new_milestone and isinstance(new_milestone, str):
            self.milestones.append(new_milestone)
        
        # 添加阻塞项
        new_blocker = state_update.get("add_blocker")
        if new_blocker and isinstance(new_blocker, str):
            self.blockers.append(new_blocker)
        
        # 移除阻塞项
        remove_blocker = state_update.get("remove_blocker")
        if remove_blocker and isinstance(remove_blocker, str):
            if remove_blocker in self.blockers:
                self.blockers.remove(remove_blocker)
        
        # 阻塞子目标
        block_idx = state_update.get("block_sub_goal")
        if block_idx is not None and isinstance(block_idx, int):
            if 0 <= block_idx < len(self.sub_goals):
                self.sub_goals[block_idx].status = "blocked"
    
    def increment_step(self) -> None:
        """增加步数计数"""
        self.step_count += 1
    
    def add_sub_goal(self, description: str) -> bool:
        """
        添加新的子目标
        
        Args:
            description: 子目标描述
            
        Returns:
            bool: True 表示添加成功，False 表示已达上限被拒绝
        """
        if len(self.sub_goals) >= self.MAX_SUB_GOALS:
            logger.warning(
                f"⚠️ 子目标数量已达上限({self.MAX_SUB_GOALS})，"
                f"拒绝添加: {description[:50]}..."
            )
            return False
        
        self.sub_goals.append(SubGoal(description=description, status="pending"))
        return True
