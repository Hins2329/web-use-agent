"""
动作执行器模块

提供高级的页面操作接口，基于 BrowserController 实现智能化的元素操作。
包含自动等待逻辑，确保操作的稳定性和可靠性。
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

from .controller import BrowserController
from ...utils.exceptions import BrowserError

logger = logging.getLogger(__name__)


@dataclass
class Action:
    """
    动作数据结构

    定义智能体执行的标准化动作格式。
    """
    action: str  # "click", "type", "scroll", "navigate", "wait", "done", "upload_file", "select_option"
    target: Dict[str, Any]  # 目标元素信息
    input: Dict[str, Any] = None  # 输入数据
    options: Dict[str, Any] = None  # 额外选项


@dataclass
class ActionResult:
    """
    动作执行结果

    包含执行状态和相关信息。
    """
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class ActionExecutor:
    """
    高级操作执行器

    基于 BrowserController 提供智能化的页面操作接口。
    所有操作都包含自动等待逻辑，确保元素就绪后再执行。
    """

    def __init__(self, browser_controller: BrowserController):
        """
        初始化动作执行器

        Args:
            browser_controller: 已连接的浏览器控制器实例
        """
        self.browser = browser_controller

    async def execute_action(self, action: Action) -> ActionResult:
        """
        执行标准化动作

        Args:
            action: 要执行的动作对象

        Returns:
            ActionResult: 执行结果

        Raises:
            BrowserError: 执行失败时抛出
        """
        try:
            # 【防护检查】确保 action 对象的完整性
            if not hasattr(action, 'action'):
                raise BrowserError("Action 对象缺少 'action' 属性")
            
            # 【强制解包逻辑】处理 action 可能是字典或字符串的情况
            action_type = action.action
            
            # 如果 action.action 是字典，尝试从中提取 "action" 字段
            if isinstance(action_type, dict):
                logger.warning(f"⚠️  检测到 action.action 是字典，正在解包: {action_type}")
                # 从字典中提取 "action" 字段
                action_type = action_type.get("action", "")
                if not action_type:
                    raise BrowserError(f"action 字典中缺少 'action' 字段: {action_type}")
                logger.info(f"✓ 解包成功: action_type = {repr(action_type)}")
            
            # 确保 action_type 是字符串
            if not isinstance(action_type, str):
                # 最后的救援：尝试用 parser 标准化
                try:
                    from src.agent.utils.parser import parse_llm_response
                    import json
                    normalized = parse_llm_response(json.dumps({"action": action_type}))
                    action_type = normalized.get("action", "wait")
                    logger.info(f"✓ Parser 救援成功: action_type = {repr(action_type)}")
                except Exception as e:
                    logger.error(f"Parser 救援失败: {e}")
                    raise BrowserError(f"无法确定动作类型: {action_type}")
            
            # 转换为小写
            action_type = action_type.lower()
            
            # 【日志】记录最终的动作类型
            logger.debug(f"✓ 最终动作类型: {action_type}")
            logger.debug(f"✓ 动作详情 - target: {action.target}, input: {action.input}")

            if action_type == "click":
                success = await self.smart_click(action.target.get("element_id", ""))
                message = "点击操作成功" if success else "点击操作失败"

            elif action_type == "type":
                text = action.input.get("text", "") if action.input else ""
                success = await self.smart_type(action.target.get("element_id", ""), text)
                message = "输入操作成功" if success else "输入操作失败"

            elif action_type == "navigate":
                url = action.input.get("url", "") if action.input else ""
                await self.browser.navigate(url)
                success = True
                message = f"导航成功: {url}"

            elif action_type == "scroll":
                success = await self.scroll_into_view(action.target.get("element_id", ""))
                message = "滚动操作成功" if success else "滚动操作失败"

            elif action_type == "wait":
                timeout = action.options.get("timeout", 10000) if action.options else 10000
                success = await self.browser.wait_for_element(
                    action.target.get("element_id", "") if action.target else "",
                    timeout=timeout
                )
                message = "等待操作成功" if success else "等待操作失败"

            elif action_type == "upload_file":
                file_path = action.input.get("file_path", "") if action.input else ""
                result = await self.smart_upload(action.target.get("element_id", ""), file_path)
                success = result.success
                message = result.message

            elif action_type == "select_option":
                option_value = action.input.get("value", "") if action.input else ""
                success = await self.select_option(action.target.get("element_id", ""), option_value)
                message = "选项选择成功" if success else "选项选择失败"

            elif action_type == "human_intervene":
                # 人工干预动作：在终端显示提示，等待用户完成操作后回车
                success = await self.human_intervene(action)
                message = "人工干预完成" if success else "人工干预被中止"

            elif action_type == "done":
                success = True
                message = "任务完成"

            else:
                # Enhanced error message with full action object inspection
                action_inspect = {
                    "action_type": action_type,
                    "action_type_python_type": type(action_type).__name__,
                    "action_object": {
                        "action": action.action,
                        "action_type": type(action.action).__name__ if action.action else None,
                        "target": action.target if action.target else {},
                        "input": action.input if action.input else {},
                        "options": action.options if action.options else {}
                    }
                }
                logger.error(f"ACTION INSPECTION:\n{json.dumps(action_inspect, ensure_ascii=False, indent=2)}")
                
                # List supported actions for debugging
                supported = ["click", "type", "scroll", "wait", "screenshot", "extract_page_info", 
                           "human_intervene", "upload_file", "done"]
                logger.error(f"Supported actions: {supported}")
                
                raise BrowserError(f"不支持的动作类型: {action_type}\n详见日志中的ACTION INSPECTION")

            return ActionResult(
                success=success,
                message=message,
                data={"action": action_type}
            )

        except Exception as e:
            # 【契约保证】所有情况下都返回 ActionResult，不抛出异常
            error_msg = f"动作执行失败: {action.action} - {str(e)}"
            logger.error(error_msg)
            return ActionResult(
                success=False,
                message=error_msg,
                data={"action": getattr(action, 'action', 'unknown'), "error": str(e)}
            )

    async def smart_click(self, element_id: str) -> bool:
        """
        智能点击元素 - 支持坐标兜底策略

        执行梯队：
        1. 首选策略：使用 Playwright 标准选择器进行点击
        2. 兜底策略：如果选择器失效（TimeoutError），降级使用物理坐标点击
        3. 异常处理：如果两个策略都失败，返回 False
        
        核心逻辑：
        - 从 ElementRegistry 获取 selector 和坐标 (center_x, center_y)
        - 先尝试 selector 路由（设置较短超时时间）
        - 如果失败且有坐标，使用 page.mouse.click(center_x, center_y)
        - 如果仍失败或无坐标，最终返回 False

        Args:
            element_id: 元素 ID（来自感知层，可以是 int 或 str）

        Returns:
            bool: 点击是否成功

        Raises:
            BrowserError: 致命错误时抛出
        """
        if element_id is None:
            raise BrowserError("元素 ID 不能为空")
        
        try:
            # ============ Step 1: 获取 selector 和坐标 ============
            selector = self.browser.element_registry.get_selector(element_id)
            coordinates = self.browser.element_registry.get_coordinates(element_id)
            center_x = coordinates.get("center_x") if coordinates else None
            center_y = coordinates.get("center_y") if coordinates else None
            
            if not selector:
                error_msg = (
                    f"元素 ID {element_id} 已过期或不在当前页面中，"
                    f"请重新调用感知引擎获取最新的页面信息"
                )
                logger.error(error_msg)
                raise BrowserError(error_msg)
            
            logger.debug(f"点击操作: element_id={element_id} → selector={selector}")
            if center_x is not None and center_y is not None:
                logger.debug(f"  备用坐标: center_x={center_x}, center_y={center_y}")

            # ============ Step 2: 首选策略 - Playwright Selector ============
            try:
                logger.debug(f"【首选策略】尝试使用 Playwright selector 点击...")
                
                # 等待元素可见且可点击（使用极短超时时间 - Fail Fast）
                await self.browser._page.wait_for_selector(
                    selector,
                    state="visible",
                    timeout=1000  # Fail Fast: 快速失败，进入坐标兜底
                )

                # 确保元素在视口中
                await self.browser._page.locator(selector).scroll_into_view_if_needed()

                # 执行点击
                await self.browser._page.locator(selector).click(timeout=3000)
                
                logger.info(f"✓ 【首选策略成功】点击元素 ID={element_id}")
                return True

            except Exception as selector_error:
                # 首选策略失败，尝试兜底策略
                logger.warning(
                    f"⚠️  【首选策略失败】选择器失效: {str(selector_error)[:100]}... "
                    f"- 准备降级使用物理坐标"
                )
                
                # ============ Step 3: 兜底策略 - 坐标点击（动态转换为视口相对坐标）============
                if center_x is not None and center_y is not None:
                    try:
                        logger.info(
                            f"【兜底策略】降级使用物理坐标点击（绝对坐标转视口相对）: "
                            f"绝对坐标=({center_x}, {center_y})"
                        )
                        
                        import asyncio
                        
                        # 【核心修复】动态获取当前页面的滚动偏移量
                        scroll_info = await self.browser._page.evaluate("""
                            () => ({
                                scroll_x: window.scrollX,
                                scroll_y: window.scrollY,
                                viewport_width: window.innerWidth,
                                viewport_height: window.innerHeight
                            })
                        """)
                        scroll_x = scroll_info['scroll_x']
                        scroll_y = scroll_info['scroll_y']
                        viewport_width = scroll_info['viewport_width']
                        viewport_height = scroll_info['viewport_height']
                        
                        # 【核心修复】计算视口相对坐标
                        viewport_x = center_x - scroll_x
                        viewport_y = center_y - scroll_y
                        
                        logger.debug(
                            f"  滚动偏移: scroll_x={scroll_x}, scroll_y={scroll_y}"
                        )
                        logger.debug(
                            f"  视口相对坐标: viewport_x={viewport_x}, viewport_y={viewport_y}"
                        )
                        
                        # 【核心修复】越界保护：检查元素是否在视口内
                        if (viewport_x < 0 or viewport_x > viewport_width or 
                            viewport_y < 0 or viewport_y > viewport_height):
                            logger.info(
                                f"  元素不在视口内，需要滚动到元素位置"
                            )
                            
                            # 滚动到元素位置（将元素置于视口中央）
                            await self.browser._page.evaluate(f"""
                                () => {{
                                    window.scrollTo({{
                                        left: {center_x} - window.innerWidth / 2,
                                        top: {center_y} - window.innerHeight / 2,
                                        behavior: 'instant'
                                    }});
                                }}
                            """)
                            
                            # 等待滚动完成
                            await asyncio.sleep(0.5)
                            
                            # 重新获取最新的滚动偏移量
                            scroll_info = await self.browser._page.evaluate("""
                                () => ({
                                    scroll_x: window.scrollX,
                                    scroll_y: window.scrollY
                                })
                            """)
                            scroll_x = scroll_info['scroll_x']
                            scroll_y = scroll_info['scroll_y']
                            
                            # 重新计算精确的视口相对坐标
                            viewport_x = center_x - scroll_x
                            viewport_y = center_y - scroll_y
                            
                            logger.debug(
                                f"  滚动后新坐标: viewport_x={viewport_x}, viewport_y={viewport_y}"
                            )
                        
                        # 拟人化点击序列：移动 → 悬停 → 按压
                        # 第一步：移动鼠标到目标位置（使用精准的视口相对坐标）
                        await self.browser._page.mouse.move(viewport_x, viewport_y)
                        # 第二步：极短的悬停缓冲（让浏览器感知鼠标）
                        await asyncio.sleep(0.2)
                        # 第三步：带 150ms 按压延迟的点击（模拟人类手速）
                        await self.browser._page.mouse.click(viewport_x, viewport_y, delay=150)
                        
                        logger.info(
                            f"✓ 【兜底策略成功】通过坐标点击元素 ID={element_id} "
                            f"视口坐标=({viewport_x}, {viewport_y})"
                        )
                        return True
                        
                    except Exception as coordinate_error:
                        error_msg = (
                            f"【兜底策略失败】坐标点击也失败: {str(coordinate_error)[:100]}..."
                        )
                        logger.error(error_msg)
                        return False
                else:
                    # 没有坐标可用
                    logger.warning(
                        f"⚠️  无可用的物理坐标进行兜底操作 "
                        f"(center_x={center_x}, center_y={center_y})"
                    )
                    return False

        except BrowserError:
            # 致命错误直接抛出
            raise
        except Exception as e:
            error_msg = f"点击操作遇到未预期的异常: {str(e)}"
            logger.error(error_msg)
            return False

    async def smart_type(self, element_id: str, text: str) -> bool:
        """
        智能输入文本 - 支持坐标兜底策略

        执行梯队：
        1. 首选策略：使用 Playwright 标准选择器进行输入
        2. 兜底策略：如果选择器失效（TimeoutError），降级使用物理坐标点击后输入
        3. 异常处理：如果两个策略都失败，返回 False
        
        核心逻辑：
        - 从 ElementRegistry 获取 selector 和坐标 (center_x, center_y)
        - 先尝试 selector 路由（设置较短超时时间）
        - 如果失败且有坐标，使用 page.mouse.click() 激活输入框，再用 page.keyboard.type()
        - 如果仍失败或无坐标，最终返回 False

        Args:
            element_id: 元素 ID（来自感知层，可以是 int 或 str）
            text: 要输入的文本内容

        Returns:
            bool: 输入是否成功

        Raises:
            BrowserError: 致命错误时抛出
        """
        if element_id is None:
            raise BrowserError("元素 ID 不能为空")
        
        if not text:
            raise BrowserError("输入文本不能为空")

        try:
            # ============ Step 1: 获取 selector 和坐标 ============
            selector = self.browser.element_registry.get_selector(element_id)
            coordinates = self.browser.element_registry.get_coordinates(element_id)
            center_x = coordinates.get("center_x") if coordinates else None
            center_y = coordinates.get("center_y") if coordinates else None
            
            if not selector:
                error_msg = (
                    f"元素 ID {element_id} 已过期或不在当前页面中，"
                    f"请重新调用感知引擎获取最新的页面信息"
                )
                logger.error(error_msg)
                raise BrowserError(error_msg)
            
            logger.debug(f"输入操作: element_id={element_id} → selector={selector}, text={text[:50]}")
            if center_x is not None and center_y is not None:
                logger.debug(f"  备用坐标: center_x={center_x}, center_y={center_y}")

            # ============ Step 2: 首选策略 - Playwright Selector ============
            try:
                logger.debug(f"【首选策略】尝试使用 Playwright selector 输入...")
                
                # 等待元素可见（使用极短超时时间 - Fail Fast）
                await self.browser._page.wait_for_selector(
                    selector,
                    state="visible",
                    timeout=1000  # Fail Fast: 快速失败，进入坐标兜底
                )

                # 确保元素在视口中
                await self.browser._page.locator(selector).scroll_into_view_if_needed()

                # 清空并输入文本
                locator = self.browser._page.locator(selector)
                await locator.clear(timeout=3000)
                await locator.fill(text, timeout=3000)

                logger.info(f"✓ 【首选策略成功】输入文本到元素 ID={element_id}")
                return True

            except Exception as selector_error:
                # 首选策略失败，尝试兜底策略
                logger.warning(
                    f"⚠️  【首选策略失败】选择器失效: {str(selector_error)[:100]}... "
                    f"- 准备降级使用物理坐标"
                )
                
                # ============ Step 3: 兜底策略 - 坐标输入（动态转换为视口相对坐标）============
                if center_x is not None and center_y is not None:
                    try:
                        logger.info(
                            f"【兜底策略】降级使用物理坐标输入（绝对坐标转视口相对）: "
                            f"绝对坐标=({center_x}, {center_y})"
                        )
                        
                        import asyncio
                        
                        # 【核心修复】动态获取当前页面的滚动偏移量
                        scroll_info = await self.browser._page.evaluate("""
                            () => ({
                                scroll_x: window.scrollX,
                                scroll_y: window.scrollY,
                                viewport_width: window.innerWidth,
                                viewport_height: window.innerHeight
                            })
                        """)
                        scroll_x = scroll_info['scroll_x']
                        scroll_y = scroll_info['scroll_y']
                        viewport_width = scroll_info['viewport_width']
                        viewport_height = scroll_info['viewport_height']
                        
                        # 【核心修复】计算视口相对坐标
                        viewport_x = center_x - scroll_x
                        viewport_y = center_y - scroll_y
                        
                        logger.debug(
                            f"  滚动偏移: scroll_x={scroll_x}, scroll_y={scroll_y}"
                        )
                        logger.debug(
                            f"  视口相对坐标: viewport_x={viewport_x}, viewport_y={viewport_y}"
                        )
                        
                        # 【核心修复】越界保护：检查元素是否在视口内
                        if (viewport_x < 0 or viewport_x > viewport_width or 
                            viewport_y < 0 or viewport_y > viewport_height):
                            logger.info(
                                f"  元素不在视口内，需要滚动到元素位置"
                            )
                            
                            # 滚动到元素位置（将元素置于视口中央）
                            await self.browser._page.evaluate(f"""
                                () => {{
                                    window.scrollTo({{
                                        left: {center_x} - window.innerWidth / 2,
                                        top: {center_y} - window.innerHeight / 2,
                                        behavior: 'instant'
                                    }});
                                }}
                            """)
                            
                            # 等待滚动完成
                            await asyncio.sleep(0.5)
                            
                            # 重新获取最新的滚动偏移量
                            scroll_info = await self.browser._page.evaluate("""
                                () => ({
                                    scroll_x: window.scrollX,
                                    scroll_y: window.scrollY
                                })
                            """)
                            scroll_x = scroll_info['scroll_x']
                            scroll_y = scroll_info['scroll_y']
                            
                            # 重新计算精确的视口相对坐标
                            viewport_x = center_x - scroll_x
                            viewport_y = center_y - scroll_y
                            
                            logger.debug(
                                f"  滚动后新坐标: viewport_x={viewport_x}, viewport_y={viewport_y}"
                            )
                        
                        # 第一步：拟人化点击激活焦点（移动 → 悬停 → 按压）
                        await self.browser._page.mouse.move(viewport_x, viewport_y)
                        await asyncio.sleep(0.2)
                        await self.browser._page.mouse.click(viewport_x, viewport_y, delay=150)
                        
                        # 第二步：等待输入框响应（充分的焦点激活时间）
                        await asyncio.sleep(0.5)
                        
                        # 第三步：模拟人类打字速度，使用 100ms 字符间延迟
                        await self.browser._page.keyboard.type(text, delay=100)
                        
                        logger.info(
                            f"✓ 【兜底策略成功】通过坐标输入文本到元素 ID={element_id} "
                            f"视口坐标=({viewport_x}, {viewport_y})"
                        )
                        return True
                        
                    except Exception as coordinate_error:
                        error_msg = (
                            f"【兜底策略失败】坐标输入也失败: {str(coordinate_error)[:100]}..."
                        )
                        logger.error(error_msg)
                        return False
                else:
                    # 没有坐标可用
                    logger.warning(
                        f"⚠️  无可用的物理坐标进行兜底操作 "
                        f"(center_x={center_x}, center_y={center_y})"
                    )
                    return False

        except BrowserError:
            # 致命错误直接抛出
            raise
        except Exception as e:
            error_msg = f"输入操作遇到未预期的异常: {str(e)}"
            logger.error(error_msg)
            return False

    async def smart_upload(self, element_id: str, file_path: str) -> ActionResult:
        """
        智能文件上传 - 仅支持 selector 策略（文件上传强依赖 DOM）

        执行梯队：
        1. 首选策略：使用 Playwright 标准选择器进行文件上传
        2. 兜底策略：文件上传无法使用物理坐标兜底（<input type="file"> 必须通过 DOM API）
        3. 异常处理：如果选择器失败，直接返回失败结果
        
        核心逻辑：
        - 验证本地文件是否存在
        - 从 ElementRegistry 获取 selector
        - 使用 Playwright 的 set_input_files() API 上传文件
        - 如果 selector 失效，无法兜底（文件上传强依赖原生 DOM 节点）

        Args:
            element_id: 元素 ID（来自感知层，可以是 int 或 str）
            file_path: 要上传的本地文件路径（绝对路径或相对路径）

        Returns:
            ActionResult: 包含上传结果的标准响应对象

        Raises:
            不抛出异常，所有错误都封装在 ActionResult 中
        """
        import os
        
        # ============ Step 0: 参数验证 ============
        if element_id is None:
            return ActionResult(
                success=False,
                message="元素 ID 不能为空",
                data={"error": "missing_element_id"}
            )
        
        if not file_path:
            return ActionResult(
                success=False,
                message="文件路径不能为空",
                data={"error": "missing_file_path"}
            )
        
        # ============ Step 1: 本地文件校验 ============
        if not os.path.exists(file_path):
            error_msg = f"文件不存在: {file_path}"
            logger.error(error_msg)
            return ActionResult(
                success=False,
                message=error_msg,
                data={"error": "file_not_found", "file_path": file_path}
            )
        
        if not os.path.isfile(file_path):
            error_msg = f"路径不是文件: {file_path}"
            logger.error(error_msg)
            return ActionResult(
                success=False,
                message=error_msg,
                data={"error": "not_a_file", "file_path": file_path}
            )
        
        logger.debug(f"文件校验通过: {file_path} (大小: {os.path.getsize(file_path)} 字节)")

        try:
            # ============ Step 2: 获取 selector（坐标对文件上传无效）============
            selector = self.browser.element_registry.get_selector(element_id)
            
            if not selector:
                error_msg = (
                    f"元素 ID {element_id} 已过期或不在当前页面中，"
                    f"请重新调用感知引擎获取最新的页面信息"
                )
                logger.error(error_msg)
                return ActionResult(
                    success=False,
                    message=error_msg,
                    data={"error": "element_not_found", "element_id": element_id}
                )
            
            logger.debug(f"上传操作: element_id={element_id} → selector={selector}, file={file_path}")

            # ============ Step 3: 首选策略 - Playwright Selector（唯一策略）============
            try:
                logger.debug(f"【首选策略】尝试使用 Playwright selector 上传文件...")
                
                # 等待元素可见（文件上传元素通常是 <input type="file">）
                await self.browser._page.wait_for_selector(
                    selector,
                    state="attached",  # 文件输入框可能是隐藏的，只需要 attached
                    timeout=5000
                )

                # 确保元素在视口中（如果可见的话）
                try:
                    await self.browser._page.locator(selector).scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    # 隐藏的文件输入框无法滚动，忽略此错误
                    logger.debug("  文件输入框可能是隐藏的，跳过滚动操作")

                # 执行文件上传（Playwright 的核心 API）
                await self.browser._page.locator(selector).set_input_files(file_path, timeout=3000)
                
                logger.info(f"✓ 【首选策略成功】文件上传成功: element_id={element_id}, file={file_path}")
                return ActionResult(
                    success=True,
                    message=f"文件上传成功: {os.path.basename(file_path)}",
                    data={
                        "element_id": element_id,
                        "file_path": file_path,
                        "file_name": os.path.basename(file_path),
                        "file_size": os.path.getsize(file_path)
                    }
                )

            except Exception as selector_error:
                # 首选策略失败，文件上传无法兜底
                error_msg = (
                    f"【上传失败】选择器失效且无法兜底: {str(selector_error)[:200]}... "
                    f"- 文件上传强依赖 DOM 节点，无法使用物理坐标"
                )
                logger.error(error_msg)
                
                return ActionResult(
                    success=False,
                    message=f"文件上传失败: {str(selector_error)[:100]}",
                    data={
                        "error": "selector_failed",
                        "element_id": element_id,
                        "file_path": file_path,
                        "detail": str(selector_error)[:200]
                    }
                )

        except Exception as e:
            error_msg = f"文件上传遇到未预期的异常: {str(e)}"
            logger.error(error_msg)
            return ActionResult(
                success=False,
                message=error_msg,
                data={
                    "error": "unexpected_exception",
                    "element_id": element_id,
                    "file_path": file_path,
                    "detail": str(e)[:200]
                }
            )

    async def scroll_into_view(self, element_id: str) -> bool:
        """
        滚动元素到视口内（增强版：支持页面级滚动 + 滚动距离优化）

        支持两种模式：
        1. 元素级滚动：element_id 非空时，滚动到指定元素
        2. 页面级滚动：element_id 为空时，向下滚动视口高度的 3/4（保留 1/4 上下文）

        Args:
            element_id: 元素 ID（来自感知层，可以是 int 或 str）
                       - 非空：滚动到指定元素
                       - 空字符串：执行页面级向下滚动

        Returns:
            bool: 滚动是否成功

        Raises:
            BrowserError: 滚动失败时抛出
        """
        import asyncio
        
        # ============ 模式 1: 页面级滚动（element_id 为空）============
        if element_id is None or element_id == "" or str(element_id).strip() == "":
            logger.info("执行页面级向下滚动（视口高度的 3/4）...")
            
            try:
                # 获取滚动前的位置
                before_scroll = await self.browser._page.evaluate("""
                    () => ({
                        scroll_y: window.scrollY,
                        scroll_height: document.documentElement.scrollHeight,
                        viewport_height: window.innerHeight
                    })
                """)
                
                logger.debug(f"  滚动前: scroll_y={before_scroll['scroll_y']}, "
                           f"scroll_height={before_scroll['scroll_height']}, "
                           f"viewport_height={before_scroll['viewport_height']}")
                
                # 计算滚动距离：视口高度的 3/4（保留 1/4 上下文）
                scroll_distance = int(before_scroll['viewport_height'] * 0.75)
                
                # 执行滚动
                await self.browser._page.evaluate(f"window.scrollBy(0, {scroll_distance})")
                await asyncio.sleep(0.5)  # 等待滚动完成
                
                # 获取滚动后的位置
                after_scroll = await self.browser._page.evaluate("""
                    () => ({
                        scroll_y: window.scrollY,
                        scroll_height: document.documentElement.scrollHeight,
                        viewport_height: window.innerHeight
                    })
                """)
                
                logger.debug(f"  滚动后: scroll_y={after_scroll['scroll_y']}, "
                           f"scroll_height={after_scroll['scroll_height']}")
                
                # 检测是否已经到底部
                is_at_bottom = (
                    after_scroll['scroll_y'] + after_scroll['viewport_height'] >= 
                    after_scroll['scroll_height'] - 10  # 10px 容差
                )
                
                if is_at_bottom:
                    logger.warning("⚠️  已滚动到页面底部，无法继续滚动")
                    print(f"⚠️  已滚动到页面底部")
                    raise BrowserError("已滚动到页面底部，目标元素可能不存在")
                
                # 检测滚动是否有效（实际滚动距离 > 10px）
                actual_scroll = after_scroll['scroll_y'] - before_scroll['scroll_y']
                if abs(actual_scroll) < 10:
                    logger.warning("⚠️  滚动无效，页面可能无法滚动")
                    print(f"⚠️  页面无法滚动")
                    raise BrowserError("页面无法滚动，可能已到达底部或页面不可滚动")
                
                logger.info(f"✓ 页面滚动成功: {before_scroll['scroll_y']} → {after_scroll['scroll_y']} "
                          f"(滚动了 {actual_scroll}px，约 {actual_scroll / before_scroll['viewport_height'] * 100:.0f}% 视口高度)")
                print(f"✓ 页面滚动成功: 滚动了 {actual_scroll}px")
                return True
                
            except BrowserError:
                # 已经是 BrowserError，直接抛出
                raise
            except Exception as e:
                error_msg = f"页面级滚动失败: {str(e)}"
                logger.error(error_msg)
                print(f"✗ {error_msg}")
                raise BrowserError(error_msg)

        # ============ 模式 2: 元素级滚动（element_id 非空）============
        try:
            # 【核心】使用 ElementRegistry 查询真实选择器
            selector = self.browser.element_registry.get_selector(element_id)
            
            if not selector:
                error_msg = (
                    f"元素 ID {element_id} 已过期或不在当前页面中，"
                    f"请重新调用感知引擎获取最新的页面信息"
                )
                print(f"✗ {error_msg}")
                logger.error(error_msg)
                raise BrowserError(error_msg)
            
            logger.debug(f"滚动操作: element_id={element_id} → selector={selector}")

            await self.browser._page.wait_for_selector(selector, timeout=10000)
            await self.browser._page.locator(selector).scroll_into_view_if_needed()

            print(f"✓ 滚动到视图成功: {element_id}")
            logger.info(f"✓ 滚动操作完成: element_id={element_id}, selector={selector}")
            return True

        except BrowserError:
            raise
        except Exception as e:
            error_msg = f"滚动到视图失败: {element_id} - {str(e)}"
            print(f"✗ {error_msg}")
            logger.error(error_msg)
            raise BrowserError(error_msg)

    async def select_option(self, element_id: str, value: str) -> bool:
        """
        选择下拉选项

        使用 ElementRegistry 查询真实选择器。

        Args:
            element_id: 选择元素 ID（来自感知层，可以是 int 或 str）
            value: 要选择的选项值

        Returns:
            bool: 选择是否成功

        Raises:
            BrowserError: 选择失败时抛出
        """
        if element_id is None:
            raise BrowserError("元素 ID 不能为空")
        
        if not value:
            raise BrowserError("选项值不能为空")

        try:
            # 【核心】使用 ElementRegistry 查询真实选择器
            selector = self.browser.element_registry.get_selector(element_id)
            
            if not selector:
                error_msg = (
                    f"元素 ID {element_id} 已过期或不在当前页面中，"
                    f"请重新调用感知引擎获取最新的页面信息"
                )
                print(f"✗ {error_msg}")
                logger.error(error_msg)
                raise BrowserError(error_msg)
            
            logger.debug(f"选项操作: element_id={element_id} → selector={selector}, value={value}")

            await self.browser._page.wait_for_selector(selector, timeout=10000)
            await self.browser._page.select_option(selector, value)

            print(f"✓ 选项选择成功: {element_id} -> '{value}'")
            logger.info(f"✓ 选项操作完成: element_id={element_id}, selector={selector}, value={value}")
            return True

        except BrowserError:
            raise
        except Exception as e:
            error_msg = f"选项选择失败: {element_id} -> '{value}' - {str(e)}"
            print(f"✗ {error_msg}")
            logger.error(error_msg)
            raise BrowserError(error_msg)

    async def human_intervene(self, action: Action) -> bool:
        """
        人工干预动作处理器
        
        当 Agent 遇到无法自动处理的情况（如验证码、登录弹窗等）时，
        调用此方法将浏览器控制权交给人类用户，等待用户完成操作后继续。
        
        Args:
            action: 包含 human_intervene 动作的 Action 对象
                    - target: 可以包含 area（影响的区域描述）
                    - input: 可以包含 reason（需要人工干预的原因）
        
        Returns:
            bool: 用户是否成功完成了操作
        
        特点：
        1. 在终端打印醒目的提示
        2. 阻塞等待用户操作（通过 input() 调用）
        3. 用户在浏览器中完成操作后回车
        4. 返回后，调用方（workflow）会强制执行新的截图和 DOM 采集
        """
        import asyncio
        
        # 【防护检查】安全提取动作参数
        reason = "未知原因"
        area = "页面"
        
        if action.input and isinstance(action.input, dict):
            reason = action.input.get("reason", "未知原因")
        
        if action.target and isinstance(action.target, dict):
            area = action.target.get("area", "页面")
        
        # 打印醒目的人工干预提示
        print("\n" + "=" * 90)
        print("⚠️  【人工干预需求 - Human Intervention Required】")
        print("=" * 90)
        print(f"\n🤖 Agent 原因: {reason}")
        print(f"📍 影响区域: {area}")
        print("\n📋 操作步骤:")
        print("  1. 查看浏览器窗口（应该已自动打开）")
        print("  2. 完成必要的操作（如登录、验证码、弹窗关闭等）")
        print("  3. 操作完成后，在此终端按下 [按回车键] 继续")
        print("  4. Agent 将自动重新感知页面并继续执行")
        print("\n💡 提示: 按 Ctrl+C 可中止整个过程")
        print("=" * 90 + "\n")
        
        # 阻塞等待用户操作
        loop = asyncio.get_event_loop()
        try:
            # 在后台线程中运行 input()，不阻塞事件循环
            await loop.run_in_executor(
                None,
                input,
                "➜ 请在浏览器中完成操作，操作完成后按【回车】继续... "
            )
            
            logger.info("✅ 用户确认操作完成，Agent 将重新感知页面...")
            print("\n✅ 用户确认操作完成，Agent 将重新感知页面...\n")
            return True
            
        except KeyboardInterrupt:
            logger.warning("❌ 用户中断了人工干预流程 (Ctrl+C)")
            print("\n\n❌ 用户中断了人工干预流程 (Ctrl+C)\n")
            return False
        except Exception as e:
            logger.error(f"⚠️  人工干预过程中出错: {str(e)}")
            print(f"\n⚠️  人工干预过程中出错: {str(e)}\n")
            return False
