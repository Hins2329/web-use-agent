"""
应用程序配置管理

使用 pydantic-settings 实现配置的统一管理，支持：
- YAML 配置文件加载
- .env 环境变量加载
- 环境变量覆盖配置文件
- 配置验证和类型检查
"""


from dotenv import load_dotenv
from pathlib import Path
import os

# 使用绝对路径加载 .env 文件
env_file = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_file, override=True)
from typing import Optional, Tuple
from dataclasses import dataclass, field

try:
    import yaml
except ImportError:
    yaml = None

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


@dataclass
class LLMConfig:
    """
    大语言模型配置
    
    定义 LLM 的提供者、模型、API 密钥等信息。
    支持 'zhipu'、'openai'、'claude' 等提供者。
    """

    mode: str = "auto"
    """LLM 模式: auto (自动路径) 或 manual (手动输入路径)"""
    provider: str = "zhipu"
    """模型提供者: zhipu, openai, claude"""
    model: str = "glm-4.7-flash"
    """模型名称 - 最新免费版本"""
    api_key: str = ""
    """API 密钥"""
    base_url: str = ""
    """API 基础 URL，为空时由各 Provider 自行兜底"""
    temperature: float = 0.1
    """采样温度 (0-1)，越小越确定"""
    max_tokens: int = 4000
    """最大生成令牌数"""
    compressor_model: str = ""
    """上下文压缩使用的模型，为空时使用主模型"""


@dataclass
class VLMConfig:
    """
    视觉语言模型配置
    
    定义 VLM 的提供者、模型、API 密钥等信息。
    用于页面截图分析和视觉理解任务。
    """

    provider: str = "zhipu"
    """模型提供者: zhipu, openai, openrouter, claude"""
    model: str = "glm-4.6v-flash"
    """模型名称 - 最新免费视觉版本"""
    api_key: str = ""
    """API 密钥"""
    base_url: str = ""
    """API 基础 URL，为空时由各 Provider 自行兜底"""
    max_image_size: int = 1024
    """图片压缩尺寸"""
    mode: str = "auto"
    """VLM 模式: auto (调用 API) 或 manual (手动输入)"""
    screenshot_dir: str = "./screenshots"
    """截图保存目录"""


@dataclass
class UnifiedModelConfig:
    """
    统一模型配置
    
    如果使用支持多模态和工具调用的单一模型（如 GLM-4.6V-Flash），
    可使用此配置同时处理文本和视觉任务。
    """

    provider: str = "zhipu"
    """模型提供者"""
    model: str = "glm-4.6v-flash"
    """模型名称 - 最新免费视觉版本"""
    api_key: str = ""
    """API 密钥"""
    use_for_both: bool = True
    """是否同时用于 LLM 和 VLM 任务"""
    base_url: str = ""
    """API 基础 URL，为空时由各 Provider 自行兜底"""


@dataclass
class CostControlConfig:
    """
    成本控制配置
    
    用于限制 API 调用成本的配置，包括令牌限制和速率限制。
    """

    max_tokens_per_request: int = 4000
    """单次请求最大令牌数"""
    daily_token_limit: int = 100000
    """每日总令牌限制"""
    vlm_requests_per_minute: int = 20
    """VLM 每分钟最大请求数"""
    enable_token_tracking: bool = True
    """是否启用令牌追踪"""


@dataclass
class BrowserConfig:
    """
    浏览器配置
    
    控制 Chrome 浏览器的行为和资源配置。
    """

    headless: bool = False
    """是否以无头模式运行"""
    window_size: Tuple[int, int] = (1920, 1080)
    """浏览器窗口大小"""
    user_data_dir: str = "./browser_data"
    """用户数据目录路径"""
    executable_path: Optional[str] = None
    """Chrome 执行文件路径，如果为空则自动查找"""
    keep_open: bool = False
    """任务完成后是否保持浏览器不关闭（仅断开连接）"""
    page_load_timeout: int = 30000
    """页面加载超时时间（毫秒），超时继续而不是中止"""


@dataclass
class PerceptionConfig:
    """
    感知层配置
    
    控制页面感知和理解的行为。
    """

    cache_enabled: bool = True
    """是否启用缓存"""
    cache_ttl: int = 300
    """缓存 TTL（秒）"""
    dom_priority: bool = True
    """是否优先使用 DOM 解析而不是 VLM"""


@dataclass
class AgentConfig:
    """
    Agent 执行配置
    
    控制 Agent 的执行行为，包括步数限制和超时设置。
    """

    max_steps: int = 15
    """最大执行步数"""
    timeout: int = 60
    """执行超时时间（秒）"""
    retry_count: int = 3
    """失败重试次数"""
    fallback_enabled: bool = True
    """是否启用备用方案"""
    login_pause_duration: int = 30
    """登录页面暂停等待时间（秒），允许用户手动扫码"""


@dataclass
class LoggingConfig:
    """
    日志配置
    
    控制日志输出的级别和目标。
    """

    level: str = "INFO"
    """日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL"""
    file: str = "./logs/agent.log"
    """日志文件路径"""


