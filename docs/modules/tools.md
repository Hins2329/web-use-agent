# Tools Module (本地工具模块)

## 模块定位
`agent/tools` 是系统的本地能力扩展层，负责执行非浏览器范畴的本地 OS 操作，与 `agent/execution` 浏览器执行层形成物理隔离和职责分离。

## 核心职责

### 负责范围
- 执行本地文件系统操作（读取、写入、列表、删除等）
- 处理本地数据文件（JSON、TXT、CSV 等格式）
- 返回标准化的 `ActionResult` 格式
- 验证文件路径和处理文件系统错误
- 提供本地环境与智能体的交互能力

### 明确禁止事项
- **绝对禁止**操作 Playwright 句柄或浏览器对象
- **绝对禁止**直接修改 DOM 元素
- **绝对禁止**跨界调用 `perception` 模块
- **绝对禁止**执行浏览器相关动作（click、type、navigate 等）
- **绝对禁止**访问 `execution` 模块的内部状态

## 数据接口

### 输入格式：标准 Action 对象

```json
{
  "action": "read_file",
  "target": {},
  "input": {
    "file_path": "/path/to/file.json"
  },
  "options": {}
}
```

**字段说明：**
- `action`: 动作类型，必须是工具类动作（如 `read_file`）
- `target`: 目标对象，对于文件操作通常为空字典
- `input`: 输入参数，包含操作所需的具体参数
  - `file_path`: 文件的绝对或相对路径（必需）
- `options`: 可选配置参数

### 输出格式：标准 ActionResult

```json
{
  "success": true,
  "message": "File read successfully: /path/to/file.json",
  "data": {
    "file_content": {
      "file_path": "/path/to/file.json",
      "content": "...",
      "encoding": "utf-8",
      "size_bytes": 1024,
      "file_type": "json"
    }
  }
}
```

**字段说明：**
- `success`: 布尔值，表示操作是否成功
- `message`: 人类可读的结果消息
- `data`: 操作结果数据（成功时包含文件内容等信息）

### 错误响应示例

```json
{
  "success": false,
  "message": "File not found: /invalid/path.txt",
  "data": {}
}
```

## 支持的动作类型

### 当前支持

#### 1. read_file - 读取本地文件

**用途：** 读取本地文件内容并返回

**输入参数：**
- `file_path` (必需): 文件路径字符串

**返回数据：**
- `file_content`: FileContent 对象，包含文件路径、内容、编码、大小、类型

**错误处理：**
- 文件不存在 → `FileNotFoundError`
- 权限不足 → `PermissionError`
- 编码错误 → `DecodingError`

**示例：**
```json
{
  "action": "read_file",
  "target": {},
  "input": {"file_path": "/data/products.json"},
  "options": {}
}
```

### 未来扩展

#### 2. write_file - 写入本地文件

**用途：** 将内容写入本地文件

**输入参数：**
- `file_path` (必需): 目标文件路径
- `content` (必需): 要写入的内容
- `encoding` (可选): 文件编码，默认 utf-8
- `overwrite` (可选): 是否覆盖已存在文件，默认 false

#### 3. list_directory - 列出目录内容

**用途：** 列出指定目录下的文件和子目录

**输入参数：**
- `directory_path` (必需): 目录路径
- `recursive` (可选): 是否递归列出，默认 false
- `filter_pattern` (可选): 文件名过滤模式（如 "*.json"）

#### 4. delete_file - 删除文件

**用途：** 删除指定的本地文件

**输入参数：**
- `file_path` (必需): 要删除的文件路径
- `confirm` (必需): 确认标志，必须为 true

## 架构位置

### 在系统中的位置

```
perception -> workflow -> llm -> workflow -> [Action Router]
                                                  |
                                    +-------------+-------------+
                                    |                           |
                                    v                           v
                              execution                      tools
                              (浏览器操作)                  (本地操作)
                                    |                           |
                                    v                           v
                            Browser Controller            OS File System
```

### 与其他模块的关系

- **workflow**: 通过 Action Router 接收路由后的工具动作
- **execution**: 平行关系，互不依赖，各自处理不同领域的动作
- **perception**: 无直接交互，禁止跨界调用
- **llm**: 无直接交互，通过 workflow 间接协作

## 实现要点

### 文件路径验证

```python
def validate_file_path(file_path: str) -> bool:
    """验证文件路径的有效性"""
    # 1. 检查路径非空
    if not file_path:
        return False
    
    # 2. 检查文件存在
    if not os.path.exists(file_path):
        return False
    
    # 3. 检查是文件而非目录
    if os.path.isdir(file_path):
        return False
    
    # 4. 检查文件可读
    if not os.access(file_path, os.R_OK):
        return False
    
    return True
```

