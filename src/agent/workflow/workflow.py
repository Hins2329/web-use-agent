"""
工作流引擎模块

实现 ReAct 循环核心逻辑，驱动智能体完成任务。
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import json
import asyncio
from pathlib import Path
from datetime import datetime

from ...config.settings import get_config
from ...utils.logger import setup_logger
from ...utils.exceptions import BrowserError, PerceptionError, LLMError
from ..execution.controller import BrowserController
from ..execution.actions import ActionExecutor, Action
from ..perception.engine import PerceptionEngine
from ..llm.llm_client import LLMClient
from prompts.system_prompt import SYSTEM_PROMPT_TEMPLATE as EXTRACTED_SYSTEM_PROMPT_TEMPLATE
from .loop_monitor import LoopMonitor
from ..memory.task_state import TaskState, SubGoal
from ..memory.context_manager import ContextManager


logger = setup_logger("agent")


@dataclass
class TaskResult:
    """
    任务执行结果
    """
    success: bool
    final_thought: str
    steps_taken: int
    actions_executed: List[Dict[str, Any]]
    final_page_state: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class AgentWorkflow:
    """
    Agent 工作流引擎

    实现 ReAct（Reasoning + Acting）循环：
    1. 获取当前页面状态
    2. 调用 LLM 进行推理
    3. 执行 LLM 推荐的动作
    4. 循环直到完成或超过步数限制
    """

    SYSTEM_PROMPT_TEMPLATE = EXTRACTED_SYSTEM_PROMPT_TEMPLATE
    
    # 【动作类型分类】用于检测执行环境切换
    LOCAL_ACTIONS = {"read_file", "write_file", "create_file"}
    BROWSER_ACTIONS = {"click", "type", "navigate", "scroll", "wait", "upload_file", "select_option", "human_intervene", "done"}

    def __init__(self):
        self.config = get_config()
        self.browser: Optional[BrowserController] = None
        self.executor: Optional[ActionExecutor] = None
        self.perception_engine = PerceptionEngine()
        self.llm_client = LLMClient()
        self.action_history: List[Dict[str, Any]] = []
        self.step_count = 0
        self._last_url = None  # 用于检测URL改变，决定是否清空持久化ID映射
        self._prev_action_type: Optional[str] = None  # 用于检测执行环境切换
        
        # 【新增】实例化死循环监控器
        self.loop_monitor = LoopMonitor()
        logger.debug("✓ LoopMonitor 已初始化")
        
        # 【新增】实例化本地工具执行器
        from ..tools.local_executor import LocalToolExecutor
        self.tool_executor = LocalToolExecutor()
        logger.debug("✓ LocalToolExecutor 已初始化")
        
        # 【懒感知机制】脏标记和状态缓存
        self._browser_needs_update: bool = True  # 脏标记：是否需要更新浏览器状态
        self._last_page_state: Optional[Dict[str, Any]] = None  # 缓存的页面状态
        self._last_element_ids: Optional[set] = None  # 上一轮的元素ID集合（用于Diff模式）
        self._last_added_count: int = 0  # 上一轮新增的元素数量（用于动态追加子目标）
        logger.debug("✓ 懒感知机制已初始化（脏标记=True）")
        
        # 【上下文数据】持久化的数据（如文件内容），避免在 action_history 中重复
        self.context_data: Dict[str, Any] = {}
        logger.debug("✓ 上下文数据存储已初始化")
        
        # 【任务状态机】维护任务执行状态
        self.task_state: Optional[TaskState] = None
        logger.debug("✓ 任务状态机已初始化")
        
        # 【上下文压缩】上下文压缩管理器
        self.context_manager = ContextManager(threshold_ratio=0.8, model_max_tokens=128000)
        logger.debug("✓ 上下文压缩管理器已初始化")
        
        # 【技能管理器】实例化技能管理器
        from ..memory.skill_manager import SkillManager
        self.skill_manager = SkillManager()
        logger.debug("✓ SkillManager 已初始化")

    async def _initialize_task_state(self, goal: str) -> TaskState:
        """
        初始化任务状态，调用 LLM 生成初始子目标列表
        
        该方法会单独调用一次 LLM，让它基于用户目标生成结构化的子目标列表。
        
        Args:
            goal: 用户原始目标
            
        Returns:
            TaskState: 初始化后的任务状态对象
        """
        logger.info("初始化任务状态，生成子目标列表...")
        
        # 构建专门用于生成子目标的 prompt
        system_prompt = """你是一个任务规划专家。给定一个用户目标，你需要将其分解为 3-5 个可执行的子目标。

【返回格式】
你必须返回纯 JSON 格式，不要有任何其他文字或 Markdown 代码块：

{
    "sub_goals": [
        {"description": "子目标1描述", "status": "pending"},
        {"description": "子目标2描述", "status": "pending"},
        {"description": "子目标3描述", "status": "pending"}
    ]
}

【规则】
1. 每个子目标应该是具体、可执行的步骤
2. 子目标之间应该有逻辑顺序
3. 所有子目标的初始状态都是 "pending"
4. 子目标数量控制在 3-5 个
5. 直接输出 JSON，不要用 ```json``` 包裹

