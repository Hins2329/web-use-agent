"""
本地工具执行器模块

提供本地系统操作能力，支持文件读写、目录列表等操作。
所有操作完全独立于浏览器层，不涉及任何 Playwright 或浏览器相关的库。
"""

import logging
import json
from typing import Dict, Any, Optional
from pathlib import Path

from ..execution.actions import Action, ActionResult

logger = logging.getLogger(__name__)


class LocalToolExecutor:
    """
    本地工具执行器

    消费本地工具相关的 Action，执行本地 OS 操作。
    支持读取本地文件、文件系统操作等非浏览器交互。
    """

    def __init__(self):
        """
        初始化本地工具执行器
        """
        self.logger = logging.getLogger(__name__)

    async def execute_tool(self, action: Action) -> ActionResult:
        """
        执行本地工具动作

        Args:
            action: 本地工具动作对象，必须包含 action 字段

        Returns:
            ActionResult: 执行结果，包含成功状态、消息和数据

        Raises:
            ValueError: 当 action 对象格式错误时抛出
        """
        try:
            # 【防护检查】确保 action 对象的完整性
            if not hasattr(action, 'action'):
                return ActionResult(
                    success=False,
                    message="Action 对象缺少 'action' 属性",
                    data={}
                )

            action_type = action.action

            # 【路由分发】根据动作类型调用对应的处理器
            if action_type == "read_file":
                return await self._read_file(action)
            else:
                return ActionResult(
                    success=False,
                    message=f"未支持的本地工具类型: {action_type}",
                    data={}
                )

        except Exception as e:
            self.logger.error(f"执行本地工具时发生异常: {str(e)}", exc_info=True)
            return ActionResult(
                success=False,
                message=f"执行本地工具失败: {str(e)}",
                data={}
            )

    async def _read_file(self, action: Action) -> ActionResult:
        """
        读取本地文件

        从 action.input 中获取 file_path，支持 .txt 和 .json 文件。
        自动识别文件类型并进行相应的解析。

        Args:
            action: 包含 input.file_path 的动作对象

        Returns:
            ActionResult: 成功时返回 {success=True, data={content: <内容>}}
                         失败时返回 {success=False, message=<错误信息>}
        """
        try:
            # 【参数提取】从 action.input 获取文件路径
            if action.input is None or not isinstance(action.input, dict):
                return ActionResult(
                    success=False,
                    message="缺少 input 参数或 input 不是字典类型",
                    data={}
                )

            file_path = action.input.get("file_path")
            if not file_path:
                return ActionResult(
                    success=False,
                    message="缺少必需参数: file_path",
                    data={}
                )

            # 【路径转换】将字符串转换为 Path 对象
            file_path_obj = Path(file_path)

            # 【存在性检查】确保文件存在
            if not file_path_obj.exists():
                return ActionResult(
                    success=False,
                    message=f"文件不存在: {file_path}",
                    data={}
                )

            # 【类型检查】验证是否是文件
            if not file_path_obj.is_file():
                return ActionResult(
                    success=False,
                    message=f"路径不是文件: {file_path}",
                    data={}
                )

            # 【文件读取】使用标准 open 读取文件
            file_extension = file_path_obj.suffix.lower()

            try:
                with open(file_path_obj, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 【内容解析】根据文件类型进行适当的处理
                parsed_content: Any = content

                if file_extension == ".json":
                    try:
                        parsed_content = json.loads(content)
                    except json.JSONDecodeError as e:
                        return ActionResult(
                            success=False,
                            message=f"JSON 解析失败: {str(e)} (行: {e.lineno}, 列: {e.colno})",
                            data={}
                        )
                elif file_extension == ".txt":
                    # 纯文本文件，保持原样
                    parsed_content = content
                else:
                    # 其他类型的文件也作为文本处理
                    self.logger.warning(f"不是标准文件类型 (.txt/.json): {file_extension}，将作为文本处理")
                    parsed_content = content

                # 【成功返回】返回文件内容
                return ActionResult(
                    success=True,
                    message="文件读取成功",
                    data={"content": parsed_content}
                )

            except UnicodeDecodeError as e:
                return ActionResult(
                    success=False,
                    message=f"文件编码错误（必须是 UTF-8）: {str(e)}",
                    data={}
                )
            except IOError as e:
                return ActionResult(
                    success=False,
                    message=f"文件读取 I/O 错误: {str(e)}",
                    data={}
                )

        except Exception as e:
            self.logger.error(f"读取文件时发生异常: {str(e)}", exc_info=True)
            return ActionResult(
                success=False,
                message=f"读取文件失败: {str(e)}",
                data={}
            )
