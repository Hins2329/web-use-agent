"""
感知引擎模块

实现 Set-of-Mark (SoM) 视觉感知与极致 DOM 剪枝。
通过 JavaScript 注入进行视口筛选、语义剪枝、坐标提取和动态画框，
最终输出符合 PageSchema 的精简结构化数据。
"""

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from .dom_parser import DOMParser, PageSchema, PageElement
from .som_extractor import SoMExtractor
from ..llm.factory import LLMFactory
from ...utils.exceptions import PerceptionError, LLMError


logger = logging.getLogger(__name__)


class PerceptionEngine:
    """
    感知引擎 - 集成 SoM 视觉提取和极致剪枝

    工作流程：
    1. 使用 SoM 提取器进行视口剪枝、语义剪枝、坐标提取
    2. 动态画框并生成带标记的截图（vlm_hints）
    3. 将提取的元素注册到 ElementRegistry
    4. 返回极致精简的 PageSchema（Token 消耗 < 3K）
    """

    def __init__(self):
        self.dom_parser = DOMParser()
        self.som_extractor = SoMExtractor()
        # 通过工厂获取视觉实例（使用 GLM-4.6V-Flash）
        self.vlm_client = LLMFactory.get_instance(role="vision")
        self._cache_cleared = False  # 用于跟踪缓存清空状态
        
        # 【截图哈希缓存】用于减少多模态 token 消耗
        self._last_screenshot_hash: Optional[str] = None
        self._last_screenshot_b64: Optional[str] = None

    def clear_cache(self) -> None:
        """
        清空感知层缓存。
        
        在每个 ReAct 循环周期中由 workflow 调用，
        确保下一轮 perception 必须重新采集页面状态。
        """
        self._cache_cleared = True
        logger.debug("✓ 感知缓存已标记为待清空")

    def _compute_screenshot_hash(self, screenshot_bytes: bytes) -> str:
        """
        计算截图的感知哈希（像素采样）。
        
        将截图缩放到 16x16 灰度图并计算 MD5，用于快速判断截图是否变化。
        只有哈希完全相同时才复用缓存，保守策略避免误判。
        
        Args:
            screenshot_bytes: 截图的字节数据
            
        Returns:
            str: MD5 哈希值（32位十六进制字符串）
        """
        try:
            from PIL import Image
            import hashlib
            import io
            
            # 缩放到 16x16 灰度图进行像素采样
            img = Image.open(io.BytesIO(screenshot_bytes)).convert("L").resize((16, 16))
            return hashlib.md5(img.tobytes()).hexdigest()
        except Exception as e:
            logger.warning(f"计算截图哈希失败: {e}，返回空哈希")
            return ""  # 返回空字符串，确保不会匹配任何缓存

    async def understand(self, page_handler: Any, user_goal: Optional[str] = "") -> Dict[str, Any]:
        """
        理解页面并返回结构化结果。

        优先使用 SoM 视觉感知进行极致剪枝；生成带标记截图；
        将元素注册到 ElementRegistry，确保下游执行层能找到每个节点。

        Args:
            page_handler: 页面处理对象（BrowserController 实例）
                         必须包含 element_registry 和 _page 等属性
            user_goal: 用户当前目标描述

        Returns:
            Dict[str, Any]: 包含 page_schema 以及可选 vlm_hints
        """
        try:
            # 检查必要的页面对象
            if not hasattr(page_handler, '_page') or not page_handler._page:
                raise PerceptionError("page_handler 必须包含有效的 Playwright Page 对象（_page）")

            page = page_handler._page
            screenshot_path = None

            # ============ Phase 1: SoM 视觉提取 ============
            logger.info("【Phase 1】执行 SoM 视觉提取和画框...")
            som_elements = await self.som_extractor.extract_and_mark(page)
            
            if not som_elements:
                logger.warning("⚠️  SoM 未提取到任何元素，降级使用 DOM 解析")
                return await self._fallback_to_dom(page_handler, user_goal)

            logger.info(f"✓ SoM 提取成功: {len(som_elements)} 个元素")

            # ============ Phase 2: 防抖等待（GPU 渲染缓冲） ============
            # 在画框完成与截图之间强制等待 0.8 秒
            # 理由：给浏览器 GPU 充足时间完成红色边框渲染，
            #      同时为页面的突发重绘（淘宝 SPA）留出缓冲时间
            logger.debug("【防抖】等待浏览器渲染红框（0.8秒）...")
            await asyncio.sleep(0.8)
            logger.debug("✓ 防抖完成")

            # ============ Phase 3: 生成带标记的截图 ============
            logger.info("【Phase 3】生成带标记的截图（vlm_hints）...")
            screenshot_path = await self.som_extractor.take_marked_screenshot(page)
            logger.info(f"✓ 截图已生成: {screenshot_path}")
            
            # ============ Phase 3.5: 截图哈希缓存判断 ============
            # 读取截图文件并计算哈希，判断是否可以复用上一张截图
            screenshot_b64 = None
            try:
                screenshot_bytes = Path(screenshot_path).read_bytes()
                current_hash = self._compute_screenshot_hash(screenshot_bytes)
                
                if current_hash and current_hash == self._last_screenshot_hash and self._last_screenshot_b64:
                    # 截图未变化，复用缓存
                    logger.info("✓ 截图未变化，复用缓存截图（节省多模态 token）")
                    screenshot_b64 = self._last_screenshot_b64
                else:
                    # 截图有变化，更新缓存
                    import base64
                    screenshot_b64 = base64.b64encode(screenshot_bytes).decode()
                    self._last_screenshot_hash = current_hash
                    self._last_screenshot_b64 = screenshot_b64
                    logger.debug(f"✓ 截图已更新缓存（哈希: {current_hash[:8]}...）")
            except Exception as e:
                # 缓存失败时降级：使用新截图，不抛异常
                logger.warning(f"截图哈希缓存处理失败: {e}，降级使用新截图")
                import base64
                screenshot_bytes = Path(screenshot_path).read_bytes()
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode()
                self._last_screenshot_hash = None
                self._last_screenshot_b64 = None

            # ============ Phase 4: 清理画框 ============
            logger.info("【Phase 4】清理页面标记...")
            await self.som_extractor.cleanup_overlay(page)
            logger.info("✓ 画框已清理")

            # ============ Phase 5: 构建 PageSchema ============
            logger.info("【Phase 4】构建极致精简 PageSchema...")
            page_schema = self._build_page_schema_from_som(page_handler, som_elements)
            logger.info(f"✓ PageSchema 已构建: {len(page_schema.elements)} 个元素")

            # ============ Phase 6: 注册到 ElementRegistry ============
            logger.info("【Phase 5】同步元素到 ElementRegistry...")
            if hasattr(page_handler, 'element_registry'):
                # 清空会话映射（保留持久化映射）
                page_handler.element_registry.clear()
                
                # 批量注册元素
                index_to_persistent_id = page_handler.element_registry.bulk_register(
                    [elem.to_dict() for elem in page_schema.elements]
                )
                
                # 更新 element_id 为 persistent_id
                updated_elements = []
                for idx, elem in enumerate(page_schema.elements):
                    if idx in index_to_persistent_id:
                        persistent_id = index_to_persistent_id[idx]
                        elem.element_id = persistent_id
                        updated_elements.append(elem)
                
                page_schema.elements = updated_elements
                
                logger.info(
                    f"✓ 已注册 {len(index_to_persistent_id)} 个元素到 ElementRegistry"
                )

            # ============ Phase 7: 组装返回结果 ============
            logger.info("【Phase 7】组装返回结果...")
            result = {"page_schema": page_schema.to_dict()}
            
            # 添加 vlm_hints（带标记的截图）
            if screenshot_path and Path(screenshot_path).exists():
                result["vlm_hints"] = {
                    "screenshot_path": screenshot_path,
                    "elements_marked": len(som_elements),
                    "description": "带 Set-of-Mark 编号的页面截图"
                }
            
            return result

        except Exception as exc:
            logger.error(f"SoM 感知失败: {exc}")
            # 降级到 DOM 解析
            logger.info("降级到 DOM 解析...")
            return await self._fallback_to_dom(page_handler, user_goal)

    def _build_page_schema_from_som(self, page_handler: Any, som_elements: list) -> PageSchema:
        """
        从 SoM 提取的元素数据构建 PageSchema。

        Args:
            page_handler: 页面处理对象
            som_elements: SoM 提取的元素列表

        Returns:
            PageSchema: 构建的页面结构
        """
        page_schema = PageSchema()
        page_schema.url = self._get_url(page_handler)
        page_schema.title = self._get_title(page_handler)
        page_schema.summary = "通过 SoM 视觉提取得到的页面结构"

        # 将 SoM 元素转换为 PageElement
        for som_elem in som_elements:
            element = PageElement(
                element_id=som_elem.get("element_id", 0),
                type=som_elem.get("type", "unknown"),
                text=som_elem.get("text", ""),
                interactable=True,
                role=som_elem.get("type", "unknown"),
                selector=som_elem.get("selector"),
                center_x=som_elem.get("center_x"),
                center_y=som_elem.get("center_y"),
                title=None,
                placeholder=None,
                attributes={},
            )
            page_schema.elements.append(element)

        return page_schema

    async def _fallback_to_dom(self, page_handler: Any, user_goal: str) -> Dict[str, Any]:
        """
        降级到 DOM 解析的备选方案。

        Args:
            page_handler: 页面处理对象
            user_goal: 用户目标

        Returns:
            Dict[str, Any]: 返回结果
        """
        try:
            html = await self._resolve_html(page_handler)
            page_schema = self.dom_parser.clean_and_parse(html)
            page_schema.url = await self._resolve_url(page_handler)
            
            # 注册到 ElementRegistry
            if hasattr(page_handler, 'element_registry'):
                page_handler.element_registry.clear()
                
                index_to_persistent_id = page_handler.element_registry.bulk_register(
                    [elem.to_dict() for elem in page_schema.elements]
                )
                
                updated_elements = []
                for idx, elem in enumerate(page_schema.elements):
                    if idx in index_to_persistent_id:
                        persistent_id = index_to_persistent_id[idx]
                        elem.element_id = persistent_id
                        updated_elements.append(elem)
                
                page_schema.elements = updated_elements

            return {"page_schema": page_schema.to_dict()}

        except Exception as exc:
            logger.error(f"DOM 降级失败: {exc}")
            raise PerceptionError(f"感知引擎完全失败: {exc}")

    def _get_url(self, page_handler: Any) -> str:
        """
        从 page_handler 获取当前 URL。

        Args:
            page_handler: 页面处理对象

        Returns:
            str: 页面 URL
        """
        if hasattr(page_handler, '_page') and page_handler._page:
            return page_handler._page.url
        if hasattr(page_handler, 'url'):
            return page_handler.url
        return ""

    def _get_title(self, page_handler: Any) -> str:
        """
        从 page_handler 获取页面标题。

        Args:
            page_handler: 页面处理对象

        Returns:
            str: 页面标题
        """
        if hasattr(page_handler, '_page') and page_handler._page:
            try:
                # 通过同步方式获取标题（需要在异步上下文中）
                # 这里先返回空字符串，后续可以通过 evaluate 获取
                return ""
            except:
                return ""
        return ""

    async def _resolve_html(self, page_handler: Any) -> str:
        """
        从 page_handler 获取 HTML 内容。

        Args:
            page_handler: 页面处理对象

        Returns:
            str: 页面 HTML
        """
        if hasattr(page_handler, "html") and isinstance(page_handler.html, str):
            return page_handler.html
        if hasattr(page_handler, "get_html"):
            return await self._call_maybe_async(page_handler.get_html)
        if hasattr(page_handler, "get_page_content"):
            return await self._call_maybe_async(page_handler.get_page_content)
        if hasattr(page_handler, "content") and isinstance(page_handler.content, str):
            return page_handler.content
        raise PerceptionError("无法从 page_handler 获取 HTML 内容")

    async def _resolve_url(self, page_handler: Any) -> str:
        """
        从 page_handler 获取当前 URL。

        Args:
            page_handler: 页面处理对象

        Returns:
            str: 页面 URL
        """
        if hasattr(page_handler, "url") and isinstance(page_handler.url, str):
            return page_handler.url
        if hasattr(page_handler, "current_url") and isinstance(page_handler.current_url, str):
            return page_handler.current_url
        if hasattr(page_handler, "_page") and page_handler._page:
            return page_handler._page.url
        return ""

    async def _resolve_screenshot_path(self, page_handler: Any) -> str:
        """
        从 page_handler 获取截图路径。

        Args:
            page_handler: 页面处理对象

        Returns:
            str: 截图文件路径
        """
        if hasattr(page_handler, "last_screenshot_path") and page_handler.last_screenshot_path:
            return page_handler.last_screenshot_path
        if hasattr(page_handler, "screenshot_path") and isinstance(page_handler.screenshot_path, str):
            return page_handler.screenshot_path
        if hasattr(page_handler, "screenshot"):
            screenshot_data = await self._call_maybe_async(page_handler.screenshot)
            if isinstance(screenshot_data, bytes):
                tmp_file = Path(tempfile.mktemp(suffix=".png"))
                tmp_file.write_bytes(screenshot_data)
                return str(tmp_file)
        raise PerceptionError("无法从 page_handler 获取截图路径或截图数据")

    async def _call_maybe_async(self, func_or_method: Any) -> Any:
        """
        调用可能是异步的函数或方法。

        Args:
            func_or_method: 函数或方法

        Returns:
            Any: 函数的返回值
        """
        if callable(func_or_method):
            result = func_or_method()
            if asyncio.iscoroutine(result):
                return await result
            return result
        return func_or_method

