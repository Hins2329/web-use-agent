"""
浏览器控制器模块

使用 Playwright 异步库实现 Chrome 浏览器控制。
提供基本的页面操作接口，包括连接、导航、截图、内容获取等。
"""

import asyncio
import logging
import tempfile
from datetime import datetime
from typing import Optional, Tuple, Dict
from pathlib import Path

from playwright.async_api import async_playwright, Browser, Page, Playwright, TimeoutError as PlaywrightTimeoutError

from ...config.settings import get_config
from ...utils.exceptions import BrowserError

logger = logging.getLogger(__name__)


class ElementRegistry:
    """
    元素ID映射注册表 - 支持持久化ID
    
    维护感知层生成的 element_id (整数) 与执行层需要的选择器 (CSS/XPath)
    之间的映射关系，支持基于选择器特征的持久化ID。
    
    核心特性：
    1. selector -> element_id 反向映射（持久化）
    2. element_id -> selector 正向映射（会话内有效）
    3. 同一个选择器始终映射到相同的ID，即使DOM重新排序或页面刷新
    
    工作流：
    1. 感知层: clean_and_parse() → 生成 element_id
    2. 感知层: register_elements() → 调用 bulk_register()
    3. bulk_register(): 检查每个selector是否已知
       - 已知: 复用原有ID
       - 未知: 分配新ID，记录selector->ID映射
    4. 执行层: get_selector(element_id) → 查询Registry，获取Selector
    5. 新页面: on_page_change() → 清空会话映射但保留selector持久化映射
    """
    
    def __init__(self):
        """初始化注册表"""
        self._registry: Dict[int, str] = {}  # element_id -> CSS selector (会话映射)
        self._element_details: Dict[int, dict] = {}  # 存储元素的详细信息用于调试
        self._selector_to_id: Dict[str, int] = {}  # selector -> element_id (持久化映射)
        self._next_persistent_id = 1  # 持久化ID计数器
        self._coordinates: Dict[int, dict] = {}  # element_id -> {center_x, center_y} (坐标映射)
    
    def register(self, element_id: int, selector: str, element_info: dict = None) -> None:
        """
        注册单个元素的ID→Selector映射
        
        【核心修复】绝对信任感知层传来的 element_id：
        - 不再通过 selector 去重或重新生成 ID
        - 直接使用感知层传来的 element_id 存入映射
        - 即使 selector 为空字符串，也要存储（执行层会使用坐标兜底）
        
        Args:
            element_id: 感知层生成的元素ID (整数)
            selector: 元素的CSS选择器或XPath（可以为空字符串）
            element_info: (可选) 元素的详细信息，用于调试和日志
                         可包含 center_x 和 center_y 坐标信息
        """
        # 【修复】检查 element_info 中是否包含感知层传来的 element_id
        # 如果包含，则绝对信任并使用该 ID，不再重新生成
        if element_info and 'element_id' in element_info:
            element_id = element_info['element_id']
        
        if not isinstance(element_id, int):
            raise ValueError(f"element_id 必须是整数，收到: {type(element_id).__name__}")
        
        # 【修复】允许空选择器，执行层会使用坐标兜底策略
        if not isinstance(selector, str):
            selector = ""  # 强制转换为空字符串
        
        # 直接存入映射，不进行去重或重新生成 ID
        self._registry[element_id] = selector
        if element_info:
            self._element_details[element_id] = element_info
            
            # 提取并存储坐标信息
            if 'center_x' in element_info and 'center_y' in element_info:
                self._coordinates[element_id] = {
                    'center_x': element_info['center_x'],
                    'center_y': element_info['center_y']
                }
    
    def get_selector(self, element_id: int) -> Optional[str]:
        """
        根据element_id查询Selector
        
        Args:
            element_id: 感知层的元素ID (整数或字符串的数字)
        
        Returns:
            str: CSS选择器 (如果找到)
            None: 如果ID已过期或不存在
        """
        # 支持字符串数字转换（从JSON响应中）
        if isinstance(element_id, str):
            try:
                element_id = int(element_id)
            except ValueError:
                return None
        
        return self._registry.get(element_id)
    
    def get_coordinates(self, element_id: int) -> Optional[Dict[str, int]]:
        """
        根据element_id查询元素的中心坐标
        
        Args:
            element_id: 感知层的元素ID (整数或字符串的数字)
        
        Returns:
            Dict: {"center_x": int, "center_y": int} (如果找到)
            None: 如果ID不存在或没有坐标信息
        """
        if isinstance(element_id, str):
            try:
                element_id = int(element_id)
            except ValueError:
                return None
        
        return self._coordinates.get(element_id)
    
    def bulk_register(self, elements: list) -> Dict[int, int]:
        """
        批量注册多个元素 - 【核心修复】绝对信任感知层 ID
        
        【修复说明】：
        - 彻底废弃通过 selector 去重和分配 ID 的逻辑
        - 直接使用感知层传来的 element_id，不再重新生成或去重
        - 即使 selector 为空字符串，也要存储（执行层会使用坐标兜底）
        - 确保整个单步 ReAct 循环内的 ID 是与 JS 提取时的一对一绝对绑定
        
        Args:
            elements: 感知层返回的元素列表，每个元素应包含 element_id
        
        Returns:
            Dict[int, int]: element_index -> element_id 的映射
                           供perception确认注册结果
        """
        count = 0
        index_to_element_id: Dict[int, int] = {}  # 元素索引 -> element_id
        
        for idx, elem in enumerate(elements):
            if not isinstance(elem, dict):
                continue
            
            # 【核心修复】直接使用感知层传来的 element_id
            element_id = elem.get('element_id')
            if element_id is None:
                # 如果感知层没有提供 element_id，跳过该元素
                continue
            
            # 获取 selector（可以为空字符串）
            selector = elem.get('selector', '')
            
            # 【核心修复】直接注册，不进行去重或重新生成 ID
            self.register(element_id, selector, elem)
            
            # 记录元素索引到 element_id 的映射
            index_to_element_id[idx] = element_id
            count += 1
        
        return index_to_element_id
    
    def generate_selector(self, elem: dict) -> Optional[str]:
        """
        为元素生成选择器（公开方法，供perception使用）
        
        Args:
            elem: 元素信息字典
        
        Returns:
            str: CSS选择器，或 None 如果无法生成
        """
        return self._generate_selector(elem)
    
    def _generate_selector(self, elem: dict) -> Optional[str]:
        """
        为元素生成最优CSS选择器 - 改进的多级fallback策略
        
        【核心改进】防止生成太通用的selector，避免jQuery语法：
        - 避免仅使用role或type的单一属性selector
        - 优先使用属性组合（type + role + text）来增加唯一性
        - 所有生成的selector必须符合Playwright标准（CSS或XPath）
        - 不使用jQuery特定语法（:contains等）
        
        优先级（从高到低）：
        1. id属性 (最准确)
        2. class属性组合
        3. data-* / aria-* 属性
        4. type + name 属性
        5. type + [type='value'] 属性 (input等)
        6. type + [placeholder] 属性
        7. type + [title] 属性
        8. type + [role] 属性
        9. 纯type属性 (最后的fallback)
        
        【说明】文本内容不在selector中编码，因为：
        - :contains()是jQuery语法，Playwright不支持
        - 文本容易改变，导致selector失效
        - 文本匹配应该在bulk_register的冲突检测中特殊处理
        
        Args:
            elem: 元素信息字典
        
        Returns:
            str: CSS选择器，或 None 如果无法生成
        """
        attributes = elem.get('attributes', {})
        elem_type = elem.get('type', 'div').lower()
        elem_role = elem.get('role', '').strip()
        
        # 优先1: id 属性 (最准确)
        elem_id = attributes.get('id')
        if elem_id and elem_id.strip():
            return f"#{elem_id}"
        
        # 优先2: class 属性（所有class组合）
        elem_class = attributes.get('class')
        if elem_class:
            class_list = elem_class.split() if isinstance(elem_class, str) else []
            if class_list:
                # 使用所有class组合以提高唯一性
                class_selector = ".".join(class_list)
                return f"{elem_type}.{class_selector}"
        
        # 优先3: 其他可识别属性 (data-*, aria-*)
        for attr_key in ['data-id', 'data-testid', 'aria-label', 'aria-describedby']:
            attr_val = attributes.get(attr_key)
            if attr_val and attr_val.strip():
                return f"[{attr_key}='{attr_val}']"
        
        # 优先4: name 属性
        name = attributes.get('name')
        if name and name.strip():
            return f"{elem_type}[name='{name}']"
        
        # 优先5: type 属性（对input等元素）
        input_type = attributes.get('type')
        if input_type and input_type.strip():
            return f"{elem_type}[type='{input_type}']"
        
        # 优先6: placeholder属性（对input等表单元素）
        placeholder = elem.get('placeholder', '')
        if placeholder and placeholder.strip():
            return f"{elem_type}[placeholder='{placeholder[:50]}']"
        
        # 优先7: title属性
        title = elem.get('title', '')
        if title and title.strip():
            return f"{elem_type}[title='{title[:50]}']"
        
        # 优先8: role属性（type + role组合）
        if elem_role:
            return f"{elem_type}[role='{elem_role}']"
        
        # 优先9: 仅使用type属性
        # 这可能不唯一，但至少能定位到元素类型
        # bulk_register会检测冲突并通过其他机制区分
        if elem_type and elem_type.strip():
            return elem_type
        
        # 如果都失败了，返回None
        return None
    
    def clear(self) -> None:
        """
        清空会话映射但保留持久化映射
        
        在每一轮新的感知开始时调用：
        1. 清空当前会话的 element_id -> selector 映射
        2. 保留 selector -> element_id 的持久化映射
        3. 这样同一个选择器仍然能映射到相同的ID
        
        只有在URL改变或页面完全替换时，才应调用 clear_persistent()。
        """
        old_size = len(self._registry)
        self._registry.clear()
        self._element_details.clear()
        self._coordinates.clear()  # 清空坐标映射
        if old_size > 0:
            import logging
            logging.getLogger(__name__).debug(
                f"清空会话映射 ({old_size} 个元素)，保留持久化映射 ({len(self._selector_to_id)} 个选择器)"
            )
    
    def clear_persistent(self) -> None:
        """
        完全清空所有映射（包括持久化映射）
        
        仅在以下情况调用：
        1. 页面URL改变
        2. 浏览器导航到新页面
        3. 用户明确要求重置
        """
        old_session = len(self._registry)
        old_persistent = len(self._selector_to_id)
        self._registry.clear()
        self._element_details.clear()
        self._selector_to_id.clear()
        self._coordinates.clear()  # 清空坐标映射
        self._next_persistent_id = 1
        if old_session > 0 or old_persistent > 0:
            import logging
            logging.getLogger(__name__).info(
                f"完全清空映射：会话({old_session}) + 持久化({old_persistent})"
            )
    
    def get_debug_info(self) -> dict:
        """
        获取调试信息
        
        返回当前注册表的统计信息和示例。
        """
        sample_size = min(5, len(self._registry))
        sample = dict(list(self._registry.items())[:sample_size])
        
        return {
            "total_registered": len(self._registry),
            "sample_mappings": sample,
            "first_id": min(self._registry.keys()) if self._registry else None,
            "last_id": max(self._registry.keys()) if self._registry else None,
        }
    
    def __repr__(self) -> str:
        return f"ElementRegistry(registered={len(self._registry)})"


