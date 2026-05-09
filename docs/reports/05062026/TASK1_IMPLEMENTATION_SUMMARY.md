# Task 1 实现总结：TaskState 任务状态机

## 完成时间
2026-05-06

## 修改的文件

### 1. **新建文件：`src/agent/memory/task_state.py`**
实现了完整的任务状态机模块，包括：

#### 核心数据类
- **`SubGoal`**: 子目标数据类
  - `description`: 子目标描述
  - `status`: 状态（"pending" / "completed" / "blocked"）
  - `to_dict()`: 转换为字典
  - `from_dict()`: 从字典创建实例

- **`TaskState`**: 任务状态数据类
  - `task_id`: 任务唯一标识（当前固定为 "task_1"）
  - `goal`: 用户原始目标（永不修改）
  - `sub_goals`: 子目标列表
  - `milestones`: 已完成的关键里程碑列表
  - `blockers`: 当前阻塞项列表
  - `step_count`: 已执行步数

#### 核心方法
- `to_dict()` / `from_dict()`: 字典序列化/反序列化
- `to_json()`: JSON 序列化
- **`serialize_for_prompt()`**: 序列化为适合注入 LLM prompt 的文本格式
- **`update_from_llm_response()`**: 根据 LLM 返回的 state_update 更新状态
- `increment_step()`: 增加步数计数

### 2. **修改文件：`src/agent/workflow/workflow.py`**

#### 新增导入
```python
from ..memory.task_state import TaskState, SubGoal
```

#### 新增实例变量
```python
self.task_state: Optional[TaskState] = None
```

#### 新增方法：`_initialize_task_state()`
- 在任务开始时调用 LLM 生成初始子目标列表
- 使用专门的 prompt 让 LLM 将用户目标分解为 3-5 个子目标
- 创建并返回初始化的 TaskState 对象
- 包含降级处理：如果 LLM 调用失败，创建默认子目标

#### 修改 `run_task()` 方法
1. **任务开始时初始化 TaskState**：
   ```python
   self.task_state = await self._initialize_task_state(goal)
   ```

2. **ReAct 循环中更新步数**：
   ```python
   if self.task_state:
       self.task_state.increment_step()
   ```

3. **处理 LLM 返回的 state_update**：
   ```python
   if self.task_state and "state_update" in decision:
       state_update = decision.get("state_update")
       if state_update:
           self.task_state.update_from_llm_response(state_update)
   ```

#### 修改 `_reasoning()` 方法
- 在构建 system_prompt 时注入 TaskState：
  ```python
  if self.task_state:
      task_state_str = self.task_state.serialize_for_prompt()
      system_prompt += f"\n\n{task_state_str}"
  ```

### 3. **修改文件：`prompts/system_prompt.py`**

#### 扩展 JSON Schema
在返回格式中新增 `state_update` 字段：
```json
{
    "thought": "...",
    "action": "...",
    "target": {...},
    "input": {...},
    "options": {...},
    "state_update": {
        "complete_sub_goal": 0,
        "add_sub_goal": "新子目标描述",
        "add_milestone": "里程碑描述",
        "add_blocker": "阻塞项描述",
        "remove_blocker": "要移除的阻塞项",
        "block_sub_goal": 0
    }
}
```

#### 新增使用说明
- 详细说明了 state_update 各字段的用途
- 新增了包含 state_update 的示例

## TaskState 序列化格式

### 注入到 LLM Prompt 的文本格式
```
【任务状态】
任务ID: task_1
目标: 在淘宝上搜索并购买Python书籍
已执行步数: 3

子目标进度:
  1. [⏳] 打开淘宝首页 (pending)
  2. [✓] 在搜索框输入'Python书籍' (completed)
  3. [⏳] 浏览搜索结果并选择合适的商品 (pending)
  4. [⏳] 加入购物车并完成支付 (pending)

已完成的里程碑:
  ✓ 已输入搜索关键词
  ✓ 搜索结果已加载

当前阻塞项: （无）
```

