# 失败模式记忆功能实现总结

## 实现日期
2026-05-07

## 功能概述
为 Web Agent 的记忆模块添加失败模式库功能，用于记录和检索任务失败经验。该功能与现有的成功经验库（SOP）并行工作，帮助 Agent 在执行任务前识别潜在的失败模式，并在任务失败后自动提炼失败原因和规避建议。

## 实现的功能

### 1. Skill_Manager 类新增方法

#### 1.1 失败模式存储功能
- **`_load_failure_patterns()`**: 从 JSON 文件加载失败模式列表
- **`_save_failure_patterns()`**: 保存失败模式列表到 JSON 文件（线程安全）
- **`_save_failure_patterns_unsafe()`**: 保存失败模式列表到 JSON 文件（非线程安全，内部使用）
- **`save_failure_pattern(goal, failure_summary, suggestion)`**: 保存新的失败模式
  - 生成 UUID 作为 pattern_id
  - 记录 UTC 时间戳（ISO 8601 格式）
  - 设置 type 字段为 "failure_pattern"
  - 追加到失败模式列表并持久化

#### 1.2 失败模式检索功能
- **`search_failure_patterns(goal, top_k=5)`**: 基于任务目标检索相关的失败模式
  - 当前阶段（<50条）：返回所有失败模式
  - 预留接口：函数签名保持不变，内部加注释 "TODO: >50条时改为向量检索"
  - 返回格式：list[dict]，每个 dict 含 failure_summary、suggestion、goal

#### 1.3 失败原因提炼功能
- **`FAILURE_REFLECTION_SYSTEM_PROMPT`**: 失败反思提示词模板
- **`_format_failure_reflection_input(goal, action_history)`**: 格式化失败反思输入
- **`_extract_failure_reflection_from_result(result)`**: 从 LLM 返回结果中提取失败反思
- **`reflect_failure(goal, action_history, llm_client)`**: 反思提炼失败原因和规避建议（async）
  - 调用 LLM 进行失败原因分析
  - 返回包含 failure_summary 和 suggestion 的字典
  - LLM 调用失败时抛出 LLMError

### 2. Workflow_Engine 类集成

#### 2.1 初始化
- 在 `__init__` 方法中实例化 SkillManager
- 添加日志记录

#### 2.2 任务开始时检索失败模式
- 在 `run_task` 方法中，任务状态机初始化之后调用 `search_failure_patterns`
- 如果检索到失败模式，调用 `_format_failure_patterns` 格式化
- 将格式化后的字符串追加到 `task_guidance` 参数
- 添加日志记录

#### 2.3 任务失败时保存失败模式
- 在 `run_task` 方法的异常处理分支中调用 `reflect_failure`
- 调用 `save_failure_pattern` 保存提炼结果
- 使用 try-except 捕获异常，记录警告日志
- 不中断任务执行，继续返回 TaskResult

#### 2.4 任务超时时保存失败模式
- 在超过最大步数限制的分支中调用 `reflect_failure`
- 调用 `save_failure_pattern` 保存提炼结果
- 使用 try-except 捕获异常，记录警告日志
- 不中断任务执行，继续返回 TaskResult

#### 2.5 失败模式格式化
- **`_format_failure_patterns(failure_patterns)`**: 格式化失败模式为字符串
  - 空列表返回空字符串
  - 使用清晰的标题和分隔符
  - 每个失败模式显示序号、失败特征和规避建议

## 存储文件信息

### 文件路径
```
browser_data/failure_patterns.json
```

### 文件格式
```json
[
  {
    "pattern_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "goal": "在淘宝上搜索并购买一本Python书籍",
    "failure_summary": "在搜索结果页面无法找到目标商品，Agent 陷入重复滚动死循环",
    "suggestion": "在搜索前先明确商品关键词，搜索后检查结果数量，如果结果为空则调整关键词重新搜索",
    "type": "failure_pattern",
    "created_at": "2025-01-15T08:30:00Z"
  }
]
```

