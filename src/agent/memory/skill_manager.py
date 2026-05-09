"""
技能管理器模块

负责经验反思提炼与本地持久化存储，实现 Self-Learning 机制。
"""

import json
import uuid
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from threading import Lock

from ...utils.logger import setup_logger
from ...utils.exceptions import LLMError


logger = setup_logger("agent")


class SkillManager:
    """
    技能管理器
    
    负责：
    1. 反思提炼：将成功任务的 action_history 总结为通用 Skill
    2. 本地存储：持久化技能到 JSON 文件
    3. 技能检索：基于意图匹配检索相关技能（未来扩展）
    
    架构约束：
    - 纯粹的经验管理类，不参与网页执行
    - 不直接调用 perception、execution 或 tools 模块
    - 不修改 workflow 的循环控制逻辑
    """
    
    # 反思提示词模板
    REFLECTION_SYSTEM_PROMPT = """你是一个经验提炼大师。你的任务是从成功完成的任务历史中提炼出通用的操作指导（SOP）。

【核心约束】
1. **去具体化**：绝对禁止在 SOP 中保留具体的 element_id、选择器、坐标等实例化信息
   - ❌ 错误示例："点击 element_id=5"
   - ✅ 正确示例："点击搜索按钮"

2. **过滤废动作**：历史中可能包含试错、死循环警告（system_warning）和兜底动作，请过滤掉这些废动作

3. **提炼主线**：只保留达成目标的核心主线逻辑，输出为精简的通用步骤

4. **语义描述**：使用自然语言描述操作意图，而非技术细节
   - ❌ 错误示例："在 input[name='q'] 中输入文本"
   - ✅ 正确示例："在搜索框中输入关键词"

5. **通用性**：SOP 应该适用于类似的任务场景，而非仅限于当前页面

【输出格式】
请输出一个简洁的 SOP 文本，每个步骤占一行，使用数字编号。

示例输出：
1. 导航到目标网站
2. 在搜索框中输入关键词
3. 点击搜索按钮
4. 等待搜索结果加载
5. 点击第一个搜索结果
"""
    
    # 失败反思提示词模板
    FAILURE_REFLECTION_SYSTEM_PROMPT = """你是一个失败经验提炼专家。你的任务是从失败的任务历史中提炼出失败的根本原因和规避建议。

【核心约束】
1. **识别根本原因**：分析失败的根本原因，而非表面现象
   - ❌ 错误示例："点击失败"
   - ✅ 正确示例："目标元素不可点击，可能被遮挡或未加载完成"

2. **提供可执行建议**：规避建议应该是具体、可执行的步骤
   - ❌ 错误示例："注意页面状态"
   - ✅ 正确示例："在点击前先等待页面加载完成，使用 wait 动作确认元素可见"

3. **去具体化**：不要保留具体的 element_id、选择器、坐标等信息
   - ❌ 错误示例："element_id=5 点击失败"
   - ✅ 正确示例："搜索按钮点击失败"

4. **简洁明了**：失败特征和建议都应该简洁明了，避免冗长描述

【输出格式】
请输出一个 JSON 对象，包含两个字段：

{
  "failure_summary": "失败特征和根本原因的描述",
  "suggestion": "规避建议"
}

【示例输出】
{
  "failure_summary": "在搜索结果页面无法找到目标商品，Agent 陷入重复滚动死循环",
  "suggestion": "在搜索前先明确商品关键词，搜索后检查结果数量，如果结果为空则调整关键词重新搜索"
}
"""

    def __init__(self, skills_file_path: Optional[str] = None):
        """
        初始化技能管理器
        
        Args:
            skills_file_path: 技能库文件路径，默认为 browser_data/skills_library.json
        """
        # 确定技能库文件路径
        if skills_file_path is None:
            # 默认路径：browser_data/skills_library.json
            project_root = Path(__file__).parent.parent.parent.parent
            skills_dir = project_root / "browser_data"
            skills_dir.mkdir(parents=True, exist_ok=True)
            self.skills_file_path = skills_dir / "skills_library.json"
            self.failure_patterns_file_path = skills_dir / "failure_patterns.json"
        else:
            self.skills_file_path = Path(skills_file_path)
            self.skills_file_path.parent.mkdir(parents=True, exist_ok=True)
            self.failure_patterns_file_path = self.skills_file_path.parent / "failure_patterns.json"
        
        # 线程锁，确保文件读写安全
        self._lock = Lock()
        self._failure_patterns_lock = Lock()
        
        # 初始化时加载技能库
        self.skills: List[Dict[str, Any]] = self._load_skills()
        
        # 初始化时加载失败模式库
        self.failure_patterns: List[Dict[str, Any]] = self._load_failure_patterns()
        
        logger.info(f"✓ SkillManager 已初始化，技能库路径: {self.skills_file_path}")
        logger.info(f"✓ 当前技能库包含 {len(self.skills)} 个技能")
        logger.info(f"✓ 当前失败模式库包含 {len(self.failure_patterns)} 个失败模式")
    
    def _load_skills(self) -> List[Dict[str, Any]]:
        """
        从本地 JSON 文件加载技能库
        
        Returns:
            List[Dict[str, Any]]: 技能列表
        """
        with self._lock:
            try:
                if not self.skills_file_path.exists():
                    logger.debug(f"技能库文件不存在，创建空文件: {self.skills_file_path}")
                    self._save_skills_unsafe([])
                    return []
                
                with open(self.skills_file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    
                    # 处理空文件
                    if not content:
                        logger.debug("技能库文件为空，返回空列表")
                        return []
                    
                    # 解析 JSON
                    skills = json.loads(content)
                    
                    # 验证格式
                    if not isinstance(skills, list):
                        logger.warning(f"技能库格式错误（非列表），重置为空列表")
                        self._save_skills_unsafe([])
                        return []
                    
                    logger.debug(f"成功加载 {len(skills)} 个技能")
                    return skills
                    
            except json.JSONDecodeError as e:
                logger.error(f"技能库 JSON 解析失败: {e}，重置为空列表")
                self._save_skills_unsafe([])
                return []
            except Exception as e:
                logger.error(f"加载技能库失败: {e}，返回空列表")
                return []
    
    def _load_failure_patterns(self) -> List[Dict[str, Any]]:
        """
        从本地 JSON 文件加载失败模式库
        
        Returns:
            List[Dict[str, Any]]: 失败模式列表
        """
        with self._failure_patterns_lock:
            try:
                if not self.failure_patterns_file_path.exists():
                    logger.debug(f"失败模式库文件不存在，创建空文件: {self.failure_patterns_file_path}")
                    self._save_failure_patterns_unsafe([])
                    return []
                
                with open(self.failure_patterns_file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    
                    # 处理空文件
                    if not content:
                        logger.debug("失败模式库文件为空，返回空列表")
                        return []
                    
                    # 解析 JSON
                    patterns = json.loads(content)
                    
                    # 验证格式
                    if not isinstance(patterns, list):
                        logger.warning(f"失败模式库格式错误（非列表），重置为空列表")
                        self._save_failure_patterns_unsafe([])
                        return []
                    
                    logger.debug(f"成功加载 {len(patterns)} 个失败模式")
                    return patterns
                    
            except json.JSONDecodeError as e:
                logger.error(f"失败模式库 JSON 解析失败: {e}，重置为空列表")
                self._save_failure_patterns_unsafe([])
                return []
            except Exception as e:
                logger.error(f"加载失败模式库失败: {e}，返回空列表")
                return []
    
    def _save_skills(self, skills: List[Dict[str, Any]]) -> None:
        """
        保存技能库到本地 JSON 文件（线程安全）
        
        Args:
            skills: 技能列表
        """
        with self._lock:
            self._save_skills_unsafe(skills)
    
    def _save_skills_unsafe(self, skills: List[Dict[str, Any]]) -> None:
        """
        保存技能库到本地 JSON 文件（非线程安全，内部使用）
        
        Args:
            skills: 技能列表
        """
        try:
            with open(self.skills_file_path, "w", encoding="utf-8") as f:
                json.dump(skills, f, ensure_ascii=False, indent=2)
            logger.debug(f"技能库已保存: {len(skills)} 个技能")
        except Exception as e:
            logger.error(f"保存技能库失败: {e}")
            raise
    
    def _save_failure_patterns(self, patterns: List[Dict[str, Any]]) -> None:
        """
        保存失败模式库到本地 JSON 文件（线程安全）
        
        Args:
            patterns: 失败模式列表
        """
        with self._failure_patterns_lock:
            self._save_failure_patterns_unsafe(patterns)
    
    def _save_failure_patterns_unsafe(self, patterns: List[Dict[str, Any]]) -> None:
        """
        保存失败模式库到本地 JSON 文件（非线程安全，内部使用）
        
        Args:
            patterns: 失败模式列表
        """
        try:
            with open(self.failure_patterns_file_path, "w", encoding="utf-8") as f:
                json.dump(patterns, f, ensure_ascii=False, indent=2)
            logger.debug(f"失败模式库已保存: {len(patterns)} 个失败模式")
        except Exception as e:
            logger.error(f"保存失败模式库失败: {e}")
            raise
    
    async def reflect_and_extract(
        self,
        goal: str,
        action_history: List[Dict[str, Any]],
        llm_client
    ) -> str:
        """
        反思提炼：将成功任务的操作历史总结为通用 SOP
        
        Args:
            goal: 任务目标
            action_history: 操作历史列表
            llm_client: LLMClient 实例，用于调用 LLM 进行反思
        
        Returns:
            str: 提炼后的通用 SOP 文本
        
        Raises:
            LLMError: LLM 调用失败时抛出
        """
        logger.info("开始反思提炼经验...")
        
        # 构造用户输入
        user_input = self._format_reflection_input(goal, action_history)
        
        try:
            # 调用 LLM 进行反思（纯文本模式，不需要图像）
            result = await llm_client.chat(
                system_prompt=self.REFLECTION_SYSTEM_PROMPT,
                user_input=user_input,
                temperature=0.7,  # 适度的创造性
                max_tokens=1000,  # 足够生成 SOP
                image_path=None,  # 反思不需要图像
                valid_element_ids=None,  # 反思不需要 ID 验证
            )
            
            # 提取 SOP 文本
            sop_text = self._extract_sop_from_result(result)
            
            logger.info(f"✓ 反思提炼完成，生成 SOP 长度: {len(sop_text)} 字符")
            logger.debug(f"生成的 SOP:\n{sop_text}")
            
            return sop_text
            
        except LLMError as e:
            logger.error(f"反思提炼失败（LLM 错误）: {e}")
            raise
        except Exception as e:
            logger.error(f"反思提炼失败（未知错误）: {e}")
            raise LLMError(f"反思提炼失败: {e}")
    
    def _format_reflection_input(
        self,
        goal: str,
        action_history: List[Dict[str, Any]]
    ) -> str:
        """
        格式化反思输入
        
        Args:
            goal: 任务目标
            action_history: 操作历史列表
        
        Returns:
            str: 格式化的用户输入
        """
        lines = [
            f"【任务目标】",
            goal,
            "",
            f"【操作历史】（共 {len(action_history)} 步）",
        ]
        
        # 格式化操作历史
        for i, action in enumerate(action_history, 1):
            action_type = action.get("action", "unknown")
            thought = action.get("thought", "")
            
            # 简化显示
            if action_type == "system_warning":
                # 死循环警告，标记为废动作
                lines.append(f"{i}. [废动作] system_warning: 死循环熔断")
            else:
                # 正常动作
                target = action.get("target", {})
                input_data = action.get("input", {})
                
                # 提取关键信息
                element_id = target.get("element_id", "")
                text = input_data.get("text", "")
                url = input_data.get("url", "")
                
                # 构造动作描述
                action_desc = f"{action_type}"
                if element_id:
                    action_desc += f" [element_id={element_id}]"
                if text:
                    action_desc += f" text='{text[:30]}...'" if len(text) > 30 else f" text='{text}'"
                if url:
                    action_desc += f" url='{url}'"
                
                lines.append(f"{i}. {action_desc}")
                if thought:
                    lines.append(f"   思考: {thought[:100]}..." if len(thought) > 100 else f"   思考: {thought}")
        
        lines.extend([
            "",
            "【任务要求】",
            "请提炼出达成目标的核心主线逻辑，输出为精简的通用步骤 SOP。",
            "记住：绝对禁止保留具体的 element_id，必须转为语义描述。",
        ])
        
        return "\n".join(lines)
    
    def _extract_sop_from_result(self, result: Dict[str, Any]) -> str:
        """
        从 LLM 返回结果中提取 SOP 文本
        
        Args:
            result: LLM 返回的结果字典
        
        Returns:
            str: 提取的 SOP 文本
        """
        # 尝试从 thought 字段提取
        if isinstance(result, dict):
            sop_text = result.get("thought", "")
            if sop_text and isinstance(sop_text, str):
                return sop_text.strip()
        
        # 如果 result 本身是字符串
        if isinstance(result, str):
            return result.strip()
        
        # 降级处理：返回 JSON 字符串
        logger.warning("无法从 LLM 结果中提取 SOP，使用 JSON 字符串")
        return json.dumps(result, ensure_ascii=False)
    
    async def _refine_sop(
        self,
        raw_sop: str,
        goal: str,
        llm_client
    ) -> str:
        """
        对原始 SOP 进行二次精简，去除试错步骤，保留最短可复现路径
        
        Args:
            raw_sop: 原始 SOP 文本（可能包含试错步骤）
            goal: 任务目标
            llm_client: LLMClient 实例，用于调用 LLM 进行精简
        
        Returns:
            str: 精简后的 SOP 文本。如果精简失败，返回原始 raw_sop
        """
        logger.info("开始二次精简 SOP，去除试错步骤...")
        
        # 构建精简提示词
        refine_prompt = f"""你是一个流程优化专家。以下是一个 Web Agent 完成任务的操作流程（SOP），其中可能包含试错步骤、重复操作和冗余动作。

任务目标：{goal}

原始 SOP：
{raw_sop}

请提炼出完成该任务的最短可复现路径，要求：
1. 去除明显的试错步骤（连续失败后才成功的操作序列，只保留最终成功的那步）
2. 去除重复操作（同样的动作重复了多次，只保留一次）
3. 保留所有必要步骤，不能因为"精简"而遗漏关键操作
4. 输出格式与原始 SOP 保持一致

只输出精简后的 SOP，不要解释。"""
        
        try:
            # 调用 LLM 进行精简（纯文本模式）
            result = await llm_client.chat(
                system_prompt="你是一个流程优化专家，擅长提炼最短可复现路径。",
                user_input=refine_prompt,
                temperature=0.3,  # 较低温度，保持精确性
                max_tokens=1000,
                image_path=None,
                valid_element_ids=None,
            )
            
            # 提取精简后的 SOP
            refined_sop = self._extract_sop_from_result(result)
            
            # 验证精简结果
            if not refined_sop or len(refined_sop.strip()) < 10:
                logger.warning("精简后的 SOP 过短或为空，使用原始 SOP")
                return raw_sop
            
            logger.info(f"✓ SOP 二次精简完成，长度: {len(raw_sop)} → {len(refined_sop)} 字符")
            logger.debug(f"精简后的 SOP:\n{refined_sop}")
            
            return refined_sop
            
        except Exception as e:
            # 精简失败时静默降级，返回原始 SOP
            logger.warning(f"SOP 二次精简失败: {e}，使用原始 SOP")
            return raw_sop
    
    async def save_new_skill(
        self,
        goal: str,
        sop_text: str,
        llm_client=None
    ) -> Dict[str, Any]:
        """
        保存新技能到本地技能库（支持 SOP 二次精简）
        
        Args:
            goal: 任务目标（作为 intent_description）
            sop_text: 提炼后的通用 SOP 文本（作为 guidance_sop）
            llm_client: LLMClient 实例（可选），用于 SOP 二次精简
        
        Returns:
            Dict[str, Any]: 新创建的技能字典
        """
        logger.info(f"保存新技能: {goal[:50]}...")
        
        # 【SOP 二次精简】如果提供了 llm_client，则进行精简
        refined_sop = sop_text
        if llm_client is not None:
            refined_sop = await self._refine_sop(sop_text, goal, llm_client)
        else:
            logger.debug("未提供 llm_client，跳过 SOP 二次精简")
        
        # 按照 CONTRACT.md 规范组装数据
        new_skill = {
            "skill_id": uuid.uuid4().hex,  # 全局唯一 ID
            "intent_description": goal,
            "guidance_sop": refined_sop,  # 使用精简后的 SOP
            "sop_raw": sop_text,  # 保留原始 SOP 作为备份
            "created_at": datetime.utcnow().isoformat() + "Z",  # ISO 8601 格式
            "success_count": 0,
        }
        
        # 追加到技能列表
        self.skills.append(new_skill)
        
        # 持久化到文件
        self._save_skills(self.skills)
        
        logger.info(f"✓ 新技能已保存，skill_id: {new_skill['skill_id']}")
        logger.debug(f"技能详情: {json.dumps(new_skill, ensure_ascii=False, indent=2)}")
        
        return new_skill
    
    def get_all_skills(self) -> List[Dict[str, Any]]:
        """
        获取所有技能
        
        Returns:
            List[Dict[str, Any]]: 技能列表
        """
        return self.skills.copy()
    
    def get_skill_by_id(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """
        根据 skill_id 获取技能
        
        Args:
            skill_id: 技能 ID
        
        Returns:
            Optional[Dict[str, Any]]: 技能字典，如果不存在则返回 None
        """
        for skill in self.skills:
            if skill.get("skill_id") == skill_id:
                return skill.copy()
        return None
    
    def increment_success_count(self, skill_id: str) -> bool:
        """
        增加技能的成功复用次数
        
        Args:
            skill_id: 技能 ID
        
        Returns:
            bool: 是否成功更新
        """
        for skill in self.skills:
            if skill.get("skill_id") == skill_id:
                skill["success_count"] = skill.get("success_count", 0) + 1
                self._save_skills(self.skills)
                logger.info(f"✓ 技能 {skill_id} 成功次数 +1，当前: {skill['success_count']}")
                return True
        
        logger.warning(f"技能 {skill_id} 不存在，无法更新成功次数")
        return False
    
    def search_skills_by_intent(
        self,
        query: str,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        基于意图检索技能（简单版本：关键词匹配）
        
        未来可以扩展为：
        - 使用向量数据库进行语义检索
        - 使用 LLM 进行意图匹配
        
        Args:
            query: 查询意图
            top_k: 返回前 k 个最相关的技能
        
        Returns:
            List[Dict[str, Any]]: 匹配的技能列表
        """
        logger.info(f"检索技能: {query[:50]}...")
        
        # 简单的关键词匹配
        query_lower = query.lower()
        matched_skills = []
        
        for skill in self.skills:
            intent = skill.get("intent_description", "").lower()
            sop = skill.get("guidance_sop", "").lower()
            
            # 计算匹配分数（简单的关键词重叠）
            score = 0
            for word in query_lower.split():
                if len(word) > 2:  # 忽略短词
                    if word in intent:
                        score += 2  # intent 匹配权重更高
                    if word in sop:
                        score += 1
            
            if score > 0:
                matched_skills.append((score, skill))
        
        # 按分数排序
        matched_skills.sort(key=lambda x: x[0], reverse=True)
        
        # 返回前 k 个
        result = [skill for _, skill in matched_skills[:top_k]]
        
        logger.info(f"✓ 检索到 {len(result)} 个相关技能")
        return result
    
    def save_failure_pattern(
        self,
        goal: str,
        failure_summary: str,
        suggestion: str
    ) -> Dict[str, Any]:
        """
        保存失败模式到本地失败模式库
        
        Args:
            goal: 任务目标（作为失败模式的上下文）
            failure_summary: 失败特征和根本原因的描述
            suggestion: 规避建议
        
        Returns:
            Dict[str, Any]: 新创建的失败模式字典
        
        Raises:
            IOError: 文件写入失败时抛出
        """
        logger.info(f"保存新失败模式: {goal[:50]}...")
        
        # 组装失败模式数据
        new_pattern = {
            "pattern_id": str(uuid.uuid4()),  # UUID 格式
            "goal": goal,
            "failure_summary": failure_summary,
            "suggestion": suggestion,
            "type": "failure_pattern",
            "created_at": datetime.utcnow().isoformat() + "Z",  # ISO 8601 格式（UTC）
        }
        
        # 追加到失败模式列表
        self.failure_patterns.append(new_pattern)
        
        # 持久化到文件
        self._save_failure_patterns(self.failure_patterns)
        
        logger.info(f"✓ 新失败模式已保存，pattern_id: {new_pattern['pattern_id']}")
        logger.debug(f"失败模式详情: {json.dumps(new_pattern, ensure_ascii=False, indent=2)}")
        
        return new_pattern
    
    def search_failure_patterns(
        self,
        goal: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        基于任务目标检索相关的失败模式
        
        Args:
            goal: 任务目标
            top_k: 返回前 k 个最相关的失败模式（默认 5）
        
        Returns:
            List[Dict[str, Any]]: 匹配的失败模式列表，每个字典包含：
                - failure_summary: 失败特征描述
                - suggestion: 规避建议
                - goal: 原始任务目标（可选，用于上下文）
        
        Notes:
            - 当失败模式数量 < 50 时，返回所有失败模式
            - 当失败模式数量 >= 50 时，需要改为向量检索（TODO）
        """
        logger.info(f"检索失败模式: {goal[:50]}...")
        
        try:
            # TODO: 当失败模式数量超过 50 条时，改为向量检索
            # - 使用 Embedding 模型将 goal 和 failure_summary 转换为向量
            # - 使用向量数据库（如 FAISS、Chroma）进行相似度检索
            # - 返回 top_k 个最相关的失败模式
            
            # 当前阶段：数量 < 50 时，返回所有失败模式
            if len(self.failure_patterns) < 50:
                # 只返回必要字段
                result = [
                    {
                        "failure_summary": pattern.get("failure_summary", ""),
                        "suggestion": pattern.get("suggestion", ""),
                        "goal": pattern.get("goal", ""),
                    }
                    for pattern in self.failure_patterns
                ]
                logger.info(f"✓ 检索到 {len(result)} 个失败模式（全部返回）")
                return result
            else:
                # 未来扩展：向量检索
                logger.warning(f"失败模式数量 ({len(self.failure_patterns)}) >= 50，需要实现向量检索")
                # 暂时返回前 top_k 个
                result = [
                    {
                        "failure_summary": pattern.get("failure_summary", ""),
                        "suggestion": pattern.get("suggestion", ""),
                        "goal": pattern.get("goal", ""),
                    }
                    for pattern in self.failure_patterns[:top_k]
                ]
                logger.info(f"✓ 检索到 {len(result)} 个失败模式（简单截取）")
                return result
                
        except Exception as e:
            logger.error(f"检索失败模式失败: {e}")
            return []
    
    def _format_failure_reflection_input(
        self,
        goal: str,
        action_history: List[Dict[str, Any]]
    ) -> str:
        """
        格式化失败反思输入
        
        Args:
            goal: 任务目标
            action_history: 操作历史列表
        
        Returns:
            str: 格式化的用户输入
        """
        lines = [
            f"【任务目标】",
            goal,
            "",
            f"【操作历史】（共 {len(action_history)} 步）",
        ]
        
        # 格式化操作历史（只显示关键信息）
        for i, entry in enumerate(action_history, 1):
            # 兼容新旧格式
            if "decision" in entry:
                decision = entry["decision"]
                result = entry.get("result", {})
                action_type = decision.get("action", "unknown")
                success = result.get("success", False)
                tag = entry.get("tag", "")
                
                status = "✓" if success else "✗"
                tag_icon = {"MILESTONE": "🏁", "ERROR": "❌", "NORMAL": "▪️"}.get(tag, "")
                lines.append(f"{i}. {tag_icon} {action_type} {status}")
            else:
                action_type = entry.get("action", "unknown")
                lines.append(f"{i}. {action_type}")
        
        lines.extend([
            "",
            "【任务要求】",
            "请分析失败的根本原因，并提供规避建议。",
        ])
        
        return "\n".join(lines)
    
    def _extract_failure_reflection_from_result(self, result: Dict[str, Any]) -> Dict[str, str]:
        """
        从 LLM 返回结果中提取失败反思（failure_summary 和 suggestion）
        
        Args:
            result: LLM 返回的结果字典
        
        Returns:
            Dict[str, str]: 包含 failure_summary 和 suggestion 的字典
        
        Raises:
            LLMError: 无法提取有效结果时抛出
        """
        # 尝试从 thought 字段提取
        if isinstance(result, dict):
            thought = result.get("thought", "")
            if thought and isinstance(thought, str):
                # 尝试解析 JSON
                try:
                    reflection = json.loads(thought)
                    if isinstance(reflection, dict) and "failure_summary" in reflection and "suggestion" in reflection:
                        return {
                            "failure_summary": reflection["failure_summary"],
                            "suggestion": reflection["suggestion"]
                        }
                except json.JSONDecodeError:
                    pass
            
            # 尝试直接从 result 提取
            if "failure_summary" in result and "suggestion" in result:
                return {
                    "failure_summary": result["failure_summary"],
                    "suggestion": result["suggestion"]
                }
        
        # 如果 result 本身是字符串，尝试解析 JSON
        if isinstance(result, str):
            try:
                reflection = json.loads(result)
                if isinstance(reflection, dict) and "failure_summary" in reflection and "suggestion" in reflection:
                    return {
                        "failure_summary": reflection["failure_summary"],
                        "suggestion": reflection["suggestion"]
                    }
            except json.JSONDecodeError:
                pass
        
        # 降级处理：无法提取有效结果
        logger.error(f"无法从 LLM 结果中提取失败反思: {result}")
        raise LLMError("LLM 返回格式错误，无法提取 failure_summary 和 suggestion")
    
    async def reflect_failure(
        self,
        goal: str,
        action_history: List[Dict[str, Any]],
        llm_client
    ) -> Dict[str, str]:
        """
        反思提炼：将失败任务的操作历史总结为失败原因和规避建议
        
        Args:
            goal: 任务目标
            action_history: 操作历史列表
            llm_client: LLMClient 实例，用于调用 LLM 进行反思
        
        Returns:
            Dict[str, str]: 包含两个字段：
                - failure_summary: 失败特征和根本原因
                - suggestion: 规避建议
        
        Raises:
            LLMError: LLM 调用失败时抛出
        """
        logger.info("开始反思提炼失败原因...")
        
        # 构造用户输入
        user_input = self._format_failure_reflection_input(goal, action_history)
        
        try:
            # 调用 LLM 进行反思（纯文本模式，不需要图像）
            result = await llm_client.chat(
                system_prompt=self.FAILURE_REFLECTION_SYSTEM_PROMPT,
                user_input=user_input,
                temperature=0.7,  # 适度的创造性
                max_tokens=1000,  # 足够生成失败反思
                image_path=None,  # 反思不需要图像
                valid_element_ids=None,  # 反思不需要 ID 验证
            )
            
            # 提取失败反思
            reflection = self._extract_failure_reflection_from_result(result)
            
            logger.info(f"✓ 失败反思提炼完成")
            logger.debug(f"失败特征: {reflection['failure_summary'][:100]}...")
            logger.debug(f"规避建议: {reflection['suggestion'][:100]}...")
            
            return reflection
            
        except LLMError as e:
            logger.error(f"失败反思提炼失败（LLM 错误）: {e}")
            raise
        except Exception as e:
            logger.error(f"失败反思提炼失败（未知错误）: {e}")
            raise LLMError(f"失败反思提炼失败: {e}")
