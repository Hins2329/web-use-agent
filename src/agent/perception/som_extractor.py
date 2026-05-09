"""
Set-of-Mark (SoM) 视觉提取器

通过向页面注入 JavaScript 脚本，实现：
1. 视口筛选：仅保留可见区域内的元素
2. 语义剪枝：剔除无用布局元素，仅保留交互元素或文本叶子节点
3. 坐标提取：获取每个元素的绝对中心坐标
4. 动态画框：在页面上绘制编号的红色框，标注每个元素
5. 清理现场：移除画框 DOM，恢复页面原貌
"""

from typing import List, Dict, Any, Optional
import asyncio
from pathlib import Path

from ...utils.logger import setup_logger
from ...utils.exceptions import PerceptionError


logger = setup_logger("agent")


class SoMExtractor:
    """
    Set-of-Mark 视觉元素提取器
    
    通过在浏览器中执行 JavaScript 代码，进行视口剪枝、语义剪枝、
    坐标提取和动态画框。
    """

    # JavaScript 代码（在浏览器中执行）
    JS_EXTRACT_AND_MARK = r"""
    (function() {
        const INTERACTIVE_TAGS = new Set(['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA', 'OPTION', 'LABEL']);
        const CLICKABLE_ROLES = new Set(['button', 'link', 'tab', 'menuitem', 'checkbox', 'radio']);
        
        function isInViewport(rect) {
            return rect.top < window.innerHeight &&
                   rect.bottom > 0 &&
                   rect.left < window.innerWidth &&
                   rect.right > 0;
        }
        
        function isVisible(elem) {
            const style = window.getComputedStyle(elem);
            if (style.display === 'none') return false;
            if (style.visibility === 'hidden') return false;
            if (parseFloat(style.opacity) === 0) return false;
            const rect = elem.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        }
        
        function getXPath(elem) {
            // 严格判空保护：如果传入 null/undefined 或没有 nodeType，直接返回空字符串
            if (!elem || !elem.nodeType) {
                return '';
            }
            
            const paths = [];
            let current = elem;
            
            while (current && current.nodeType === Node.ELEMENT_NODE) {
                let index = 0;
                let sibling = current.previousSibling;
                
                while (sibling) {
                    if (sibling.nodeType === Node.ELEMENT_NODE && 
                        sibling.nodeName === current.nodeName) {
                        index++;
                    }
                    sibling = sibling.previousSibling;
                }
                
                const pathIndex = index > 0 ? `[${index + 1}]` : '[1]';
                paths.unshift(current.nodeName.toLowerCase() + pathIndex);
                
                // 防止 parentElement 为 null 导致的循环中断
                current = current.parentElement;
            }
            
            return paths.length > 0 ? '/' + paths.join('/') : '';
        }
        
        function getSelector(elem) {
            // 严格判空保护：如果传入 null/undefined，直接返回空字符串
            if (!elem) {
                return '';
            }
            
            try {
                if (elem.id && elem.id.length > 0) {
                    return '#' + elem.id.replace(/"/g, '\\"');
                }
                
                if (elem.classList && elem.classList.length > 0) {
                    const classes = Array.from(elem.classList).join('.');
                    if (classes) {
                        return '.' + classes.replace(/"/g, '\\"');
                    }
                }
                
                // 最后尝试 XPath，如果失败也返回空字符串
                const xpath = getXPath(elem);
                return xpath || '';
            } catch (e) {
                console.warn('[SoM] getSelector 异常:', e);
                return '';
            }
        }
        
        function getText(elem) {
            if (!elem) return '';
            
            try {
                if (elem.tagName === 'INPUT' || elem.tagName === 'TEXTAREA') {
                    return elem.value || elem.placeholder || '';
                }
                if (elem.tagName === 'IMG') {
                    return elem.alt || '';
                }
                const text = elem.innerText || elem.textContent || '';
                return text.trim().substring(0, 100);
            } catch (e) {
                console.warn('[SoM] getText 异常:', e);
                return '';
            }
        }
        
        function isClickableDiv(elem) {
            if (!elem) return false;
            
            try {
                if (elem.tagName !== 'DIV' && elem.tagName !== 'SPAN') return false;
                const style = window.getComputedStyle(elem);
                if (style.cursor === 'pointer') return true;
                if (elem.onclick || elem.getAttribute('onclick')) return true;
                const role = (elem.getAttribute('role') || '').toLowerCase();
                if (CLICKABLE_ROLES.has(role)) return true;
                return false;
            } catch (e) {
                console.warn('[SoM] isClickableDiv 异常:', e);
                return false;
            }
        }
        
        function shouldIncludeElement(elem) {
            if (!elem) return false;
            
            try {
                // 检查是否是交互元素
                if (INTERACTIVE_TAGS.has(elem.tagName)) return true;
                if (isClickableDiv(elem)) return true;
                
                // 检查是否有意义的文本叶子节点
                const text = getText(elem);
                if (text.length > 0 && elem.children.length === 0) {
                    return true;
                }
                return false;
            } catch (e) {
                console.warn('[SoM] shouldIncludeElement 异常:', e);
                return false;
            }
        }
        
        function extractElements() {
            const elements = [];
            const elementIds = new Map();
            let elementCounter = 0;
            
            // 遍历所有元素
            const allElements = document.querySelectorAll('*');
            
            for (let elem of allElements) {
                try {
                    // 检查是否应该包含
                    if (!shouldIncludeElement(elem)) continue;
                    
                    // 检查是否在视口内且可见
                    const rect = elem.getBoundingClientRect();
                    if (!isInViewport(rect) || !isVisible(elem)) continue;
                    
                    // 获取选择器（允许失败，返回空字符串）
                    let selector = '';
                    try {
                        selector = getSelector(elem);
                    } catch (e) {
                        console.warn('[SoM] 获取选择器失败，跳过此选择器:', e);
                        selector = '';
                    }
                    
                    // 增加计数器并创建 element_id
                    elementCounter++;
                    const element_id = elementCounter;
                    
                    // 【核心修复】计算绝对页面物理坐标（而非视口相对坐标）
                    // 添加 window.scrollX 和 window.scrollY 使坐标不受页面滚动影响
                    const center_x = Math.round(rect.left + window.scrollX + rect.width / 2);
                    const center_y = Math.round(rect.top + window.scrollY + rect.height / 2);
                    
                    // 坐标至上策略：只要有坐标，即使 selector 为空也保留此元素
                    // （执行层可以依靠坐标进行物理点击兜底）
                    elements.push({
                        element_id: element_id,
                        type: elem.tagName.toLowerCase(),
                        text: getText(elem),
                        center_x: center_x,
                        center_y: center_y,
                        selector: selector,  // 可能为空字符串，由执行层兜底处理
                        width: Math.round(rect.width),
                        height: Math.round(rect.height)
                    });
                    
                    // 存储元素引用（用于后续画框）
                    elementIds.set(element_id, { elem, rect, element_id });
                    
                } catch (e) {
                    // 单个元素处理失败，记录警告并跳过，绝不中断整个流程
                    console.warn('[SoM] 处理单个元素失败，跳过此元素:', e);
                    continue;
                }
            }
            
            return { elements, elementIds };
        }
        
        function createMarkOverlay(elementIds) {
            try {
                // 创建一个用于绘制框的容器
                const overlay = document.createElement('div');
                overlay.id = 'som-overlay-container';
                overlay.style.cssText = `
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    pointer-events: none;
                    z-index: 999999;
                `;
                document.body.appendChild(overlay);
                
                // 为每个元素创建框和标签
                for (const [elementId, { rect }] of elementIds) {
                    try {
                        // 创建框
                        const box = document.createElement('div');
                        box.className = 'som-box';
                        box.style.cssText = `
                            position: fixed;
                            top: ${rect.top}px;
                            left: ${rect.left}px;
                            width: ${rect.width}px;
                            height: ${rect.height}px;
                            border: 2px solid red;
                            pointer-events: none;
                            z-index: 999999;
                        `;
                        overlay.appendChild(box);
                        
                        // 创建标签（显示 element_id）
                        const label = document.createElement('div');
                        label.className = 'som-label';
                        label.style.cssText = `
                            position: fixed;
                            top: ${Math.max(0, rect.top - 20)}px;
                            left: ${rect.left}px;
                            background-color: red;
                            color: white;
                            font-size: 12px;
                            font-weight: bold;
                            padding: 2px 6px;
                            border-radius: 3px;
                            pointer-events: none;
                            z-index: 1000000;
                            font-family: Arial, sans-serif;
                        `;
                        label.textContent = String(elementId);
                        overlay.appendChild(label);
                    } catch (e) {
                        console.warn('[SoM] 画框失败，跳过此元素:', elementId, e);
                        continue;
                    }
                }
                
                return overlay;
            } catch (e) {
                console.error('[SoM] 创建覆盖层失败:', e);
                return null;
            }
        }
        
        function cleanupOverlay() {
            try {
                const overlay = document.getElementById('som-overlay-container');
                if (overlay) {
                    overlay.remove();
                }
            } catch (e) {
                console.warn('[SoM] 清理覆盖层异常:', e);
            }
        }
        
        // 主流程
        try {
            const { elements, elementIds } = extractElements();
            createMarkOverlay(elementIds);
            return elements;
        } catch (e) {
            console.error('[SoM] 主流程异常:', e);
            return [];
        }
    })();
    """

    def __init__(self):
        """初始化 SoM 提取器"""
        self._overlay_created = False

    async def extract_and_mark(self, page: Any) -> List[Dict[str, Any]]:
        """
        在页面上提取和标记元素。

        通过执行 JavaScript：
        1. 视口筛选：仅保留可见区域内的元素
        2. 语义剪枝：仅保留交互元素或有意义的文本节点
        3. 坐标提取：获取每个元素的绝对中心坐标
        4. 动态画框：在页面上绘制编号的红色框

        Args:
            page: Playwright Page 对象

        Returns:
            List[Dict]: 提取的元素列表，每个元素包含：
                - element_id: 编号 (1, 2, 3, ...)
                - type: 元素类型（如 "button", "input"）
                - text: 元素文本内容
                - center_x: 元素中心 X 坐标（相对于视口）
                - center_y: 元素中心 Y 坐标（相对于视口）
                - selector: CSS/XPath 选择器
                - width: 元素宽度
                - height: 元素高度

        Raises:
            PerceptionError: 提取失败时抛出
        """
        try:
            logger.debug("开始执行 JavaScript 提取和画框...")
            
            # 执行 JavaScript 脚本
            elements = await page.evaluate(self.JS_EXTRACT_AND_MARK)
            
            if not isinstance(elements, list):
                raise PerceptionError(f"JS 返回格式错误：期望列表，得到 {type(elements)}")
            
            self._overlay_created = True
            logger.info(f"✓ 已标记 {len(elements)} 个元素到页面上")
            
            return elements
            
        except Exception as exc:
            raise PerceptionError(f"SoM 提取失败: {exc}")

    async def take_marked_screenshot(self, page: Any, screenshot_path: Optional[str] = None) -> str:
        """
        在元素被标记后进行截图。

        Args:
            page: Playwright Page 对象
            screenshot_path: 可选的保存路径，若不提供则生成临时文件

        Returns:
            str: 截图文件的路径

        Raises:
            PerceptionError: 截图失败时抛出
        """
        try:
            if not screenshot_path:
                import tempfile
                tmp_file = Path(tempfile.mktemp(suffix=".png"))
                screenshot_path = str(tmp_file)
            
            logger.debug(f"保存带标记的截图到: {screenshot_path}")
            await page.screenshot(path=screenshot_path, full_page=True)
            logger.debug(f"✓ 截图已保存")
            
            return screenshot_path
            
        except Exception as exc:
            raise PerceptionError(f"截图失败: {exc}")

    async def cleanup_overlay(self, page: Any) -> None:
        """
        清理页面上的标记覆盖层。

        Args:
            page: Playwright Page 对象

        Raises:
            PerceptionError: 清理失败时抛出
        """
        if not self._overlay_created:
            return
        
        try:
            logger.debug("清理标记覆盖层...")
            await page.evaluate(r"""
            (function() {
                const overlay = document.getElementById('som-overlay-container');
                if (overlay) {
                    overlay.remove();
                }
            })();
            """)
            
            self._overlay_created = False
            logger.debug("✓ 标记覆盖层已清理")
            
        except Exception as exc:
            logger.warning(f"清理覆盖层失败: {exc}")
