# 数据协议总则
- 所有跨模块数据必须为显式 JSON/字典结构。
- 协议字段命名固定，不允许同义替换。
- 消费方按协议读取，生产方保证协议完整性。

# LLM 输出 JSON 标准格式
```json
{
  "thought": "string",
  "action": "string",
  "target": {},
  "input": {},
  "options": {},
  "confidence": 0.5,
  "state_update": {
    "complete_sub_goal": 0,
    "add_milestone": "string",
    "add_blocker": "string"
  }
}
```

约束：
- `thought`：字符串。
- `action`：字符串，小写动作码。
- `target`：对象。
- `input`：对象。
- `options`：对象。
- `confidence`：`0.0-1.0` 浮点（可选，缺省按解析器默认值处理）。
- `state_update`：对象（可选），用于更新 TaskState：
  - `complete_sub_goal`：整数（可选），完成的子目标索引。
  - `add_milestone`：字符串（可选），新增里程碑描述。
  - `add_blocker`：字符串（可选），新增阻塞项描述。

# Action 标准结构
```json
{
  "action": "click|type|navigate|scroll|wait|upload_file|select_option|human_intervene|done|read_file|write_file",
  "target": {},
  "input": {},
  "options": {}
}
```

**动作类型分类：**

**浏览器动作（Browser Actions）** - 路由到 `execution` 模块：
- `click`: 点击页面元素
- `type`: 在输入框中输入文本
- `navigate`: 导航到新 URL
- `scroll`: 滚动页面
- `wait`: 等待指定时间
- `upload_file`: 上传文件（需要操作 DOM 的 `<input type="file">` 元素，因此归属于浏览器执行层）
- `select_option`: 选择下拉选项
- `human_intervene`: 请求人工介入
- `done`: 任务完成

**本地工具动作（Tool Actions）** - 路由到 `tools` 模块：
- `read_file`: 读取本地文件内容
- `write_file`: 写入内容到本地文件（未来扩展）

**重要说明：**
- `upload_file` 虽然涉及文件，但因为需要操作 DOM 元素（`<input type="file">`），所以归属于 `execution` 模块
- `read_file` 仅读取本地文件系统，不涉及浏览器操作，归属于 `tools` 模块

执行返回：
```json
{
  "success": true,
  "message": "string",
  "data": {}
}
```

# PageSchema 结构规范
```json
{
  "url": "string",
  "title": "string",
  "summary": "string",
  "page_type": "string",
  "elements": [
    {
      "id": 1,
      "element_id": 1,
      "type": "string",
      "text": "string",
      "interactable": true,
      "role": "string",
      "title": "string|null",
      "placeholder": "string|null",
      "attributes": {}
    }
  ]
}
```

- `elements` 列表现在通过 SoM 提取，仅包含当前视口内可见的交互元素，以实现极致 Token 压缩（通常 < 3K）。
- 感知层必须同时输出 `vlm_hints` 字段，用于携带带标号的 SoM 截图路径和视觉补充信息。
- `ElementRegistry` 除了注册 selector，还必须同步存储 `center_x` 和 `center_y` 坐标。

# Skill 数据结构规范
```json
{
  "skill_id": "string (唯一标识符)",
  "intent_description": "string (意图描述，用于语义检索)",
  "guidance_sop": "string (通用指导规则，去具体化的 SOP 文本)",
  "created_at": "string (ISO 8601 时间戳)",
  "success_count": "int (成功复用次数)"
}
```

约束：
- `skill_id`：全局唯一，建议使用 UUID 或语义化命名。
- `intent_description`：用于意图匹配的自然语言描述，不包含特定 `element_id` 或页面细节。
- `guidance_sop`：提炼后的通用操作指导，必须去除具体的选择器、坐标、元素 ID 等实例化信息。
- `created_at`：技能创建时间，用于版本管理与过期淘汰。
- `success_count`：技能被成功复用的次数，用于质量评估与优先级排序。

# 失败模式数据结构规范
```json
{
  "pattern_id": "string (唯一标识符)",
  "goal": "string (失败任务的目标)",
  "failure_summary": "string (失败特征描述)",
  "suggestion": "string (规避建议)",
  "created_at": "string (ISO 8601 时间戳)"
}
```

约束：
- `pattern_id`：全局唯一，建议使用 UUID。
- `goal`：失败任务的原始目标，用于语义检索匹配。
- `failure_summary`：失败特征的自然语言描述，提炼失败的根本原因。
- `suggestion`：规避建议，指导 Agent 如何避免重复相同错误。
- `created_at`：失败模式创建时间，用于版本管理。