class BrowserController:
    """
    Chrome DevTools Protocol 控制器

    使用 Playwright 异步库控制 Chrome 浏览器，提供页面操作的基本接口。
    支持连接已存在的浏览器实例或启动新的浏览器实例。
    """

    def __init__(self):
        """
        初始化浏览器控制器

        从全局配置中获取浏览器相关配置。
        """
        self.config = get_config().browser
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._connected = False
        self.last_screenshot_path: Optional[str] = None  # 存储最后一次截图的路径
        self._screenshot_count = 0  # 截图计数器
        self.element_registry = ElementRegistry()  # 元素ID→Selector映射表

    async def connect(self) -> None:
        """
        连接浏览器

        优先尝试通过调试端口连接已打开的浏览器实例，
        如果失败则根据配置启动新的浏览器实例。

        Raises:
            BrowserError: 连接失败时抛出
        """
        try:
            self._playwright = await async_playwright().start()

            # 优先尝试连接已存在的浏览器实例
            try:
                # 尝试连接到本地 Chrome 调试端口 (通常是 9222)
                self._browser = await self._playwright.chromium.connect_over_cdp(
                    "http://localhost:9222"
                )
                print("✓ 成功连接到已存在的 Chrome 实例")
            except Exception:
                # 连接失败，启动新的浏览器实例
                print("未找到已存在的 Chrome 实例，启动新的浏览器...")
                
                # 创建用户数据目录
                user_data_dir = Path(self.config.user_data_dir)
                user_data_dir.mkdir(parents=True, exist_ok=True)
                
                # 使用 launch_persistent_context 来正确处理用户数据目录
                launch_options = {
                    "headless": self.config.headless,
                    "args": [
                        f"--window-size={self.config.window_size[0]},{self.config.window_size[1]}",
                        "--start-maximized",  # 窗口最大化
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-accelerated-2d-canvas",
                        "--no-first-run",
                        "--no-zygote",
                        "--disable-gpu",
                    ]
                }

                if self.config.executable_path:
                    launch_options["executable_path"] = self.config.executable_path

                # 使用 launch_persistent_context 而不是 launch
                context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(user_data_dir.absolute()),
                    **launch_options
                )
                
                # 从持久化上下文获取浏览器
                self._browser = context
                
                print("✓ 成功启动新的 Chrome 实例")

            # 创建或获取页面
            if len(self._browser.pages) > 0:
                self._page = self._browser.pages[0]
            else:
                self._page = await self._browser.new_page()

            self._connected = True
            print("✓ 浏览器控制器连接成功")

        except Exception as e:
            error_msg = f"浏览器连接失败: {str(e)}"
            print(f"✗ {error_msg}")
            await self._cleanup()
            raise BrowserError(error_msg)

    async def navigate(self, url: str) -> None:
        """
        导航到指定 URL

        采用智能等待策略：优先使用 networkidle 等待网络完全空闲，
        若超时则记录警告并继续执行（适应淘宝等复杂 SPA 页面）。
        
        Args:
            url: 要导航到的完整 URL

        Raises:
            BrowserError: 导航失败时抛出
        """
        if not self._connected or not self._page:
            raise BrowserError("浏览器未连接，请先调用 connect()")

        try:
            # 升级为 networkidle 等待策略，适应现代 SPA 页面的异步渲染
            # 淘宝等网站可能永远无法完全 idle，设置 try-except 捕获 TimeoutError
            try:
                await self._page.goto(url, wait_until="networkidle", timeout=15000)
                logger.info(f"✓ 成功导航到: {url}（网络空闲状态）")
            except PlaywrightTimeoutError:
                # 淘宝等网站可能有长连接或轮询请求，导致永久无法 idle
                # 记录警告但不抛出异常，直接继续执行
                logger.warning(f"⚠️  导航超时（networkidle），但继续执行: {url}")
            except Exception as e:
                # 其他导航错误仍然按异常处理
                raise e
            
            # 固定延迟 3 秒，确保页面完全加载和动画完成
            print("⏳ 等待页面完全加载 (3s)...")
            await asyncio.sleep(3)
            
        except Exception as e:
            error_msg = f"页面导航异常: {str(e)}"
            print(f"✗ {error_msg}")
            raise BrowserError(error_msg)

    async def click(self, selector: str) -> bool:
        """
        点击指定选择器的元素

        Args:
            selector: CSS 选择器或 XPath

        Returns:
            bool: 点击是否成功

        Raises:
            BrowserError: 点击失败时抛出
        """
        if not self._connected or not self._page:
            raise BrowserError("浏览器未连接，请先调用 connect()")

        try:
            # 等待元素出现并可见
            await self._page.wait_for_selector(selector, timeout=10000)
            await self._page.click(selector)
            print(f"✓ 成功点击元素: {selector}")
            return True
        except Exception as e:
            error_msg = f"元素点击失败: {selector} - {str(e)}"
            print(f"✗ {error_msg}")
            raise BrowserError(error_msg)

    async def type_text(self, selector: str, text: str) -> bool:
        """
        在指定选择器的元素中输入文本

        Args:
            selector: CSS 选择器或 XPath
            text: 要输入的文本内容

        Returns:
            bool: 输入是否成功

        Raises:
            BrowserError: 输入失败时抛出
        """
        if not self._connected or not self._page:
            raise BrowserError("浏览器未连接，请先调用 connect()")

        try:
            # 等待元素出现并可见
            await self._page.wait_for_selector(selector, timeout=10000)
            # 清空现有内容并输入新文本
            await self._page.fill(selector, "")
            await self._page.fill(selector, text)
            print(f"✓ 成功输入文本到元素: {selector}")
            return True
        except Exception as e:
            error_msg = f"文本输入失败: {selector} - {str(e)}"
            print(f"✗ {error_msg}")
            raise BrowserError(error_msg)

    async def screenshot(self) -> bytes:
        """
        截取当前页面截图，保存文件并记录路径
        
        截图保存位置和命名：
        - Manual 模式：./screenshots/step_XX_YYYYMMDD_HHMMSS.png
        - Auto 模式：./screenshots/step_XX_YYYYMMDD_HHMMSS.png（也保存，便于调试）
        - 文件名格式统一为 step_{序号:02d}_{时间戳}.png

        Returns:
            bytes: PNG 格式的截图数据

        Raises:
            BrowserError: 截图失败时抛出
        """
        if not self._connected or not self._page:
            raise BrowserError("浏览器未连接，请先调用 connect()")

        try:
            screenshot_bytes = await self._page.screenshot(full_page=True)
            
            # 统一的截图目录和命名逻辑
            screenshot_dir = Path(get_config().vlm.screenshot_dir)
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            
            # 递增计数器和生成时间戳
            self._screenshot_count += 1
            now = datetime.now()
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            screenshot_filename = f"step_{self._screenshot_count:02d}_{timestamp}.png"
            screenshot_path = screenshot_dir / screenshot_filename
            
            # 保存截图
            screenshot_path.write_bytes(screenshot_bytes)
            self.last_screenshot_path = str(screenshot_path)
            
            print(f"✓ 成功截取页面截图，已保存到: {self.last_screenshot_path}")
            return screenshot_bytes
        except Exception as e:
            error_msg = f"截图失败: {str(e)}"
            print(f"✗ {error_msg}")
            raise BrowserError(error_msg)

    async def get_page_content(self) -> str:
        """
        获取当前页面的 HTML 内容

        Returns:
            str: 页面的完整 HTML 内容

        Raises:
            BrowserError: 获取内容失败时抛出
        """
        if not self._connected or not self._page:
            raise BrowserError("浏览器未连接，请先调用 connect()")

        try:
            content = await self._page.content()
            print("✓ 成功获取页面内容")
            return content
        except Exception as e:
            error_msg = f"获取页面内容失败: {str(e)}"
            print(f"✗ {error_msg}")
            raise BrowserError(error_msg)

    async def get_state(self) -> dict:
        """
        获取当前页面的完整状态(HTML、URL、截图路径)

        Returns:
            dict: 包含以下键的字典：
                - html: 页面的 HTML 内容
                - url: 当前页面 URL
                - screenshot_path: 最后一次截图的路径（可能为 None）

        Raises:
            BrowserError: 获取状态失败时抛出
        """
        return {
            "html": await self.get_page_content(),
            "url": self._page.url if self._page else "",
            "screenshot_path": getattr(self, "last_screenshot_path", None)
        }

    async def upload_file(self, selector: str, file_path: str) -> bool:
        """
        上传文件到指定选择器的文件输入元素

        Args:
            selector: 文件输入元素的 CSS 选择器
            file_path: 要上传的文件的完整路径

        Returns:
            bool: 上传是否成功

        Raises:
            BrowserError: 上传失败时抛出
        """
        if not self._connected or not self._page:
            raise BrowserError("浏览器未连接，请先调用 connect()")

        try:
            # 检查文件是否存在
            if not Path(file_path).exists():
                raise BrowserError(f"文件不存在: {file_path}")

            # 等待文件输入元素出现
            await self._page.wait_for_selector(selector, timeout=10000)

            # 设置文件到输入元素
            await self._page.set_input_files(selector, file_path)
            print(f"✓ 成功上传文件: {file_path} -> {selector}")
            return True
        except Exception as e:
            error_msg = f"文件上传失败: {file_path} -> {selector} - {str(e)}"
            print(f"✗ {error_msg}")
            raise BrowserError(error_msg)

    async def wait_for_element(self, selector: str, timeout: int = 10000) -> bool:
        """
        等待指定选择器的元素出现

        Args:
            selector: CSS 选择器或 XPath
            timeout: 等待超时时间（毫秒），默认 10000ms

        Returns:
            bool: 元素是否在超时时间内出现

        Raises:
            BrowserError: 等待失败时抛出
        """
        if not self._connected or not self._page:
            raise BrowserError("浏览器未连接，请先调用 connect()")

        try:
            await self._page.wait_for_selector(selector, timeout=timeout)
            print(f"✓ 元素已出现: {selector}")
            return True
        except Exception as e:
            error_msg = f"等待元素超时: {selector} - {str(e)}"
            print(f"✗ {error_msg}")
            raise BrowserError(error_msg)

    async def disconnect(self) -> None:
        """
        断开浏览器连接并清理资源
        
        如果 keep_open 为 True，只断开 CDP 连接，保持浏览器进程运行。
        """
        await self._cleanup()
        print("✓ 浏览器控制器已断开连接")

    async def _cleanup(self) -> None:
        """
        清理浏览器资源
        """
        try:
            if self._page:
                await self._page.close()
                self._page = None

            if self._browser:
                if not self.config.keep_open:
                    # 不保持打开，直接关闭
                    await self._browser.close()
                    self._browser = None
                else:
                    # 保持浏览器打开，只断开连接
                    print("✓ 浏览器保持开启（仅断开连接）")
                    self._browser = None

            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

            self._connected = False
        except Exception as e:
            print(f"清理浏览器资源时出错: {e}")

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.disconnect()
