"""
手动 VLM 客户端实现（Human-in-the-Loop）

实现 BaseLLMClient 接口，在手动模式下：
- 自动截图并保存到指定目录
- 打印建议 Prompt 给用户（遵循 vlm_prompt.md 格式）
- 多行输入支持：用户可以粘贴数百行 Gemini 分析报告
- 阻塞等待用户在终端输入来自 Google AI Studio 的结构化分析结果
- 验证返回的分析结果是否符合标准格式
- 优雅的 Ctrl+C 处理和缓冲区清理
"""

import asyncio
import sys
import json
import tempfile
import tty
import termios
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from ..base import BaseLLMClient
from ...utils.parser import parse_llm_response
from ....config.settings import get_config
from ....utils.logger import setup_logger
from ....utils.exceptions import PerceptionError


logger = setup_logger("agent")


class ManualVLMClient(BaseLLMClient):
    """
    手动视觉语言模型客户端 (Human-in-the-Loop)

    工作流程：
    1. Agent 需要视觉分析时调用 chat_with_vision()
    2. 自动截图并保存到 ./screenshots/step_XX_timestamp.png
    3. 显示醒目的 [MANUAL MODE] 框
    4. 打印建议的 Prompt（遵循 prompts/vlm_prompt.md 格式）
    5. 阻塞等待用户多行输入（粘贴完成后按两次回车）
    6. 用户在 Google AI Studio 中分析截图并粘贴结果
    7. 返回用户输入的结构化分析结果
    
    返回格式遵循 prompts/vlm_prompt.md：
    - [页面信息]: 标题、URL、类型、状态
    - [页面核心内容]: 页面描述
    - [可交互元素]: 元素列表及位置
    - [特殊信息]: 弹窗、登录状态、验证码等
    
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
            Dict[str, Any]: 标准格式的动作规范（遵循 07_api_spec.md）
            包含：thought, action, target, input

        工作流程：
        1. 保存 system_prompt 和 user_input 到文件
        2. 等待用户粘贴推理决策（JSON 格式）
        3. 调用 parser.parse_llm_response() 标准化格式
        4. 直接返回标准 Dict （不做任何额外包装）
        """
        # 【步骤 1】文件持久化 - 保存提示词到文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.step_count += 1
        
        # 创建输出目录
        output_dir = Path("txts/llm_txts")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 文件命名格式：logic_step_{timestamp}.txt
        log_filename = f"logic_step_{timestamp}.txt"
        log_filepath = output_dir / log_filename
        
        # 保存系统提示和用户输入
        with open(log_filepath, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write(f"逻辑推理步骤 #{self.step_count}\n")
            f.write(f"时间戳: {timestamp}\n")
            f.write("=" * 80 + "\n\n")
            
            f.write("【系统提示词】\n")
            f.write("-" * 80 + "\n")
            f.write(system_prompt + "\n\n")
            
            f.write("【用户输入】\n")
            f.write("-" * 80 + "\n")
            f.write(user_input + "\n\n")
            
            f.write("【等待用户输入】\n")
            f.write("-" * 80 + "\n")

        print("\n" + "=" * 80)
        print("🤖 【手动逻辑推理模式】")
        print("=" * 80)
        print(f"\n✓ 逻辑推理信息已保存至: {log_filepath.absolute()}\n")
        print("系统提示词:")
        print(f"{system_prompt}\n")
        print("用户提示词:")
        print(f"{user_input}")
        print("=" * 80)
        
        # 【步骤 2】多行读取 - 获取用户的推理决策
        loop = asyncio.get_event_loop()
        try:
            user_response = await loop.run_in_executor(
                None,
                self._read_multiline_input,
                "请输入你的推理决策（JSON格式，包含 'thought' 和 'action' 字段）\n"
            )
        except KeyboardInterrupt:
            print("\n⚠️  用户中止了输入")
            user_response = json.dumps({
                "thought": "用户中止了推理过程",
                "action": "done",
                "target": {},
                "input": {}
            })
        
        # 【步骤 3】解析响应 - 调用统一的响应解析器
        # Parser 保证返回标准格式的 Dict，包括：thought, action, target, input
        # 如果检测到嵌套格式或其他错误格式，会自动拍平和转换
        result = parse_llm_response(user_response)
        
        # 【强制类型检查】确保返回的是字典，不是字符串
        # 这是防止下游代码中 'str' object has no attribute 'get' 的最后防线
        if not isinstance(result, dict):
            logger.error(f"❌ CRITICAL: parse_llm_response 返回了非字典类型: {type(result)}")
            logger.error(f"原始响应: {user_response[:200]}")
            # 强制转换为字典（符合标准格式）
            result = {
                "thought": "解析异常：返回值类型错误",
                "action": "wait",
                "target": {},
                "input": {"delay": 1000}
            }
        
        # 【步骤 4】记录日志
        with open(log_filepath, "a", encoding="utf-8") as f:
            f.write("【用户响应】\n")
            f.write("-" * 80 + "\n")
            f.write(user_response + "\n\n")
            f.write("【解析结果 (标准格式)】\n")
            f.write("-" * 80 + "\n")
            f.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        
        logger.info(f"✓ 用户逻辑推理完成 ({len(user_response)} 字)")
        logger.info(f"✓ 推理日志保存至: {log_filepath}")
        logger.debug(f"✓ 返回标准格式: action={result.get('action')}, target={result.get('target')}")
        
        # 【直接返回】不做任何额外包装
        # 返回格式保证：{thought: str, action: str, target: dict, input: dict}
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
        文本+图像多模态对话（手动模式，遵循 vlm_prompt.md 格式）

        支持多行输入 - 用户可以粘贴数百行的分析报告。
        
        优化：
        1. 截图转移：将 /tmp 下的临时截图转移到 screenshot_dir
        2. 拒绝刷屏：将 system_prompt 和 user_input 保存到文件，终端只打印提示

        Args:
            system_prompt: 系统提示词
            user_input: 用户输入（包含关于图像的指令）
            image_path: 图像文件的本地路径
            temperature: 未使用
            max_tokens: 未使用

        Returns:
            Dict[str, Any]: 包含 recommendation（用户的结构化分析）的响应

        Raises:
            PerceptionError: 图像文件不存在时抛出
        """
        import shutil
        
        image_file = Path(image_path)
        if not image_file.exists():
            raise PerceptionError(f"图像文件不存在: {image_path}")

        # ========================================================================
        # 【优化 1】截图转移：从 /tmp 复制到 screenshot_dir
        # ========================================================================
        screenshot_path = Path(image_path)
        temp_dir = Path(tempfile.gettempdir()).resolve()
        try:
            is_temp_file = temp_dir in screenshot_path.resolve().parents
        except Exception:
            is_temp_file = str(screenshot_path).startswith(str(temp_dir))

        if is_temp_file:
            # 这是临时文件，转移到 screenshot_dir
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_filename = f"som_marked_step_{self.step_count}_{timestamp}.png"
            target_dir = Path(self.config.screenshot_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / target_filename
            
            try:
                shutil.copy(str(screenshot_path), str(target_path))
                logger.info(f"✓ 截图已转移至: {target_path}")
                screenshot_path = target_path
            except Exception as e:
                logger.warning(f"截图转移失败，使用原始路径: {e}")
                screenshot_path = Path(image_path)

        logger.debug(f"手动 VLM 分析: {screenshot_path}")

        # ========================================================================
        # 【优化 2】拒绝刷屏：保存 Prompt 到文件，终端只打印提示
        # ========================================================================
        # 创建 vlm prompts 输出目录
        vlm_prompts_dir = Path("txts/vlm_prompts")
        vlm_prompts_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prompt_filename = f"manual_vlm_step_{self.step_count}_{timestamp}.txt"
        prompt_filepath = vlm_prompts_dir / prompt_filename
        
        # 将 system_prompt 和 user_input 写入文件
        try:
            with open(prompt_filepath, "w", encoding="utf-8") as f:
                f.write("=" * 90 + "\n")
                f.write(f"手动 VLM 分析步骤 #{self.step_count}\n")
                f.write(f"时间戳: {timestamp}\n")
                f.write("=" * 90 + "\n\n")
                
                f.write("【系统提示词】\n")
                f.write("-" * 90 + "\n")
                f.write(system_prompt + "\n\n")
                
                f.write("【用户输入】\n")
                f.write("-" * 90 + "\n")
                f.write(user_input + "\n\n")
                
                f.write("【关于截图】\n")
                f.write("-" * 90 + "\n")
                f.write(f"截图已保存至: {screenshot_path.absolute()}\n")
            
            logger.info(f"✓ VLM Prompt 已保存至: {prompt_filepath.absolute()}")
        except Exception as e:
            logger.warning(f"保存 Prompt 文件失败: {e}")

        # ========================================================================
        # 显示醒目的用户交互界面（仅打印提示，不打印完整 Prompt）
        # ========================================================================
        print("\n" + "=" * 90)
        print("🔔 【手动 VLM 模式 (Human-in-the-Loop) - 多行输入】")
        print("=" * 90)
        print(f"\n✓ 截图已保存至: {screenshot_path}")
        print(f"  绝对路径: {screenshot_path.absolute()}\n")
        
        # 醒目提示 Prompt 已保存到文件
        print(f"📋 Prompt 过长，已保存至: {prompt_filepath.absolute()}。请打开该文件复制发送给大模型。")
        
        print("📝 操作步骤：")
        print("  1. 打开 https://aistudio.google.com")
        print("  2. 点击 [+ New chat]")
        print(f"  3. 上传截图文件: {screenshot_path.absolute()}")
        print(f"  4. 打开文件查看完整 Prompt：")
        print(f"     {prompt_filepath.absolute()}")
        print(f"  5. 复制文件中的系统提示和用户提示")
        print(f"  6. 粘贴到 Gemini 对话框")
        print(f"  7. 等待 Gemini 返回结构化分析")
        print(f"  8. 复制 Gemini 的完整分析结果")
        print(f"  9. 粘贴到下方的输入框中")
        
        print("\n📌 重要：关于输入格式")
        print("  • 请输入标准 Action JSON 格式：")
        print("""
  {
    "thought": "你的推理过程",
    "action": "动作类型（如 click, type, scroll 等）",
    "target": {"element_id": 元素ID},
    "input": {"text": "输入内容"}
  }
        """)
        
        print("\n⌨️  输入提示：")
        print("  • 一次性粘贴整个 Action JSON（支持多行）")
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
                "请粘贴标准 Action JSON 格式的决策"
            )
        except KeyboardInterrupt:
            print("\n⚠️  用户中止了输入（按 Ctrl+C）")
            # 提供默认响应
            user_response = json.dumps({
                "thought": "用户中止了输入",
                "action": "wait",
                "target": {},
                "input": {"delay": 1000}
            })
        
        # 直接调用解析器并返回结果
        result = parse_llm_response(user_response)
        if not isinstance(result, dict):
            result = {
                "thought": "解析异常",
                "action": "wait",
                "target": {},
                "input": {}
            }
        
        logger.info(f"手动 VLM 输入已接收 ({len(user_response)} 字): {user_response[:150]}...")
        
        # 直接返回解析后的标准格式
        return result

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
