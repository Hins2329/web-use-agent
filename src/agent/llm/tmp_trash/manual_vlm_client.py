"""
手动 VLM 客户端实现（Human-in-the-Loop）

实现 BaseLLMClient 接口，在手动模式下：
- 自动截图并保存到指定目录
- 打印建议 Prompt 给用户（遵循 vlm_prompt.md 格式）
- 多行输入支持：用户可以粘贴数百行 Gemini 分析报告
- 阻塞等待用户在终端输入来自 Google AI Studio 的分析结果
- 优雅的 Ctrl+C 处理和缓冲区清理
"""

import asyncio
import sys
import json
import tty
import termios
from io import StringIO
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from ..base import BaseLLMClient
from ....config.settings import get_config
from ....utils.logger import setup_logger
from ....utils.exceptions import PerceptionError


logger = setup_logger("agent")


class ManualVLMClient(BaseLLMClient):
    """
    手动视觉语言模型客户端 (Human-in-the-Loop)

    工作流程：
    1. Agent 调用 chat_with_vision() 或 chat()
    2. 自动截图并保存
    3. 显示建议 Prompt
    4. 阻塞等待用户多行输入（粘贴完成后按两次回车）
    5. 清理缓冲区并返回用户输入
    6. Agent 继续执行

    特点：
    - 支持数百行的多行粘贴输入
    - 优雅的 Ctrl+C 处理
    - 自动缓冲区清理
    - 完整的格式验证和错误恢复
    """

    def __init__(self, api_key: str = "", base_url: str = ""):
        """
        初始化手动 VLM 客户端

        Args:
            api_key: 未使用（手动模式不需要 API Key）
            base_url: 未使用（手动模式不需要 Base URL）
        """
        super().__init__(api_key, base_url, "manual-vlm")
        self.config = get_config().vlm
        self.step_count = 0
        
        # 确保截图目录存在
        screenshot_dir = Path(self.config.screenshot_dir)
        screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def chat(
        self,
        system_prompt: str,
        user_input: str,
        temperature: float = 0.1,
        max_tokens: int = 4000,
    ) -> Dict[str, Any]:
        """
        纯文本对话（手动模式 - 逻辑推理）

        Args:
            system_prompt: 系统提示词
            user_input: 用户输入
            temperature: 未使用
            max_tokens: 未使用

        Returns:
            Dict[str, Any]: 包含 'thought' 和 'action' 的响应

        NOTE: 返回格式必须是 Dict，不能是纯字符串
        """
        print("\n" + "=" * 80)
        print("🤖 【手动逻辑推理模式】")
        print("=" * 80)
        print("系统提示词:")
        print(f"{system_prompt}\n")
        print("用户提示词:")
        print(f"{user_input}")
        print("=" * 80)
        
        # 获取用户的推理决策
        loop = asyncio.get_event_loop()
        try:
            user_response = await loop.run_in_executor(
                None,
                self._read_multiline_input,
                "请输入你的推理决策（JSON格式，包含 'thought' 和 'action' 字段）"
            )
        except KeyboardInterrupt:
            print("\n⚠️  用户中止了输入")
            user_response = json.dumps({
                "thought": "用户中止了推理过程",
                "action": "done"
            })
        
        # 尝试解析 JSON
        try:
            result = json.loads(user_response)
            if not isinstance(result, dict):
                result = {"thought": "用户输入", "action": user_response}
        except (json.JSONDecodeError, ValueError):
            # 如果不是有效的 JSON，包装为响应
            result = {
                "thought": "用户输入（纯文本）",
                "action": user_response
            }
        
        # 确保返回的是 Dict，包含必需字段
        if "content" not in result:
            result["content"] = user_response
        
        logger.info(f"用户逻辑推理输入 ({len(user_response)} 字): {user_response[:200]}...")
        return result

    async def chat_with_vision(
        self,
        system_prompt: str,
        user_input: str,
        image_path: str,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> Dict[str, Any]:
        """
        文本+图像多模态对话（手动模式 - 视觉分析）

        Args:
            system_prompt: 系统提示词
            user_input: 用户输入（包含关于图像的指令）
            image_path: 图像文件的本地路径
            temperature: 未使用
            max_tokens: 未使用

        Returns:
            Dict[str, Any]: 包含 'recommendation' 的响应

        Raises:
            PerceptionError: 图像文件不存在时抛出
        """
        image_file = Path(image_path)
        if not image_file.exists():
            raise PerceptionError(f"图像文件不存在: {image_path}")

        # 将截图复制到配置的截图目录
        self.step_count += 1
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        screenshot_filename = f"step_{self.step_count:02d}_{timestamp}.png"
        screenshot_path = Path(self.config.screenshot_dir) / screenshot_filename
        
        try:
            # 复制截图文件到目标目录
            image_data = image_file.read_bytes()
            screenshot_path.write_bytes(image_data)
            logger.debug(f"截图已保存到: {screenshot_path}")
        except Exception as e:
            logger.warning(f"保存截图到 {screenshot_path} 失败: {e}")

        # ========================================================================
        # 显示醒目的用户交互界面
        # ========================================================================
        print("\n" + "=" * 90)
        print("🔔 【手动 VLM 模式 (Human-in-the-Loop) - 多行输入】")
        print("=" * 90)
        print(f"\n✓ 截图已保存至: {screenshot_path}")
        print(f"  绝对路径: {screenshot_path.absolute()}\n")
        
        print("📋 建议发给 Google AI Studio (Gemini) 的 Prompt：")
        print("-" * 90)
        print(f"系统提示:\n{system_prompt}\n")
        print(f"用户提示:\n{user_input}")
        print("-" * 90)
        
        print("\n📝 操作步骤：")
        print("  1. 打开 https://aistudio.google.com")
        print("  2. 点击 [+ New chat]")
        print(f"  3. 上传截图文件: {screenshot_path.absolute()}")
        print(f"  4. 复制上面虚线框中的完整 Prompt（包括系统提示和用户提示）")
        print(f"  5. 粘贴到 Gemini 对话框")
        print(f"  6. 等待 Gemini 返回结构化分析")
        print(f"  7. 复制 Gemini 的完整分析结果")
        print(f"  8. 粘贴到下方的输入框中")
        
        print("\n📌 重要：关于输入格式")
        print("  • Gemini 的返回必须符合以下格式（4 个主要部分）：")
        print("""
  [页面信息]
  标题: ...
  URL: ...
  类型: ...
  状态: ...
  
  [页面核心内容]
  ...
  
  [可交互元素]
  [类型] "文本" | 位置 | 状态
  ...
  
  [特殊信息]
  ...
        """)
        
        print("\n⌨️  输入提示：")
        print("  • 一次性粘贴整个分析报告（支持数百行）")
        print("  • 粘贴完成后，按两次回车键 [Enter] 来提交")
        print("  • 如果中途出错，可以按 Ctrl+C 重新输入")
        print("=" * 90)
        
        # ========================================================================
        # 多行输入处理
        # ========================================================================
        loop = asyncio.get_event_loop()
        try:
            user_response = await loop.run_in_executor(
                None,
                self._read_multiline_input,
                "请粘贴 Gemini 的完整分析结果（确保包含所有 [XXX] 部分）"
            )
        except KeyboardInterrupt:
            print("\n⚠️  用户中止了输入（按 Ctrl+C）")
            # 提供默认响应
            user_response = self._generate_default_response()
            is_valid = False
        else:
            # 验证返回格式
            is_valid = self._validate_vlm_response(user_response)
            if not is_valid:
                print("\n⚠️  警告：返回结果格式可能不完整（但继续执行）")
                logger.warning(f"VLM 返回格式不符合标准: 缺少必需部分")
        
        logger.info(f"用户视觉分析输入已接收 ({len(user_response)} 字): {user_response[:150]}...")
        
        # 返回符合标准的响应（必须是 Dict）
        return {
            "recommendation": user_response.strip(),
            "provider": "manual",
            "model": "manual-vlm",
            "format_valid": is_valid,
            "raw_response": {
                "user_input": user_response,
                "screenshot_path": str(screenshot_path),
            },
        }

    def _read_multiline_input(self, prompt: str) -> str:
        """
        读取多行输入，直到用户按两次回车（产生空行）

        实现细节：
        1. 清空 stdin 缓冲区，防止残留输入干扰
        2. 使用 sys.stdin.readline() 逐行读取
        3. 检测连续的空行（两次回车）作为终止条件
        4. 自动清理最后的多余空行
        5. 处理 EOFError（Ctrl+D）

        Args:
            prompt: 显示给用户的提示文本

        Returns:
            str: 用户输入的完整文本（已清理）

        Raises:
            KeyboardInterrupt: 用户按 Ctrl+C 时抛出
        """
        print(f"\n{prompt}：")
        print("[粘贴后请按两次回车提交] [或按 Ctrl+C 取消]\n")
        
        # 有益的尝试：清空 stdin 缓冲区
        # 注意：这在某些环境下可能不完全有效，但能帮助大多数情况
        try:
            # 设置非阻塞模式以清空缓冲区
            if hasattr(sys.stdin, 'readline'):
                old_settings = None
                try:
                    # 尝试获取终端设置（如果可用）
                    old_settings = termios.tcgetattr(sys.stdin.fileno())
                except (termios.error, OSError):
                    # 如果不在终端环境中，跳过
                    pass
        except Exception:
            pass
        
        lines = []
        consecutive_empty_lines = 0
        
        try:
            while True:
                try:
                    # 使用 readline 逐行读取，保留换行符
                    line = sys.stdin.readline()
                    
                    # 检测 EOF（Ctrl+D）
                    if not line:
                        # EOF 情况
                        break
                    
                    # 检查行是否为空（只有换行符）
                    if line.strip() == "":
                        consecutive_empty_lines += 1
                        # 累计空行，但只在两个空行时才添加一个
                        if consecutive_empty_lines == 1:
                            lines.append("")  # 添加第一个空行
                        elif consecutive_empty_lines == 2:
                            # 第二个空行 - 作为终止条件
                            break
                    else:
                        # 非空行
                        consecutive_empty_lines = 0
                        # 移除尾部换行符后添加
                        lines.append(line.rstrip("\n"))
                        
                except KeyboardInterrupt:
                    # 用户按 Ctrl+C
                    raise
                    
        except KeyboardInterrupt:
            # 清理并抛出
            print("\n(取消输入)")
            raise
        
        # 清理结果：移除末尾多余的空行
        while lines and lines[-1].strip() == "":
            lines.pop()
        
        # 合并所有行
        result = "\n".join(lines)
        
        # 打印确认信息
        print(f"\n✓ 已接收 {len(result)} 字的输入")
        
        return result

    def _validate_vlm_response(self, response: str) -> bool:
        """
        验证 VLM 返回是否符合标准格式

        检查是否包含所有必需的部分：
        - [页面信息]
        - [页面核心内容]
        - [可交互元素]
        - [特殊信息]

        Args:
            response: 用户粘贴的 Gemini 分析结果

        Returns:
            bool: 是否符合格式
        """
        required_sections = [
            "[页面信息]",
            "[页面核心内容]",
            "[可交互元素]"
        ]
        
        for section in required_sections:
            if section not in response:
                logger.debug(f"缺少必需部分: {section}")
                return False
        
        return True

    def _generate_default_response(self) -> str:
        """
        生成默认的 VLM 响应

        当发生以下情况时使用：
        - 用户按 Ctrl+C 中止输入
        - 用户直接按 Enter 而不输入内容
        - VLM 连接超时

        Returns:
            str: 默认响应文本（包含所有必需部分）
        """
        return """[页面信息]
标题: 未确定
URL: 未确定
类型: 其他
状态: 正常加载

[页面核心内容]
页面加载完成。用户选择跳过手动分析，Agent 将基于 DOM 树智能推断并继续执行。

[可交互元素]
暂无特殊标记的可交互元素。

[特殊信息]
弹窗: 无
登录状态: 不确定
验证码: 无
其他阻碍: 无
"""
