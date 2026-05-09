# 通用 LLM 工厂架构使用指南

## 概述

通用工厂架构提供了一个统一的接口来访问多个 LLM 提供者（Zhipu、OpenAI、Claude 等），同时支持手动（Human-in-the-Loop）模式。

## 核心概念

### 对象模型

```
┌─────────────────────────────────────────┐
│          LLMFactory                      │
│  (通用工厂 - 单一入口)                    │
└──────────────┬──────────────────────────┘
               │
        ┌──────┴──────┐
        │             │ get_instance(role="logic"|"vision")
        │             │
        ▼             ▼
   ┌────────┐   ┌──────────┐
   │ Logic  │   │  Vision  │
   │ Model  │   │  Model   │
   └────────┘   └──────────┘
        │             │
        └──────┬──────┘
               │
     ┌─────────┴─────────┐
     │                   │
     ▼                   ▼
 ┌────────────┐      ┌──────────┐
 │ Zhipu GLM  │      │ OpenAI   │
 │ Claude     │      │ Manual   │
 │ ...        │      │ ...      │
 └────────────┘      └──────────┘
```

### 支持的提供者

| 提供者 | 推理模型 | 视觉模型 | 状态 |
|--------|---------|---------|------|
| **zhipu** | GLM-4.7-Flash | GLM-4.6V-Flash | ✅ 完全实现 |
| **manual** | 用户输入 | 用户输入 | ✅ 完全实现 |
| **openai** | gpt-4 | gpt-4-vision | ❌ Stub (待实现) |
| **claude** | claude-3 | claude-3-vision | ❌ Stub (待实现) |

---

## 使用方法

### 方式 1: 通过工厂直接获取（推荐）

```python
from src.agent.llm.factory import LLMFactory

# 获取推理模型（纯文本）
logic_client = LLMFactory.get_instance(role="logic")
response = await logic_client.chat(
    system_prompt="你是一个助手",
    user_input="请总结这段文本"
)

# 获取视觉模型（图像理解）
vision_client = LLMFactory.get_instance(role="vision")
response = await vision_client.chat_with_vision(
    system_prompt="你是一个视觉分析专家",
    user_input="分析这张图片",
    image_path="/path/to/image.png"
)
```

### 方式 2: 通过兼容性包装器（向后兼容）

```python
from src.agent.llm.llm_client import LLMClient

# 自动使用配置中指定的提供者
client = LLMClient()
response = await client.chat(
    system_prompt="...",
    user_input="..."
)
```

### 方式 3: 在应用中集成

```python
from src.agent.perception.engine import PerceptionEngine
from src.agent.workflow import AgentWorkflow

# PerceptionEngine 已自动使用工厂
engine = PerceptionEngine()

# Workflow 已自动使用工厂（通过 LLMClient）
workflow = AgentWorkflow()
```

---

## 配置管理

### 配置文件示例 (config.yaml)

```yaml
llm:
  provider: "zhipu"              # 推理提供者
  model: "glm-4.7-flash"
  api_key: "${ZHIPU_API_KEY}"
  temperature: 0.1
  max_tokens: 4000

vlm:
  provider: "zhipu"              # 视觉提供者
  mode: "auto"                   # "auto" 或 "manual"
  screenshot_dir: "./screenshots"
  api_key: "${ZHIPU_API_KEY}"
```

### 环境变量配置 (.env)

```bash
ZHIPU_API_KEY=sk_xxxxxxxxxxx
OPENAI_API_KEY=sk_xxxxxxxxxxx
CLAUDE_API_KEY=sk_xxxxxxxxxxx
```

---

## 响应格式

### chat() 方法的响应

```python
{
    "thought": "Agent 的思考过程",
    "action": {
        "action": "click",
        "target": {"element_id": "button_123"},
        "input": {}
    }
}
```

### chat_with_vision() 方法的响应

**自动模式（API）：**
```python
{
    "recommendation": "[页面信息]\n标题: ...\n...",
    "provider": "zhipu",
    "model": "glm-4.6v-flash"
}
```

**手动模式（用户输入）：**
```python
{
    "recommendation": "[页面信息]\n标题: ...\n...",
    "provider": "manual",
    "raw_response": {
        "user_input": "...",
        "screenshot_path": "/path/to/screenshot.png",
        "format_valid": True
    }
}
```

---

## 手动（Human-in-the-Loop）模式

### 工作流程

```
1. Agent 调用 VLM → ManualVLMClient.chat_with_vision()
   ↓
2. 自动截图并保存 → ./screenshots/step_01_20260410_134747.png
   ↓
3. 显示建议 Prompt（遵循 vlm_prompt.md 格式）
   ↓
4. 打开浏览器终端等待用户输入
   ↓
5. 用户在 Google AI Studio (Gemini) 中分析截图
   ↓
6. 用户复制分析结果并粘贴到终端
   ↓
7. 验证格式 → 返回用户输入
   ↓
8. Agent 继续执行（基于用户分析）
```

### VLM 响应格式标准（vlm_prompt.md）

ManualVLMClient 验证用户输入必须包含以下部分：