class AppConfig(BaseSettings):
    """
    应用程序全局配置单例
    
    集中管理所有模块的配置，支持从多个源加载配置：
    1. 默认值
    2. config.yaml 配置文件
    3. .env 环境变量（优先级最高）
    
    环境变量可使用 __config__ 前缀来覆盖配置，例如：
    - LLM__PROVIDER=openai 覆盖 llm.provider
    - VLM__API_KEY=xxx 覆盖 vlm.api_key
    """

    # 模型配置
    llm: LLMConfig = Field(default_factory=LLMConfig)
    """LLM 配置"""
    vlm: VLMConfig = Field(default_factory=VLMConfig)
    """VLM 配置"""
    unified_model: Optional[UnifiedModelConfig] = None
    """统一模型配置（可选）"""

    # 其他配置
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    """浏览器配置"""
    perception: PerceptionConfig = Field(default_factory=PerceptionConfig)
    """感知层配置"""
    agent: AgentConfig = Field(default_factory=AgentConfig)
    """Agent 配置"""
    cost_control: CostControlConfig = Field(default_factory=CostControlConfig)
    """成本控制配置"""
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    """日志配置"""

    class Config:
        """Pydantic 配置"""

        case_sensitive = False
        """字段名大小写敏感"""
        env_nested_delimiter = "__"
        """环境变量嵌套分隔符，例如 LLM__PROVIDER"""
        env_file = ".env"
        """加载的 .env 文件路径"""
        extra = "ignore"
        """忽略额外的环境变量"""

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "AppConfig":
        """
        从 YAML 配置文件加载配置
        
        Args:
            yaml_path: YAML 文件的路径
        
        Returns:
            加载后的 AppConfig 实例
        
        Raises:
            ConfigError: 如果 YAML 文件无法加载或解析
        """
        from ..utils.exceptions import ConfigError

        if yaml is None:
            raise ConfigError(
                "PyYAML is not installed. Please install it with: pip install pyyaml"
            )

        yaml_file = Path(yaml_path)
        if not yaml_file.exists():
            raise ConfigError(f"Config file not found: {yaml_path}")

        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                config_dict = yaml.safe_load(f) or {}
        except Exception as e:
            raise ConfigError(f"Failed to load YAML config: {e}")

        # 转换 YAML 嵌套结构为 Pydantic 模型
        config_data = {}

        # 处理 llm 配置
        if "llm" in config_dict:
            config_data["llm"] = cls._parse_config_section(config_dict["llm"])

        # 处理 vlm 配置
        if "vlm" in config_dict:
            config_data["vlm"] = cls._parse_config_section(config_dict["vlm"])

        # 处理 unified_model 配置
        if "unified_model" in config_dict:
            config_data["unified_model"] = cls._parse_config_section(
                config_dict["unified_model"]
            )

        # 处理其他配置
        for key in ["browser", "perception", "agent", "cost_control", "logging"]:
            if key in config_dict:
                config_data[key] = cls._parse_config_section(config_dict[key])

        return cls(**config_data)

    @staticmethod
    def _parse_config_section(section: dict) -> dict:
        """
        解析配置段，处理环境变量替换
        
        Args:
            section: 配置段字典
        
        Returns:
            处理后的配置段字典
        """
        result = {}
        for key, value in section.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                # 替换 ${VAR_NAME} 格式的环境变量
                env_var = value[2:-1]
                result[key] = os.getenv(env_var, "")
            else:
                result[key] = value
        return result

    def __init__(self, **data):
        """
        初始化配置，自动加载 YAML 和环境变量
        """
        # 首先尝试从 config.yaml 加载
        config_yaml_path = Path("config.yaml")
        if config_yaml_path.exists():
            try:
                yaml_config = self.from_yaml(str(config_yaml_path))
                # 将 YAML 配置的值作为默认值，然后被 .env 覆盖
                data = {
                    **self._extract_dict_recursive(yaml_config),
                    **data,
                }
            except Exception:
                # 如果 YAML 加载失败，继续使用默认值
                pass

        super().__init__(**data)

        # 配置加载完成，不再在全局层面对任何特定厂商做 API Key 注入
        # 各 Provider 的 __init__ 会自行从环境变量兜底（如 ZHIPU_API_KEY、XIAOMI_API_KEY）
        pass

    @staticmethod
    def _extract_dict_recursive(obj: "AppConfig") -> dict:
        """
        递归提取配置对象的字典表示
        
        Args:
            obj: AppConfig 实例
        
        Returns:
            字典表示
        """
        result = {}
        for key, value in obj.__dict__.items():
            if isinstance(value, (LLMConfig, VLMConfig, BrowserConfig, PerceptionConfig, AgentConfig, CostControlConfig, LoggingConfig)):
                result[key] = value.__dict__
            else:
                result[key] = value
        return result


# 全局配置实例
_config_instance: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """
    获取全局配置实例（单例模式）
    
    Returns:
        AppConfig: 全局配置实例
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = AppConfig()
    return _config_instance


def reset_config() -> None:
    """
    重置全局配置实例（主要用于测试）
    """
    global _config_instance
    _config_instance = None