# TaskState 数据结构规范
```json
{
  "task_id": "string (任务唯一标识符)",
  "goal": "string (任务目标)",
  "sub_goals": [
    {
      "description": "string (子目标描述)",
      "status": "pending|in_progress|completed"
    }
  ],
  "milestones": ["string (里程碑描述)"],
  "blockers": ["string (阻塞项描述)"],
  "step_count": "int (当前步数)"
}
```

约束：
- `task_id`：任务唯一标识符，预留用于多轮对话 TaskStack。
- `goal`：任务的原始目标描述。
- `sub_goals`：子目标列表，每个子目标包含描述和状态。
- `milestones`：已完成的里程碑列表。
- `blockers`：当前遇到的阻塞项列表。
- `step_count`：当前执行的步数。
- **不可压缩原则**：TaskState 对象在任何上下文压缩操作中绝对禁止截断或丢弃。

# ActionHistory 记录结构规范
```json
{
  "decision": {
    "thought": "string",
    "action": "string",
    "target": {},
    "input": {},
    "options": {}
  },
  "result": {
    "success": "bool",
    "message": "string",
    "data": {}
  },
  "tag": "MILESTONE|NORMAL|ERROR"
}
```

约束：
- `decision`：LLM 的决策内容。
- `result`：动作执行结果。
- `tag`：动作标签，用于上下文压缩时的优先级判断：
  - `MILESTONE`：URL 变化、子目标完成等关键步骤，永不丢弃。
  - `NORMAL`：普通动作，超出窗口后可压缩为摘要。
  - `ERROR`：失败动作，只保留最近3条。
- **tag 优先级严格互斥**：ERROR > MILESTONE > NORMAL（禁止用两个独立 if 判断导致覆盖）。

# 死循环监控规范
## 滑动窗口配置
- **Window Size**: 6（监控最近 6 步动作）
- **Action Signature**: `action` + 核心参数（如 `element_id`、`url`、`file_path`）
- **Cognitive State**: 认知状态分类（Gathering / Interacting / Navigating）

## 熵计算指标
### Action Entropy（动作熵）
- 定义：滑动窗口内 Action Signature 的信息熵。
- 计算：`H(A) = -Σ p(a) * log2(p(a))`，其中 `p(a)` 为动作签名 `a` 的出现频率。
- 阈值：`H(A) < 0.5` 视为动作单一化（可能陷入循环）。

### State Entropy（状态熵）
- 定义：滑动窗口内 Cognitive State 的信息熵。
- 计算：`H(S) = -Σ p(s) * log2(p(s))`，其中 `p(s)` 为认知状态 `s` 的出现频率。
- 阈值：`H(S) < 0.3` 视为状态固化（可能陷入循环）。

### Oscillation Score（震荡分数）
- 定义：检测 A-B-A-B 模式的震荡行为。
- 计算：统计窗口内相邻动作对 `(a_i, a_{i+1})` 的反向重复次数。
- 阈值：`Oscillation Score >= 2` 视为震荡循环（如反复点击同一元素）。

## 熔断处置规则
当满足以下任一条件时触发熔断：
1. `Action Entropy < 0.5` 且 `State Entropy < 0.3`
2. `Oscillation Score >= 2`

**熔断行为**：
- 不抛出异常，不终止任务。
- 强制中断当前动作执行（跳过本轮 `execution` 或 `tools` 调用）。
- 将血红警告追加至 LLM 下一轮的 Context 中：
  ```
  ⚠️ 【死循环警告】你已陷入循环模式！
  - 动作熵: {action_entropy:.2f} (阈值: 0.5)
  - 状态熵: {state_entropy:.2f} (阈值: 0.3)
  - 震荡分数: {oscillation_score} (阈值: 2)
  - 最近 6 步动作: {action_signatures}
  
  请立即改变策略：尝试不同的动作、切换页面、或请求人工介入。
  ```

# 错误处理规范
- 协议解析失败：返回安全默认决策（`action=wait`）并标记错误字段。
- 模块内部错误：抛出对应异常类型（`PerceptionError`、`LLMError`、`BrowserError`、`ConfigError`）。
- 工作流错误：统一折叠到任务结果结构中的失败状态与错误信息。

# 模块必须遵守的数据协议
- `perception` 输出必须可直接序列化并可被 `llm` 消费。
- `llm` 输出必须满足 Action 协议所需字段。
- `execution` 仅消费浏览器相关的标准 `Action`，不接受隐式字段推断。
- `tools` 仅消费本地工具相关的标准 `Action`，不接受隐式字段推断。
- `workflow` 仅转发与调度，不改写协议字段和值。
- `workflow` 负责根据 `action` 类型路由到正确的执行模块（`execution` 或 `tools`）。