【示例】
用户目标：在淘宝上搜索并购买一本Python书籍
正确输出：
{"sub_goals": [{"description": "打开淘宝首页", "status": "pending"}, {"description": "在搜索框输入'Python书籍'", "status": "pending"}, {"description": "浏览搜索结果并选择合适的商品", "status": "pending"}, {"description": "加入购物车并完成支付", "status": "pending"}]}
"""
        
        user_input = f"请为以下目标生成子目标列表：{goal}"
        
        try:
            # 调用 LLM 生成子目标（纯文本模式，不需要图像）
            response = await self.llm_client.chat(
                system_prompt=system_prompt,
                user_input=user_input,
                temperature=0.7,
                max_tokens=1000,
                image_path=None,  # 不需要图像
                valid_element_ids=None  # 不需要 ID 验证
            )
            
            # 解析响应
            if isinstance(response, str):
                response = json.loads(response)
            
            sub_goals_data = response.get("sub_goals", [])
            sub_goals = [SubGoal.from_dict(sg) for sg in sub_goals_data]
            
            logger.info(f"✓ 成功生成 {len(sub_goals)} 个子目标")
            for i, sg in enumerate(sub_goals, 1):
                logger.debug(f"  {i}. {sg.description}")
            
            # 创建 TaskState 对象
            task_state = TaskState(
                task_id="task_1",  # 当前单任务固定为 task_1
                goal=goal,
                sub_goals=sub_goals,
                milestones=[],
                blockers=[],
                step_count=0
            )
            
            return task_state
            
        except Exception as e:
            logger.warning(f"生成子目标失败: {e}，使用默认子目标")
            # 降级处理：创建一个默认的子目标
            default_sub_goal = SubGoal(
                description=f"完成目标：{goal}",
                status="pending"
            )
            return TaskState(
                task_id="task_1",
                goal=goal,
                sub_goals=[default_sub_goal],
                milestones=[],
                blockers=[],
                step_count=0
            )

    def _write_replay_log(self, action_record: Dict[str, Any]) -> None:
        """
        将动作记录写入回放日志文件
        
        日志格式：logs/replay_{task_id}.jsonl
        每行一个 JSON 对象，追加写入
        
        Args:
            action_record: action_history 中的一条记录，包含 decision/result/tag 字段
        """
        try:
            # 确保 task_state 已初始化
            if not self.task_state:
                logger.warning("task_state 未初始化，跳过回放日志写入")
                return
            
            # 构建日志目录路径
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            
            # 构建日志文件路径
            task_id = self.task_state.task_id
            log_file = log_dir / f"replay_{task_id}.jsonl"
            
            # 提取决策信息
            decision = action_record.get("decision", {})
            result = action_record.get("result", {})
            tag = action_record.get("tag", "NORMAL")
            
            # 获取当前 URL
            current_url = ""
            if self.browser and self.browser._page:
                try:
                    current_url = self.browser._page.url
                except Exception:
                    current_url = "unknown"
            
            # 构建日志记录
            log_entry = {
                "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "step": self.step_count,
                "action": decision.get("action", "unknown"),
                "target": decision.get("target", {}),
                "input": decision.get("input", {}),
                "result_success": result.get("success", False),
                "result_message": result.get("message", ""),
                "tag": tag,
                "url": current_url,
                "task_state_snapshot": self.task_state.to_dict()
            }
            
            # 追加写入日志文件（单行 JSON）
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
            logger.debug(f"✓ 回放日志已写入: {log_file}")
            
        except Exception as e:
            # 写入失败时只记录警告，不影响主流程
            logger.warning(f"写入回放日志失败: {e}")

    async def run_task(self, goal: str, start_url: Optional[str] = None, task_guidance: str = "") -> TaskResult:
        """
        执行任务。

        Args:
            goal: 任务目标
            start_url: 初始页面 URL（可选）
            task_guidance: 任务执行指南（可选，用于动态注入业务 SOP）

        Returns:
            TaskResult: 任务执行结果

        Raises:
            BrowserError: 浏览器错误时抛出
        """
        self.action_history = []
        self.step_count = 0
        final_thought = ""

        try:
            # 【任务状态机】初始化任务状态
            logger.info("初始化任务状态机...")
            self.task_state = await self._initialize_task_state(goal)
            logger.info(f"✓ 任务状态机初始化完成")
            logger.debug(f"任务状态:\n{self.task_state.serialize_for_prompt()}")
            
            # 【失败模式检索】检索历史失败模式
            logger.info("检索历史失败模式...")
            failure_patterns = self.skill_manager.search_failure_patterns(goal, top_k=5)
            if failure_patterns:
                failure_guidance = self._format_failure_patterns(failure_patterns)
                task_guidance += f"\n\n{failure_guidance}"
                logger.info(f"✓ 检索到 {len(failure_patterns)} 个相关失败模式")
            else:
                logger.info("✓ 未检索到相关失败模式")
            
            # 连接浏览器
            logger.info(f"初始化浏览器和工作流...")
            self.browser = BrowserController()
            await self.browser.connect()
            self.executor = ActionExecutor(self.browser)
            logger.info("✓ 浏览器连接成功")

            # 导航到起始页面
            if start_url:
                logger.info(f"导航到起始页面: {start_url}")
                await self.browser.navigate(start_url)
                
                # 检测淘宝登录页面并暂停
                try:
                    current_url = self.browser._page.url if self.browser._page else ""
                    if "login.taobao.com" in current_url:
                        pause_duration = self.config.agent.login_pause_duration
                        logger.info(f"检测到淘宝登录页面，暂停 {pause_duration} 秒")
                        logger.info("请手动扫码登录，Agent 将继续执行...")
                        await asyncio.sleep(pause_duration)
                except Exception as e:
                    logger.warning(f"检测登录页面时出错: {e}")

            # ReAct 循环
            logger.info(f"开始 ReAct 循环，目标: {goal}")
            while self.step_count < self.config.agent.max_steps:
                logger.info(f"\n--- Step {self.step_count + 1} ---")
                self.step_count += 1
                
                # 【任务状态机】更新步数
                if self.task_state:
                    self.task_state.increment_step()

                # 【懒感知】仅在需要更新时清空元素注册表
                if self._browser_needs_update:
                    logger.debug("清空上一轮的元素ID映射...")
                    if self.browser and hasattr(self.browser, 'element_registry'):
                        self.browser.element_registry.clear()
                        logger.debug("✓ 元素ID映射已清空（保留持久化映射）")
                else:
                    logger.debug("⚡ 跳过元素ID映射清空（复用缓存）")

                # 1. 感知当前页面状态（内部会检查脏标记）
                logger.debug("获取页面状态...")
                page_state = await self._get_page_state()

                # 【动态追加子目标】检查是否需要续写子目标
                # 在感知完成后、推理之前调用，使用上一轮的新增元素数量
                await self._try_append_sub_goals(self._last_added_count)

                # 2. 调用 LLM 进行推理
                logger.debug("调用 LLM 进行推理...")
                decision = await self._reasoning(goal, page_state, task_guidance)
                final_thought = decision["thought"]
                logger.info(f"Agent 思考: {final_thought}")
                
                # 【任务状态机】处理 state_update 字段
                # 同时记录是否完成了子目标（用于后续的 MILESTONE 标签判断）
                completed_sub_goal = False
                if self.task_state and "state_update" in decision:
                    state_update = decision.get("state_update")
                    if state_update:
                        logger.debug(f"检测到 state_update: {state_update}")
                        # 检查是否完成了子目标
                        if state_update.get("complete_sub_goal") is not None:
                            completed_sub_goal = True
                        self.task_state.update_from_llm_response(state_update)
                        logger.info("✓ 任务状态已更新")
                        logger.debug(f"更新后的任务状态:\n{self.task_state.serialize_for_prompt()}")
                
                # 【新增】死循环检测与熔断
                loop_warning = self.loop_monitor.check_and_add(decision)
                if loop_warning:
                    # 触发熔断：记录警告日志
                    logger.warning("🔥 死循环熔断触发！")
                    logger.warning(loop_warning)
                    
                    # 【新增】强制兜底策略：切换到 human_intervene
                    fallback_action = self._get_fallback_action(decision)
                    
                    if fallback_action:
                        logger.info(f"🛡️  执行兜底策略: {fallback_action['action']}")
                        
                        # 执行兜底动作
                        action = Action(
                            action=fallback_action["action"],
                            target=fallback_action.get("target", {}),
                            input=fallback_action.get("input", {}),
                            options=fallback_action.get("options", {})
                        )
                        
                        result = await self.executor.execute_action(action)
                        logger.info(f"兜底动作结果: {result.message}")
                        
                        # 记录兜底动作到历史（带 tag）
                        # 兜底动作通常是 ERROR 标签
                        fallback_record = {
                            "decision": fallback_action,
                            "result": {
                                "success": result.success,
                                "message": f"[兜底策略] {result.message}",
                                "data": result.data
                            },
                            "tag": "ERROR"  # 兜底动作标记为 ERROR
                        }
                        self.action_history.append(fallback_record)
                        
                        # 【回放日志】写入日志
                        self._write_replay_log(fallback_record)
                        
                        # 强制更新脏标记
                        self._browser_needs_update = True
                        
                        # 继续下一轮循环
                        continue
                    else:
                        # 无法兜底，构造警告决策
                        warning_decision = {
                            "action": "system_warning",
                            "thought": "系统强制熔断：检测到死循环模式",
                            "target": {},
                            "input": {"warning": loop_warning},
                            "options": {},
                            "tag": "ERROR"  # 系统警告标记为 ERROR
                        }
                        self.action_history.append(warning_decision)
                        
                        # 【回放日志】写入日志
                        self._write_replay_log(warning_decision)
                        
                        # 强制中断本轮执行，直接进入下一轮循环让 LLM 看到警告
                        logger.info("⏭️  跳过本轮动作执行，将警告传递给 LLM")
                        continue
                
                # 3. 执行动作
                action_type = decision["action"]
                logger.info(f"执行动作: {action_type}")

                # 检查是否完成
                if action_type == "done":
                    logger.info("✓ 任务完成")
                    # done 动作标记为 MILESTONE
                    decision["tag"] = "MILESTONE"
                    done_record = {
                        "decision": decision,
                        "result": {
                            "success": True,
                            "message": "任务完成",
                            "data": {}
                        },
                        "tag": "MILESTONE"
                    }
                    self.action_history.append(done_record)
                    
                    # 【回放日志】写入日志
                    self._write_replay_log(done_record)
                    
                    # 【环境切换追踪】任务完成，重置追踪状态
                    self._prev_action_type = None
                    
                    # 【SOP 保存】任务成功后反思提炼并保存技能
                    try:
                        logger.info("开始反思提炼新技能...")
                        raw_sop = await self.skill_manager.reflect_and_extract(
                            goal=goal,
                            action_history=list(self.action_history),
                            llm_client=self.llm_client
                        )
                        await self.skill_manager.save_new_skill(
                            goal=goal,
                            sop_text=raw_sop,
                            llm_client=self.llm_client  # 启用二次精简
                        )
                        logger.info("✓ 新技能已保存")
                    except Exception as e:
                        logger.warning(f"⚠️ SOP保存失败（不影响任务结果）: {e}")
                    
                    return TaskResult(
                        success=True,
                        final_thought=final_thought,
                        steps_taken=self.step_count,
                        actions_executed=self.action_history,
                        final_page_state=page_state,
                    )

                # 执行动作
                try:
                    action = Action(
                        action=action_type,
                        target=decision["target"],
                        input=decision["input"],
                        options=decision["options"],
                    )
                    
                    # 【Action Router】根据动作类型路由到不同的执行器
                    if action_type == "read_file":
                        logger.debug("路由到 LocalToolExecutor...")
                        result = await self.tool_executor.execute_tool(action)
                        
                        # 【懒感知】本地工具调用后更新脏标记
                        if result.success:
                            self._browser_needs_update = False
                            logger.debug("✓ 脏标记=False（本地工具调用成功，浏览器状态未改变）")
                            
                            # 【上下文数据】存储文件内容到 context_data
                            file_path = action.input.get("file_path", "unknown") if action.input else "unknown"
                            if "read_file_results" not in self.context_data:
                                self.context_data["read_file_results"] = {}
                            self.context_data["read_file_results"][file_path] = {
                                "content": result.data.get("content"),
                                "read_at_step": self.step_count
                            }
                            logger.debug(f"✓ 文件内容已存储到 context_data: {file_path}")
                        else:
                            self._browser_needs_update = True
                            logger.debug("✓ 脏标记=True（本地工具调用失败，强制重新感知）")
                    else:
                        # 浏览器动作：click, type, navigate, scroll, wait, upload_file, select_option, human_intervene
                        logger.debug("路由到 BrowserActionExecutor...")
                        result = await self.executor.execute_action(action)
                        
                        # 【懒感知】浏览器动作后强制更新脏标记
                        self._browser_needs_update = True
                        logger.debug("✓ 脏标记=True（浏览器动作执行，页面可能已改变）")
                    
                    logger.info(f"动作结果: {result.message}")
                    
                    # 【里程碑标签】判断 tag 类型（严格互斥优先级：ERROR > MILESTONE > NORMAL）
                    tag = "NORMAL"  # 默认为 NORMAL
                    
                    # 检查 URL 是否变化
                    url_changed = False
                    if self.browser and self.browser._page:
                        current_url = self.browser._page.url
                        if self._last_url is not None and current_url != self._last_url:
                            url_changed = True
                    
                    # 检查执行环境是否切换（本地工具 ↔ 浏览器工具）
                    env_switched = False
                    if self._prev_action_type is not None:
                        prev_is_local = self._prev_action_type in self.LOCAL_ACTIONS
                        curr_is_local = action_type in self.LOCAL_ACTIONS
                        prev_is_browser = self._prev_action_type in self.BROWSER_ACTIONS
                        curr_is_browser = action_type in self.BROWSER_ACTIONS
                        
                        # 从本地工具切换到浏览器工具，或反之
                        if (prev_is_local and curr_is_browser) or (prev_is_browser and curr_is_local):
                            env_switched = True
                    
                    # 严格互斥优先级判断
                    if not result.success:
                        # 优先级 1: 执行失败 → ERROR
                        tag = "ERROR"
                    elif completed_sub_goal or url_changed or env_switched:
                        # 优先级 2: 完成子目标 或 URL 变化 或 执行环境切换 → MILESTONE
                        tag = "MILESTONE"
                        if url_changed:
                            logger.debug(f"✓ 检测到 URL 变化，标记为 MILESTONE: {self._last_url} → {current_url}")
                        if completed_sub_goal:
                            logger.debug("✓ 完成了子目标，标记为 MILESTONE")
                        if env_switched:
                            logger.debug(f"✓ 检测到执行环境切换，标记为 MILESTONE: {self._prev_action_type} → {action_type}")
                    else:
                        # 优先级 3: 其余情况 → NORMAL
                        tag = "NORMAL"
                    
                    # 【数据流闭环】记录决策和执行结果到历史（带 tag）
                    action_record = {
                        "decision": decision,
                        "result": {
                            "success": result.success,
                            "message": result.message,
                            "data": result.data  # 包含执行结果数据（如文件内容）
                        },
                        "tag": tag  # 新增 tag 字段
                    }
                    self.action_history.append(action_record)
                    
                    # 【回放日志】写入日志
                    self._write_replay_log(action_record)
                    
                    # 【环境切换追踪】更新上一步动作类型
                    self._prev_action_type = action_type
                    
                    # 【关键】升级页面等待逻辑：尝试 domcontentloaded + sleep
                    # 这给动态渲染留出时间，确保下一轮 perception 能获取到最新的页面状态
                    if action_type == "human_intervene":
                        # 人工干预情况需要更长的等待时间，让用户完成操作
                        logger.info("⚠️  人工干预动作执行，等待页面稳定（3秒）...")
                        try:
                            await self.browser._page.wait_for_load_state("domcontentloaded", timeout=5000)
                            logger.debug("✓ 页面 domcontentloaded 完成")
                        except Exception as e:
                            logger.debug(f"等待 domcontentloaded 超时或异常，继续: {e}")
                        await asyncio.sleep(3)
                    else:
                        # 普通动作：先等待 domcontentloaded，再 sleep 2 秒
                        logger.debug("等待页面稳定（domcontentloaded + 2秒）...")
                        try:
                            await self.browser._page.wait_for_load_state("domcontentloaded", timeout=5000)
                            logger.debug("✓ 页面 domcontentloaded 完成")
                        except Exception as e:
                            logger.debug(f"等待 domcontentloaded 超时或异常，继续: {e}")
                        await asyncio.sleep(2)
                    
                    # 清空感知缓存，强制下一轮采集最新页面状态
                    if hasattr(self.perception_engine, 'clear_cache'):
                        self.perception_engine.clear_cache()
                        logger.debug("✓ 感知缓存已清空")

                except Exception as exc:
                    logger.error(f"动作执行失败: {exc}")
                    
                    # 【数据流闭环】异常情况下也记录到历史（新格式，带 tag）
                    error_record = {
                        "decision": decision,
                        "result": {
                            "success": False,
                            "message": f"执行失败: {str(exc)}",
                            "data": {}
                        },
                        "tag": "ERROR"  # 异常标记为 ERROR
                    }
                    self.action_history.append(error_record)
                    
                    # 【回放日志】写入日志
                    self._write_replay_log(error_record)
                    
                    # 【懒感知】异常时强制更新脏标记
                    self._browser_needs_update = True
                    logger.debug("✓ 脏标记=True（动作执行异常，强制重新感知）")
                    
                    # 即使动作执行失败，也要进行适当的等待和清理
                    logger.debug("动作失败后的页面等待（1秒）...")
                    await asyncio.sleep(1)
                    if hasattr(self.perception_engine, 'clear_cache'):
                        self.perception_engine.clear_cache()

            # 超过步数限制
            logger.warning(
                f"超过最大步数限制 ({self.config.agent.max_steps})"
            )
            
            # 【环境切换追踪】任务超时，重置追踪状态
            self._prev_action_type = None
            
            # 【失败模式保存】提炼并保存失败模式（超时）
            try:
                logger.info("提炼失败原因（超时）...")
                reflection = await self.skill_manager.reflect_failure(
                    goal=goal,
                    action_history=self.action_history,
                    llm_client=self.llm_client
                )
                self.skill_manager.save_failure_pattern(
                    goal=goal,
                    failure_summary=reflection["failure_summary"],
                    suggestion=reflection["suggestion"]
                )
                logger.info("✓ 失败模式已保存")
            except Exception as e:
                logger.warning(f"保存失败模式时出错: {e}")
            
            return TaskResult(
                success=False,
                final_thought=final_thought,
                steps_taken=self.step_count,
                actions_executed=self.action_history,
                error_message="超过最大步数限制",
            )

        except Exception as exc:
            logger.error(f"工作流执行失败: {exc}")
            
            # 【环境切换追踪】任务异常，重置追踪状态
            self._prev_action_type = None
            
            # 【失败模式保存】提炼并保存失败模式
            try:
                logger.info("提炼失败原因...")
                reflection = await self.skill_manager.reflect_failure(
                    goal=goal,
                    action_history=self.action_history,
                    llm_client=self.llm_client
                )
                self.skill_manager.save_failure_pattern(
                    goal=goal,
                    failure_summary=reflection["failure_summary"],
                    suggestion=reflection["suggestion"]
                )
                logger.info("✓ 失败模式已保存")
            except Exception as e:
                logger.warning(f"保存失败模式时出错: {e}")
            
            return TaskResult(
                success=False,
                final_thought=final_thought,
                steps_taken=self.step_count,
                actions_executed=self.action_history,
                error_message=str(exc),
            )
        finally:
            # 清理资源
            if self.browser:
                await self.browser.disconnect()
                logger.info("✓ 浏览器已断开连接")

    async def _get_page_state(self) -> Dict[str, Any]:
        """
        获取当前页面状态（支持懒感知）。

        Returns:
            Dict[str, Any]: 页面状态信息（感知层原始输出）

        Raises:
            PerceptionError: 感知失败时抛出
        """
        if not self.browser:
            raise PerceptionError("浏览器未连接")

        try:
            # 【懒感知】检测URL变化，如果页面改变则强制更新
            current_url = self.browser._page.url if self.browser._page else ""
            if self._last_url is not None and current_url != self._last_url:
                logger.info(f"🔄 检测到页面导航: {self._last_url} → {current_url}")
                self._browser_needs_update = True
                logger.debug("✓ 脏标记=True（页面导航）")
                # 完全清空所有映射（包括持久化的）
                if hasattr(self.browser, 'element_registry'):
                    self.browser.element_registry.clear_persistent()
                    logger.info(f"✓ 清空元素ID映射以适应新页面")
                
                # 清空死循环监控器的滑动窗口
                self.loop_monitor.clear()
                logger.debug("✓ 死循环监控器已重置（页面导航）")
                
                # 【截图哈希缓存】清空截图缓存
                self.perception_engine._last_screenshot_hash = None
                self.perception_engine._last_screenshot_b64 = None
                logger.debug("✓ 截图哈希缓存已清空（页面导航）")
            
            self._last_url = current_url
            
            # 【懒感知】检查脏标记：如果不需要更新且有缓存，则复用缓存
            if not self._browser_needs_update and self._last_page_state is not None:
                logger.info("⚡ 网页状态未改变，触发懒感知，复用上一轮页面状态...")
                return self._last_page_state
            
            # 【原有逻辑】执行完整感知
            logger.debug("🔍 执行完整浏览器感知...")
            
            # 先截取最新的页面截图
            logger.debug("截取最新页面截图...")
            await self.browser.screenshot()
            
            # 直接将 browser 对象作为 page_handler 传给感知引擎
            # browser 对象提供了所有必要方法：get_page_content()、url、screenshot_path等
            result = await self.perception_engine.understand(self.browser, "")
            
            # 【懒感知】更新缓存
            self._last_page_state = result
            logger.debug("✓ 页面状态已缓存")

            return result

        except Exception as exc:
            logger.error(f"页面状态获取失败: {exc}")
            # 【懒感知】异常时强制更新脏标记
            self._browser_needs_update = True
            logger.debug("✓ 脏标记=True（感知异常）")
            raise PerceptionError(f"页面状态获取失败: {exc}")

    async def _try_append_sub_goals(self, new_element_count: int) -> None:
        """
        检查是否需要动态追加子目标
        
        触发条件（两个同时满足）：
        1. 所有现有子目标都已 completed（没有 pending 或 blocked 的）
        2. 元素 diff 新增元素数量 > 15（说明出现了大量新内容）
        
        Args:
            new_element_count: 本次 diff 的新增元素数量
        """
        if not self.task_state:
            return
        
        # 检查是否所有子目标都完成了
        pending = [sg for sg in self.task_state.sub_goals if sg.status in ("pending", "blocked")]
        if pending:
            return  # 还有未完成的，不追加
        
        if new_element_count <= 15:
            return  # 页面变化不够大，不追加
        
        logger.info(f"检测到所有子目标已完成且页面新增 {new_element_count} 个元素，尝试动态追加子目标...")
        
        # 触发 LLM 续写子目标
        existing = [sg.description for sg in self.task_state.sub_goals]
        prompt = f"""任务目标：{self.task_state.goal}

