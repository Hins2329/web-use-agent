"""
日志配置模块

提供统一的日志设置接口，支持多输出目标（控制台和文件）、
日志级别配置、以及按天轮转的文件日志。
"""

import sys
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Optional


def setup_logger(
    name: str = "agent",
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    max_bytes: int = 10485760,  # 10MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    设置日志记录器

    配置日志输出到控制台和文件，支持按天自动轮转日志文件。
    
    Args:
        name: 日志记录器名称
        log_level: 日志级别 ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        log_file: 日志文件路径，如果指定则输出到文件；默认为 "./logs/{name}.log"
        max_bytes: 单个日志文件最大字节数（用于大小轮转），默认 10MB
        backup_count: 保留的备份日志文件数，默认 5
    
    Returns:
        logging.Logger: 配置好的日志记录器实例
    
    Raises:
        ValueError: 如果日志级别不合法
    """
    # 验证日志级别
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if log_level.upper() not in valid_levels:
        raise ValueError(f"Invalid log level: {log_level}. Must be one of {valid_levels}")

    # 获取或创建日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper()))

    # 避免重复添加处理器
    if logger.handlers:
        return logger

    # 日志格式
    log_format = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    # 文件处理器（如果指定了日志文件）
    if log_file:
        log_file_path = Path(log_file)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)

        # 按天轮转的文件处理器
        # 每天午夜轮转，保留指定数量的备份
        file_handler = TimedRotatingFileHandler(
            filename=str(log_file_path),
            when="midnight",
            interval=1,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(log_format)
        logger.addHandler(file_handler)

    return logger


# 创建默认日志记录器
default_logger = setup_logger(
    name="agent",
    log_level="INFO",
    log_file="./logs/agent.log",
)
