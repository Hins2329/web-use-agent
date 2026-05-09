"""
分层异常定义模块

定义应用程序在不同层级的异常类，用于精细化的错误处理和日志记录。
"""


class BaseAgentError(Exception):
    """
    基础异常类
    
    所有应用程序异常的根类，用于统一捕获和处理项目内的所有异常。
    """

    def __init__(self, message: str, error_code: str = "UNKNOWN_ERROR"):
        """
        初始化基础异常

        Args:
            message: 异常信息描述
            error_code: 错误代码，用于识别异常类型
        """
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)

    def __str__(self):
        return f"[{self.error_code}] {self.message}"


class ConfigError(BaseAgentError):
    """
    配置异常类
    
    当配置文件读取、解析或验证失败时抛出，包括：
    - 配置文件不存在或格式错误
    - 必需的配置项缺失
    - 配置值类型或范围不合法
    """

    def __init__(self, message: str):
        """
        初始化配置异常

        Args:
            message: 异常信息描述
        """
        super().__init__(message, error_code="CONFIG_ERROR")


class BrowserError(BaseAgentError):
    """
    浏览器控制异常类
    
    当Chrome控制、页面操作或会话管理失败时抛出，包括：
    - 浏览器无法启动或连接
    - 页面导航超时
    - DOM操作失败
    - 文件上传失败
    """

    def __init__(self, message: str):
        """
        初始化浏览器异常

        Args:
            message: 异常信息描述
        """
        super().__init__(message, error_code="BROWSER_ERROR")


class PerceptionError(BaseAgentError):
    """
    感知模块异常类
    
    当页面感知、理解或分析失败时抛出，包括：
    - DOM解析失败
    - 视觉模型调用失败
    - 页面内容提取失败
    - 元素识别失败
    """

    def __init__(self, message: str):
        """
        初始化感知异常

        Args:
            message: 异常信息描述
        """
        super().__init__(message, error_code="PERCEPTION_ERROR")


class LLMError(BaseAgentError):
    """
    大语言模型异常类
    
    当LLM或VLM API调用、响应解析或决策失败时抛出，包括：
    - API请求失败
    - 令牌限制超出
    - 响应格式不合法
    - 模型无法处理输入
    """

    def __init__(self, message: str):
        """
        初始化LLM异常

        Args:
            message: 异常信息描述
        """
        super().__init__(message, error_code="LLM_ERROR")