### 错误处理策略

1. **文件不存在**: 返回 `success=false`，提供清晰的错误消息
2. **权限不足**: 返回 `success=false`，建议用户检查权限
3. **编码错误**: 返回 `success=false`，建议用户检查文件格式
4. **未知错误**: 捕获所有异常，返回通用错误消息

### 安全考虑

1. **路径遍历防护**: 验证路径，防止 `../` 等目录遍历攻击
2. **文件大小限制**: 限制可读取的文件大小（建议 50MB 以内）
3. **文件类型白名单**: 仅允许安全的文件类型（txt、json、csv 等）
4. **访问日志**: 记录所有文件访问操作，用于审计

## 使用示例

### 示例 1: 读取产品数据文件

```python
# LLM 生成的动作
action = {
    "action": "read_file",
    "target": {},
    "input": {"file_path": "/Users/agent/data/products.json"},
    "options": {}
}

# Workflow 路由到 tools 模块
result = tools_executor.execute(action)

# 检查结果
if result["success"]:
    content = result["data"]["file_content"]["content"]
    products = json.loads(content)
    print(f"成功读取 {len(products)} 个产品")
else:
    print(f"读取失败: {result['message']}")
```

### 示例 2: 完整工作流（读取文件 + 网页操作）

```python
# 步骤 1: 读取本地文件（tools 模块）
action_1 = {
    "action": "read_file",
    "target": {},
    "input": {"file_path": "/data/products.json"},
    "options": {}
}
result_1 = workflow.route_and_execute(action_1)

# 步骤 2: 导航到上架页面（execution 模块）
action_2 = {
    "action": "navigate",
    "target": {},
    "input": {"url": "https://shop.example.com/upload"},
    "options": {}
}
result_2 = workflow.route_and_execute(action_2)

# 步骤 3: 填写产品信息（execution 模块）
action_3 = {
    "action": "type",
    "target": {"element_id": 1},
    "input": {"text": products[0]["name"]},
    "options": {}
}
result_3 = workflow.route_and_execute(action_3)
```

## 测试策略

### 单元测试

- 测试 `read_file()` 处理有效文件（JSON、TXT、CSV）
- 测试 `read_file()` 处理无效路径（不存在、目录、权限不足）
- 测试 `validate_file_path()` 的边界情况
- 测试 ActionResult 格式化的正确性
- 使用 mock 文件系统进行确定性测试

### 集成测试

- 测试 workflow 正确路由工具动作到 tools 模块
- 测试 tools 模块与 execution 模块的隔离性
- 测试混合动作序列（工具动作 + 浏览器动作）
- 测试错误在模块边界的传播

### 属性测试

- 文件路径验证的正确性（无假阳性）
- ActionResult 的结构完整性
- 模块隔离性（不访问 Playwright）

## 配置参数

```python
# config/tools_config.py
class ToolsConfig:
    # 文件大小限制（字节）
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    
    # 允许的文件扩展名
    ALLOWED_EXTENSIONS = ['.txt', '.json', '.csv', '.xml', '.yaml', '.yml']
    
    # 文件编码
    DEFAULT_ENCODING = 'utf-8'
    
    # 是否启用访问日志
    ENABLE_ACCESS_LOG = True
    
    # 文件操作超时（秒）
    FILE_OPERATION_TIMEOUT = 30
```

## 扩展指南

### 添加新的工具动作

1. 在 `ToolsExecutor` 中添加新的处理方法
2. 在 Action Router 的 `is_tool_action()` 中注册新动作类型
3. 更新 LLM 提示词，告知新动作的用法
4. 编写单元测试和集成测试
5. 更新本文档

### 示例：添加 write_file 动作

```python
class ToolsExecutor:
    def execute(self, action: Action) -> ActionResult:
        if action.action == "read_file":
            return self._read_file(action)
        elif action.action == "write_file":
            return self._write_file(action)  # 新增
        else:
            return ActionResult(
                success=False,
                message=f"Unknown tool action: {action.action}",
                data={}
            )
    
    def _write_file(self, action: Action) -> ActionResult:
        # 实现文件写入逻辑
        pass
```

## 版本历史

- **v1.0** (2026-04-25): 初始版本，支持 `read_file` 动作
- **v1.1** (计划中): 添加 `write_file`、`list_directory` 动作
- **v2.0** (计划中): 支持文件监控和自动触发