```
[页面信息]
标题: 页面标题
URL: 页面地址
类型: 页面类型
状态: 加载状态

[页面核心内容]
页面的主要内容描述

[可交互元素]
[按钮] "文本" | 位置: xxx | 状态: xxx
[输入框] "文本" | 位置: xxx | 状态: xxx
...

[特殊信息]
弹窗: 是否有弹窗
登录状态: 登录/未登录/未知
验证码: 是否有验证码
...
```

---

## 扩展：添加新提供者

### 步骤 1: 实现提供者类

在 `src/agent/providers/` 目录中创建新文件：

```python
# src/agent/providers/my_provider_client.py

from ..base import BaseLLMClient
from typing import Dict, Any

class MyProviderClient(BaseLLMClient):
    def __init__(self, api_key: str, base_url: str = ""):
        super().__init__(api_key, base_url, "my-model")
    
    async def chat(self, system_prompt: str, user_input: str, **kwargs) -> Dict[str, Any]:
        # 实现方法
        pass
    
    async def chat_with_vision(self, system_prompt: str, user_input: str, 
                                image_path: str, **kwargs) -> Dict[str, Any]:
        # 实现方法
        pass
```

### 步骤 2: 更新工厂配置

编辑 `src/agent/factory.py`，更新 `PROVIDER_MAP`：

```python
PROVIDER_MAP = {
    "manual": ("providers.manual_client", "ManualVLMClient"),
    "zhipu": ("providers.zhipu_client", "ZhipuClient"),
    "openai": ("providers.openai_client", "OpenAIClient"),
    "claude": ("providers.claude_client", "ClaudeClient"),
    "my_provider": ("providers.my_provider_client", "MyProviderClient"),  # 新增
}
```

### 步骤 3: 配置文件支持

在 `config.yaml` 中添加：

```yaml
llm:
  provider: "my_provider"
  api_key: "${MY_PROVIDER_API_KEY}"

vlm:
  provider: "my_provider"
  api_key: "${MY_PROVIDER_API_KEY}"
```

完成！新提供者现在可用了。

---

## 获取支持的提供者

```python
from src.agent.llm.factory import LLMFactory

providers = LLMFactory.get_supported_providers()
print(providers)  # ['manual', 'zhipu', 'openai', 'claude']
```

---

## 故障排除

### 问题 1: "无法创建 XXXX 客户端"

**原因:** API Key 未配置或无效

**解决方案:**
```bash
# 检查 .env 文件
cat .env | grep API_KEY

# 或在 config.yaml 中检查
grep api_key config.yaml
```

### 问题 2: "提供者模块中不存在类"

**原因:** PROVIDER_MAP 中的类名不正确

**解决方案:**
1. 检查提供者文件中的实际类名
2. 更新 PROVIDER_MAP 确保匹配

### 问题 3: 手动模式提示"VLM 返回格式可能不完全符合标准"

**原因:** 用户输入缺少必需的部分

**解决方案:**
1. 确保输入包含所有 4 个主要部分
2. 参考上面的 VLM 响应格式标准

---

## 最佳实践

✅ **推荐做法**

1. **使用工厂获取实例**
   ```python
   client = LLMFactory.get_instance(role="vision")
   ```

2. **定期检查支持的提供者**
   ```python
   if "openai" in LLMFactory.get_supported_providers():
       # 可以使用 OpenAI
   ```

3. **处理异常**
   ```python
   try:
       response = await vision_client.chat_with_vision(...)
   except LLMError as e:
       logger.error(f"VLM 调用失败: {e}")
   ```

4. **配置管理分离**
   - 生产环境：使用环境变量
   - 开发环境：使用 .env 文件
   - 测试环境：使用 manual 提供者

❌ **避免做法**

1. ❌ 直接导入具体客户端
   ```python
   # 不好
   from src.agent.llm.providers.zhipu_client import ZhipuClient
   client = ZhipuClient(api_key)
   
   # 好
   client = LLMFactory.get_instance(role="logic")
   ```

2. ❌ 在代码中硬编码 API Key
   ```python
   # 不好
   api_key = "sk_test_123456"
   
   # 好
   api_key = os.getenv("ZHIPU_API_KEY")
   ```

3. ❌ 忽略缓存机制
   ```python
   # 不好（创建重复隐患）
   client1 = LLMFactory.get_instance(role="logic")
   client2 = LLMFactory.get_instance(role="logic")
   
   # 好（使用相同实例）
   client = LLMFactory.get_instance(role="logic")
   ```

---

## 相关文档

- 📄 [vlm_prompt.md](../prompts/vlm_prompt.md) - VLM 响应格式规范
- 📄 [factory.py](../src/agent/factory.py) - 工厂实现源码
- 📄 [base.py](../src/agent/base.py) - 抽象基类定义
- 📄 [test_integrated_factory.py](test_integrated_factory.py) - 集成测试示例

---

## 更新历史

| 版本 | 日期 | 描述 |
|------|------|------|
| 1.0 | 2026-04-10 | 初始版本：完整工厂架构实现 |

---

## 贡献指南

新提供者贡献流程：

1. 在 `src/agent/providers/` 中实现新提供者
2. 在 `PROVIDER_MAP` 中注册
3. 为新提供者编写测试
4. 更新本文档
5. 提交 PR 以供审核

---

**更新于:** 2026-04-10
**维护者:** Agent Team