### JSON 格式（用于序列化/持久化）
```json
{
    "task_id": "task_1",
    "goal": "在淘宝上搜索并购买Python书籍",
    "sub_goals": [
        {
            "description": "打开淘宝首页",
            "status": "pending"
        },
        {
            "description": "在搜索框输入'Python书籍'",
            "status": "completed"
        },
        {
            "description": "浏览搜索结果并选择合适的商品",
            "status": "pending"
        },
        {
            "description": "加入购物车并完成支付",
            "status": "pending"
        }
    ],
    "milestones": [
        "已输入搜索关键词",
        "搜索结果已加载"
    ],
    "blockers": [],
    "step_count": 3
}
```

## LLM 返回的 state_update 示例

### 示例 1：完成子目标并添加里程碑
```json
{
    "thought": "我已经成功输入了搜索关键词，完成了第二个子目标",
    "action": "click",
    "target": {"element_id": 10},
    "input": {},
    "options": {},
    "state_update": {
        "complete_sub_goal": 1,
        "add_milestone": "已输入搜索关键词"
    }
}
```

### 示例 2：遇到阻塞
```json
{
    "thought": "遇到了验证码，需要人工介入",
    "action": "human_intervene",
    "target": {},
    "input": {"reason": "需要完成验证码验证"},
    "options": {},
    "state_update": {
        "add_blocker": "需要完成验证码验证",
        "block_sub_goal": 2
    }
}
```

### 示例 3：解决阻塞并继续
```json
{
    "thought": "验证码已完成，可以继续了",
    "action": "click",
    "target": {"element_id": 15},
    "input": {},
    "options": {},
    "state_update": {
        "remove_blocker": "需要完成验证码验证",
        "add_milestone": "验证码验证完成"
    }
}
```

### 示例 4：动态添加新子目标
```json
{
    "thought": "发现需要先登录才能继续，添加一个新的子目标",
    "action": "click",
    "target": {"element_id": 5},
    "input": {},
    "options": {},
    "state_update": {
        "add_sub_goal": "完成用户登录"
    }
}
```

## 架构遵守情况

### ✅ 严守的架构铁律
1. **ActionResult 契约**：所有执行结果仍然返回标准格式 `{"success": bool, "message": str, "data": dict}`
2. **LLM 模块隔离**：TaskState 由 workflow 通过参数注入到 LLM，LLM 模块不直接引入 TaskState
3. **底座纯洁性**：TaskState 是通用的任务状态机，不包含任何业务特化逻辑

### 🔒 上下文压缩预留
在 TaskState 类的文档字符串中明确标注：
> TaskState 是 Agent 的工作记忆核心，在上下文压缩时永不丢弃。

在 `_reasoning()` 方法中添加了占位注释，为未来的 ContextManager 集成预留接口。

## 测试建议

### 单元测试
1. 测试 `SubGoal` 和 `TaskState` 的序列化/反序列化
2. 测试 `update_from_llm_response()` 的各种更新操作
3. 测试 `serialize_for_prompt()` 的输出格式

### 集成测试
1. 测试 `_initialize_task_state()` 能否正确生成子目标
2. 测试 ReAct 循环中 TaskState 的更新流程
3. 测试 state_update 字段的解析和应用

### 端到端测试
运行一个完整的任务，验证：
1. 任务开始时能否生成合理的子目标
2. 执行过程中 TaskState 是否正确更新
3. 日志中是否能看到 TaskState 的变化

## 下一步工作

根据 `docs/CURRENT.md` 的规划，接下来应该实现：

### Task 2 - 动作 MILESTONE 标签
- 为 action_history 添加 tag 字段
- URL 变化时自动打 MILESTONE 标签
- 依赖 Task 1（已完成）

### Task 3 - ContextManager 上下文压缩
- 监控 token 用量
- 按优先级压缩：System > TaskState > MILESTONE > SOP摘要 > 普通动作
- 依赖 Task 1 和 Task 2

## 备注

- TaskState 的 `task_id` 字段当前固定为 "task_1"，为未来的多轮对话 TaskStack（Task 6）预留
- 所有修改都遵循了现有的代码风格和架构约定
- 新增的日志使用了与现有代码一致的格式和级别
