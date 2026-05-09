"""
本地工具执行模块

负责消费本地工具相关的 Action、执行本地 OS 操作。
包含读取本地文件、未来扩展本地文件写入等非浏览器操作。
"""

from .local_executor import LocalToolExecutor

__all__ = ["LocalToolExecutor"]