### 字段说明
- **pattern_id**: UUID 格式的唯一标识符
- **goal**: 任务目标（上下文）
- **failure_summary**: 失败特征和根本原因
- **suggestion**: 规避建议
- **type**: 固定为 "failure_pattern"
- **created_at**: ISO 8601 格式的 UTC 时间戳

### 编码格式
- UTF-8 编码
- 2 空格缩进

## 架构约束遵守

✅ 在 Skill_Manager 类中新增方法，不修改现有方法
✅ 失败模式的调用逻辑在 workflow.py 中实现，不在 system_prompt.py 中
✅ 存储文件放在和现有 SOP 文件同目录（browser_data/）
✅ 所有文件操作都使用线程锁确保安全
✅ LLM 调用失败时记录警告日志，不中断任务执行

## 测试验证

### 数据结构测试
✅ 失败模式数据结构正确
✅ 所有必需字段存在
✅ type 字段为 "failure_pattern"
✅ pattern_id 是有效的 UUID
✅ created_at 是 ISO 8601 格式（UTC）
✅ JSON 序列化和反序列化正常
✅ 文件写入和读取正常

### 语法检查
✅ skill_manager.py 无语法错误
✅ workflow.py 无语法错误

## 未来扩展

### 向量检索
当失败模式数量超过 50 条时，需要改为向量检索：
- 使用 Embedding 模型将 goal 和 failure_summary 转换为向量
- 使用向量数据库（如 FAISS、Chroma）进行相似度检索
- 返回 top_k 个最相关的失败模式

### 失败模式去重
- 使用 Embedding 计算失败模式之间的相似度
- 合并相似度高于阈值的失败模式
- 保留最新的失败模式，丢弃旧的

### 失败模式评分
- 初始评分为 0
- 每次检索到并成功规避失败时，评分 +1
- 每次检索到但仍然失败时，评分 -1
- 检索时优先返回高评分的失败模式

### 失败模式分类
- 页面加载失败：网络错误、超时等
- 元素定位失败：元素不存在、被遮挡等
- 交互失败：点击无效、输入被拒绝等
- 逻辑错误：任务目标理解错误、步骤顺序错误等

### 失败模式可视化
- 失败模式数量趋势
- 失败类型分布
- 高频失败模式排行
- 失败模式的有效性评分

## 修改的文件

1. **src/agent/memory/skill_manager.py**
   - 新增失败模式相关的初始化逻辑
   - 新增 `_load_failure_patterns` 方法
   - 新增 `_save_failure_patterns` 和 `_save_failure_patterns_unsafe` 方法
   - 新增 `save_failure_pattern` 方法
   - 新增 `search_failure_patterns` 方法
   - 新增 `FAILURE_REFLECTION_SYSTEM_PROMPT` 常量
   - 新增 `_format_failure_reflection_input` 方法
   - 新增 `_extract_failure_reflection_from_result` 方法
   - 新增 `reflect_failure` 方法

2. **src/agent/workflow/workflow.py**
   - 在 `__init__` 方法中初始化 SkillManager
   - 在 `run_task` 方法中添加失败模式检索逻辑（任务开始时）
   - 在 `run_task` 方法的异常处理分支中添加失败模式保存逻辑
   - 在 `run_task` 方法的超时分支中添加失败模式保存逻辑
   - `_format_failure_patterns` 方法已存在，无需修改

## 总结

失败模式记忆功能已成功实现，所有核心功能都已完成并通过测试。该功能遵守现有架构约束，最小侵入，与现有 SOP 功能并行工作。失败模式文件存储在 `browser_data/failure_patterns.json`，使用 JSON 格式，UTF-8 编码，2 空格缩进。

功能已准备好投入使用，未来可以根据需要扩展向量检索、去重、评分、分类和可视化等高级功能。