已完成的子目标：
{chr(10).join(f'- {d}' for d in existing)}

页面出现了大量新内容，请续写接下来最多3个子目标。

要求：
1. 不重复已完成的内容
2. 每个子目标一行，只写描述，不加序号
3. 如果任务已经完成，输出"无需追加"

只输出子目标列表或"无需追加"，不要解释。"""
        
        try:
            response = await self.llm_client.chat(
                system_prompt="你是任务规划助手。",
                user_input=prompt,
                temperature=0.7,
                max_tokens=500,
                image_path=None,
                valid_element_ids=None,
                context_manager=None  # 避免递归压缩
            )
            
            # 提取响应文本
            if isinstance(response, dict):
                response_text = response.get("thought", "")
            else:
                response_text = str(response)
            
            if "无需追加" in response_text:
                logger.info("✓ LLM 判断无需追加子目标")
                return
            
            # 解析子目标列表
            lines = [l.strip() for l in response_text.strip().split("\n") 
                    if l.strip() and l.strip() != "无需追加"]
            
            added = 0
            for line in lines[:3]:  # 最多取3个
                # 清理可能的序号前缀
                line = line.lstrip("0123456789.-) ")
                if not line:
                    continue
                
                success = self.task_state.add_sub_goal(line)
                if success:
                    added += 1
                    logger.info(f"✓ 动态追加子目标: {line}")
                else:
                    logger.warning(f"⚠️ 子目标已达上限，停止追加")
                    break
            
            if added > 0:
                logger.info(f"✓ 共追加 {added} 个子目标，当前总数: {len(self.task_state.sub_goals)}")
            else:
                logger.info("✓ 未追加任何子目标")
                
        except Exception as e:
            logger.warning(f"⚠️ 动态追加子目标失败（忽略）: {e}")

    async def _reasoning(self, goal: str, page_state: Dict[str, Any], task_guidance: str = "") -> Dict[str, Any]:
        """
        调用 LLM 进行推理（支持多模态 + ID 幻觉拦截 + 动态任务指导）。

        该方法从页面状态中提取：
        1. valid_element_ids：当前页面所有可交互元素的 ID 列表
        2. image_path：SoM 标注截图的路径
        
        然后将这些信息传入 LLMClient，启用 ID 幻觉拦截机制。
        如果提供了 task_guidance，则动态注入到系统提示词中。

        Args:
            goal: 任务目标
            page_state: 当前页面状态（感知层输出）
            task_guidance: 任务执行指南（可选，用于动态注入业务 SOP）

        Returns:
            Dict[str, Any]: 推理结果 {"thought": ..., "action": ...}

        Raises:
            LLMError: 推理失败或重试超限时抛出
        """
        # ========== Step 1: 提取合法 ID 列表 ==========
        valid_element_ids = self._extract_valid_element_ids(page_state)
        logger.debug(f"提取到有效 element_id 列表: {valid_element_ids}")

        # ========== Step 2: 获取截图路径 ==========
        image_path = self._get_screenshot_path(page_state)
        if image_path:
            logger.debug(f"使用 SoM 标注截图: {image_path}")
        else:
            logger.debug("未找到 SoM 标注截图路径，将进行纯文本推理")

        # ========== Step 3: 构建页面状态摘要 ==========
        page_schema_str = self._format_page_state_to_text(page_state)

        # ========== Step 4: 构建操作历史 ==========
        action_history_str = self._format_action_history()

        # ========== Step 5: 构建上下文数据 ==========
        context_data_str = self._format_context_data()

        # ========== Step 6: 构建系统提示词 ==========
        system_prompt = self.SYSTEM_PROMPT_TEMPLATE.format(
            page_schema=page_schema_str,
            action_history=action_history_str,
            goal=goal,
        )
        
        # 【任务状态机】注入 TaskState 到系统提示词
        if self.task_state:
            task_state_str = self.task_state.serialize_for_prompt()
            system_prompt += f"\n\n{task_state_str}"
            logger.debug("✓ 已注入任务状态到系统提示词")
        
        # 【动态注入】如果提供了 task_guidance，则追加到系统提示词
        if task_guidance:
            system_prompt += f"\n\n【任务执行指南】\n{task_guidance}"
            logger.debug("✓ 已动态注入任务执行指南")
        
        # 【上下文数据注入】如果有上下文数据，追加到系统提示词
        if context_data_str:
            system_prompt += f"\n\n{context_data_str}"
            logger.debug("✓ 已注入上下文数据（文件内容等）")

        # ========== Step 7: 调用 LLM（多模态 + ID 拦截 + 上下文压缩） ==========
        user_input = f"请根据以上信息，决定下一步动作来完成目标：{goal}"
        
        try:
            decision = await self.llm_client.chat(
                system_prompt=system_prompt,
                user_input=user_input,
                image_path=image_path,
                valid_element_ids=valid_element_ids,
                context_manager=self.context_manager,
                task_state=self.task_state,
                action_history=self.action_history,
            )
            logger.debug(f"LLM 推理成功，返回动作: {decision.get('action')}")
            return decision
        except LLMError as e:
            # LLMError 已经在 llm_client 内部实现了重试，此处直接抛出
            logger.error(f"LLM 推理失败（经过重试）: {str(e)}")
            raise

    def _format_page_state_to_text(self, page_state: Dict[str, Any]) -> str:
        """
        将 page_state 转换为极简文本格式，支持元素Diff模式。
        
        **Diff模式优化**：
        - 当 _browser_needs_update=False 时，计算元素变化
        - 只输出新增和消失的元素，而不是全量元素列表
        - 进一步减少Token消耗
        
        **Token 优化策略：**
        1. 只保留 element_id、type 和关键文本
        2. 文本长度限制为 30 字符
        3. 空文本的元素使用更简洁的格式
        4. 如果元素过多（>50），只显示前 50 个

        Args:
            page_state: 页面状态字典

        Returns:
            str: 极简文本格式的页面状态（全量或Diff模式）
        """
        try:
            # 提取 URL 和标题
            page_schema = page_state.get("page_schema", {})
            url = page_schema.get("url", "未知")
            title = page_schema.get("title", "未知")

            # 提取元素列表
            elements = page_state.get("elements", [])
            if not elements:
                # 尝试从 page_schema 中获取
                if isinstance(page_schema, dict):
                    elements = page_schema.get("elements", [])

            # 提取当前元素ID集合和元素字典
            current_element_ids = set()
            element_dict = {}  # element_id -> element
            
            if elements and isinstance(elements, list):
                for elem in elements:
                    if isinstance(elem, dict):
                        element_id = elem.get("element_id")
                        if element_id is not None and isinstance(element_id, (int, float)):
                            eid = int(element_id)
                            current_element_ids.add(eid)
                            element_dict[eid] = elem
            
            # 【Diff模式判断】：脏标记为False且有上次缓存
            use_diff_mode = (not self._browser_needs_update and 
                            self._last_element_ids is not None)
            
            if use_diff_mode:
                # ========== Diff模式 ==========
                # 计算新增和消失的元素
                added_ids = current_element_ids - self._last_element_ids
                removed_ids = self._last_element_ids - current_element_ids
                
                # 【保存新增元素数量】用于动态追加子目标判断
                self._last_added_count = len(added_ids)
                
                # 如果没有任何变化
                if not added_ids and not removed_ids:
                    # 更新元素ID缓存
                    self._last_element_ids = current_element_ids
                    return (
                        f"URL: {url}\n"
                        f"Title: {title}\n"
                        f"\n"
                        f"[页面状态未变化，请基于上次感知继续决策]"
                    )
                
                # 有变化时输出diff
                lines = [
                    f"URL: {url}",
                    f"Title: {title}",
                    "",
                    "[页面无导航，元素变化如下]",
                    ""
                ]
                
                # 输出新增元素
                if added_ids:
                    lines.append(f"新增元素 ({len(added_ids)} 个):")
                    for eid in sorted(added_ids):
                        elem = element_dict.get(eid)
                        if elem:
                            lines.append(self._format_element(elem))
                    lines.append("")
                
                # 输出消失元素
                if removed_ids:
                    lines.append(f"消失元素 ({len(removed_ids)} 个):")
                    for eid in sorted(removed_ids):
                        lines.append(f"[{eid}]")
                    lines.append("")
                
                lines.append("其余元素不变")
                
                # 更新元素ID缓存
                self._last_element_ids = current_element_ids
                
                return "\n".join(lines)
            
            else:
                # ========== 全量模式 ==========
                # 全量模式下，重置新增计数
                self._last_added_count = 0
                
                lines = [
                    f"URL: {url}",
                    f"Title: {title}",
                    "",
                    "Interactive Elements:",
                ]
                
                # 【Token 优化】如果元素过多，只显示前 50 个
                display_elements = elements
                if len(elements) > 50:
                    display_elements = elements[:50]
                    lines.append(f"（显示前 50 个元素，共 {len(elements)} 个）")
                    lines.append("")
                
                # 格式化元素列表
                if display_elements and isinstance(display_elements, list):
                    for elem in display_elements:
                        if isinstance(elem, dict):
                            lines.append(self._format_element(elem))
                else:
                    lines.append("(无可交互元素)")
                
                # 更新元素ID缓存
                self._last_element_ids = current_element_ids
                
                return "\n".join(lines)

        except Exception as e:
            logger.warning(f"格式化 page_state 时出错: {str(e)}")
            # 降级处理：返回基本信息
            return f"页面状态格式化失败: {str(e)}"

    def _format_element(self, elem: Dict[str, Any]) -> str:
        """
        格式化单个元素为文本行
        
        Args:
            elem: 元素字典
            
        Returns:
            str: 格式化后的元素文本
        """
        element_id = elem.get("element_id", "?")
        elem_type = elem.get("type", "unknown")
        
        # 文本提取优先级：text > title > placeholder > 空字符串
        raw_text = elem.get("text") or elem.get("title") or elem.get("placeholder") or ""
        safe_text = str(raw_text) if raw_text is not None else ""
        
        # 文本清洗：去除换行符和多余空格
        if safe_text:
            safe_text = " ".join(safe_text.split())
            # 截断长文本为 30 字符
            if len(safe_text) > 30:
                safe_text = safe_text[:30] + "..."
            return f"[{element_id}] {elem_type}: \"{safe_text}\""
        else:
            return f"[{element_id}] {elem_type}"

    def _extract_valid_element_ids(self, page_state: Dict[str, Any]) -> Optional[List[int]]:
        """
        从页面状态中提取所有有效的 element_id。

        按照数据契约，elements 应该存放在 page_state 中。
        如果 page_state 中有 page_schema 字段，则从中提取。

        Args:
            page_state: 页面状态字典

        Returns:
            Optional[List[int]]: 有效的 element_id 列表，如果无法提取则返回 None
        """
        try:
            # 尝试从 page_state 直接获取 elements
            elements = page_state.get("elements", [])
            
            # 如果没有，尝试从 page_schema 中获取
            if not elements:
                page_schema = page_state.get("page_schema", {})
                if isinstance(page_schema, dict):
                    elements = page_schema.get("elements", [])
            
            # 提取所有有效的 element_id
            valid_ids = []
            if elements and isinstance(elements, list):
                for elem in elements:
                    if isinstance(elem, dict):
                        element_id = elem.get("element_id")
                        # 只收集整数类型的 ID
                        if element_id is not None and isinstance(element_id, (int, float)):
                            valid_ids.append(int(element_id))
            
            if valid_ids:
                logger.debug(f"✓ 成功提取 {len(valid_ids)} 个有效 element_id")
                return valid_ids
            else:
                logger.warning("⚠️  未找到任何有效的 element_id，将进行无限制推理")
                return None

        except Exception as e:
            logger.warning(f"提取 element_id 时出错: {str(e)}")
            return None

    def _get_screenshot_path(self, page_state: Dict[str, Any]) -> Optional[str]:
        """
        获取 SoM 标注截图的路径。

        按照数据契约，截图路径通常存放在 vlm_hints 字段中。
        如果感知层没有返回，则从 browser 的 screenshot_path 获取。

        Args:
            page_state: 页面状态字典

        Returns:
            Optional[str]: 截图文件的本地路径，如果未找到则返回 None
        """
        try:
            # ========== 优先级 1: 从 page_state 的 vlm_hints 中获取 ==========
            vlm_hints = page_state.get("vlm_hints")
            if isinstance(vlm_hints, dict):
                screenshot_path = vlm_hints.get("screenshot_path")
                if screenshot_path and isinstance(screenshot_path, str):
                    logger.debug(f"从 vlm_hints 中获取截图路径: {screenshot_path}")
                    return screenshot_path
            
            # ========== 优先级 2: 从 browser 的 screenshot_path 获取 ==========
            if self.browser and hasattr(self.browser, "screenshot_path"):
                screenshot_path = self.browser.screenshot_path
                if screenshot_path and isinstance(screenshot_path, str):
                    logger.debug(f"从 browser.screenshot_path 中获取截图路径: {screenshot_path}")
                    return screenshot_path
            
            logger.debug("未找到有效的截图路径")
            return None

        except Exception as e:
            logger.warning(f"获取截图路径时出错: {str(e)}")
            return None

    def _format_action_history(self) -> str:
        """
        格式化操作历史为字符串（简洁版，不包含大数据）
        
        该方法兼容新旧两种 action_history 格式：
        - 新格式: {"decision": {...}, "result": {...}, "tag": "MILESTONE/NORMAL/ERROR"}
        - 旧格式: {"action": "...", "target": {...}, ...}
        
        对于新格式，显示动作类型、执行状态和简短消息。
        大数据（如文件内容）存储在 context_data 中，不在此处显示。
        
        **Token 优化（里程碑标签系统）**：
        - MILESTONE 标签：永不丢弃（URL 变化、子目标完成）
        - ERROR 标签：只保留最近 3 条
        - NORMAL 标签：只保留最近 5 条
        - 按原始顺序合并去重
        
        Returns:
            str: 格式化后的操作历史字符串
        """
        if not self.action_history:
            return "（无操作历史）"

        # 【里程碑标签系统】按 tag 分类筛选
        all_history = list(self.action_history)
        milestones = [h for h in all_history if h.get("tag") == "MILESTONE"]
        errors = [h for h in all_history if h.get("tag") == "ERROR"][-3:]  # 只保留最近 3 条错误
        normals = [h for h in all_history if h.get("tag") == "NORMAL"][-5:]  # 只保留最近 5 条普通动作
        
        # 合并去重，按原始顺序排列
        seen = set()
        recent_history = []
        for h in all_history:
            hid = id(h)
            if h in milestones + errors + normals and hid not in seen:
                seen.add(hid)
                recent_history.append(h)
        
        lines = []
        
        # 如果历史被压缩，添加提示
        total_count = len(all_history)
        shown_count = len(recent_history)
        if shown_count < total_count:
            omitted = total_count - shown_count
            lines.append(f"（已省略 {omitted} 步普通操作，保留所有里程碑和最近错误）")
            lines.append("")
        
        # 格式化每条历史记录
        for i, entry in enumerate(recent_history, start=1):
            # 获取 tag（如果有）
            tag = entry.get("tag", "")
            tag_icon = {
                "MILESTONE": "🏁",
                "ERROR": "❌",
                "NORMAL": "▪️"
            }.get(tag, "")
            
            # 兼容新旧格式
            if "decision" in entry:
                # 新格式: {"decision": {...}, "result": {...}, "tag": "..."}
                decision = entry["decision"]
                result = entry.get("result", {})
                action_type = decision.get("action", "unknown")
                success = result.get("success", False)
                message = result.get("message", "")
                
                # 格式化状态
                status = "✓ 成功" if success else "✗ 失败"
                lines.append(f"{tag_icon} {i}. {action_type} → {status}")
                
                # 显示简短消息（不包含大数据）
                if message:
                    # 截断过长的消息
                    short_message = message[:100] + "..." if len(message) > 100 else message
                    lines.append(f"   {short_message}")
            else:
                # 旧格式兼容: {"action": "...", "target": {...}, ...}
                action_type = entry.get("action", "unknown")
                lines.append(f"{tag_icon} {i}. {action_type}")

        return "\n".join(lines)

    def _format_context_data(self) -> str:
        """
        格式化上下文数据为字符串（包含完整的大数据）
        
        该方法将 context_data 中存储的持久化数据格式化为字符串，
        用于注入到 LLM 的 system_prompt 中。
        
        当前支持的数据类型：
        - read_file_results: 已读取的文件内容（完整无损）
        
        Returns:
            str: 格式化后的上下文数据字符串，如果没有数据则返回空字符串
        """
        if not self.context_data:
            return ""
        
        lines = ["【上下文数据】"]
        
        # 格式化 read_file 结果
        if "read_file_results" in self.context_data:
            lines.append("\n已读取的文件内容：")
            for file_path, data in self.context_data["read_file_results"].items():
                content = data.get("content")
                step = data.get("read_at_step")
                lines.append(f"\n文件: {file_path} (读取于 Step {step})")
                
                # 根据内容类型格式化
                if isinstance(content, dict):
                    # JSON 对象：格式化输出
                    lines.append(json.dumps(content, ensure_ascii=False, indent=2))
                elif isinstance(content, str):
                    # 纯文本：直接输出
                    lines.append(content)
                else:
                    # 其他类型：转换为字符串
                    lines.append(str(content))
        
        return "\n".join(lines)

    def _get_fallback_action(self, failed_decision: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        根据失败的决策生成兜底动作
        
        当检测到死循环时，根据失败的动作类型生成相应的兜底策略。
        默认兜底策略是切换到 human_intervene，让用户接管控制权。
        
        Args:
            failed_decision: 触发死循环的决策
        
        Returns:
            Optional[Dict[str, Any]]: 兜底动作，如果无法兜底则返回 None
        """
        action_type = failed_decision.get("action", "")
        
        # 兜底策略表：所有死循环都切换到 human_intervene
        fallback_strategies = {
            "scroll": {
                "action": "human_intervene",
                "thought": "检测到重复滚动死循环，切换到人工介入模式",
                "target": {"area": "页面滚动区域"},
                "input": {"reason": "检测到重复滚动，可能目标元素不存在或需要人工定位"},
                "options": {}
            },
            "click": {
                "action": "human_intervene",
                "thought": "检测到重复点击死循环，切换到人工介入模式",
                "target": {"area": "点击目标元素"},
                "input": {"reason": "检测到重复点击失败，可能元素不可点击或需要人工介入"},
                "options": {}
            },
            "type": {
                "action": "human_intervene",
                "thought": "检测到重复输入死循环，切换到人工介入模式",
                "target": {"area": "输入框"},
                "input": {"reason": "检测到重复输入失败，可能输入框不可用或需要人工介入"},
                "options": {}
            },
            "wait": {
                "action": "human_intervene",
                "thought": "检测到重复等待死循环，切换到人工介入模式",
                "target": {"area": "等待区域"},
                "input": {"reason": "检测到重复等待，可能页面加载异常或需要人工介入"},
                "options": {}
            },
            "read_file": {
                "action": "human_intervene",
                "thought": "检测到重复读取文件死循环，切换到人工介入模式",
                "target": {"area": "文件系统"},
                "input": {"reason": "检测到重复读取文件，可能文件路径错误或需要人工介入"},
                "options": {}
            }
        }
        
        # 如果有特定的兜底策略，返回；否则返回通用的 human_intervene
        if action_type in fallback_strategies:
            return fallback_strategies[action_type]
        else:
            # 通用兜底策略
            return {
                "action": "human_intervene",
                "thought": f"检测到 {action_type} 动作死循环，切换到人工介入模式",
                "target": {"area": "当前操作区域"},
                "input": {"reason": f"检测到重复执行 {action_type} 动作，需要人工介入"},
                "options": {}
            }
    
    def _format_failure_patterns(self, failure_patterns: List[Dict[str, Any]]) -> str:
        """
        格式化失败模式为字符串，用于注入到 task_guidance
        
        Args:
            failure_patterns: 失败模式列表
        
        Returns:
            str: 格式化后的字符串，如果列表为空则返回空字符串
        """
        if not failure_patterns:
            return ""
        
        lines = [
            "【历史失败模式】",
            "以下是类似任务的失败经验，请注意规避：",
            ""
        ]
        
        for i, pattern in enumerate(failure_patterns, 1):
            failure_summary = pattern.get("failure_summary", "")
            suggestion = pattern.get("suggestion", "")
            
            lines.append(f"{i}. 失败特征：{failure_summary}")
            lines.append(f"   规避建议：{suggestion}")
            lines.append("")
        
        return "\n".join(lines)
