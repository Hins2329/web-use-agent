# 模块划分
- `agent/workflow`：ReAct 编排与循环控制。
- `agent/perception`：DOM 解析、页面结构化、视觉兜底。
- `agent/llm`：推理接口层、模式切换、响应标准化入口。
- `agent/execution`：动作解释、选择器映射、浏览器动作执行。
- `agent/tools`：本地系统与扩展能力层（独立于 execution 浏览器执行层）。
- `agent/memory`：智能体的经验反思、技能提取与检索（Self-Learning 机制）。
- `agent/core`：核心占位包（统一核心域入口，不承载业务逻辑）。
- `agent/utils`：Agent 内部工具（协议解析等）。
- `utils`：全局通用能力（异常、日志）。
- `config`：配置加载与配置模型。

# 每层职责
## workflow
- 负责：调度 `perception`、`llm`、`execution`、`tools`，控制循环终止条件。
- 负责：根据动作类型路由到正确的执行模块（`execution` 或 `tools`）。
- 不负责：数据修复、协议补全、字段注入。

## perception
- 负责：输出页面结构化数据（`PageSchema`）并与执行映射同步。
- 负责：提供 SoM (Set-of-Mark) 画框感知与极致 DOM 剪枝，确保感知数据既视觉可读又轻量。
- 不负责：任务决策、动作执行。

## llm
- 负责：接收提示词并返回标准协议决策 JSON。
- 不负责：浏览器控制、页面抓取、本地文件操作。

## execution
- 负责：消费浏览器相关的 `Action`、维护 `ElementRegistry`、执行浏览器操作。
- 负责：执行层的坐标流降维打击，支持选择器优选与物理坐标兜底。
- 职责范围：专注于网页交互（click、type、navigate、scroll、upload_file 等）。
- 不负责：推理决策生成、页面结构解析、本地文件操作。

## tools
- 负责：消费本地工具相关的 `Action`、执行本地 OS 操作。
- 负责：读取本地文件、未来扩展本地文件写入等非浏览器操作。
- 职责范围：专注于本地环境交互（read_file、write_file、list_directory 等）。
- 不负责：浏览器控制、DOM 操作、页面感知。

## memory
- 负责：智能体的经验反思、技能提取与检索（Self-Learning 机制）。
- 负责：将成功任务的 `action_history` 总结为通用 Skill 并持久化到本地。
- 负责：基于新任务 `goal` 检索匹配的 Skill 并注入到 `workflow` 前置阶段。
- 负责：维护失败模式库（failure_patterns.json），任务失败时自动提炼保存，任务开始时检索注入 task_guidance。
- 负责：维护 TaskState 任务状态机（goal/子目标/里程碑/阻塞项），每步由 LLM 的 state_update 字段驱动更新。
- 负责：上下文压缩管理（ContextManager），token 用量超过阈值时按优先级重组。
- 不负责：参与网页执行或改变底座的 ReAct 轮转规则。
- 不负责：直接调用 `perception`、`execution` 或 `tools` 模块。

## core / utils
- 负责：公共基础能力与约束承载。
- 不负责：跨层业务拼装。

# 明确禁止事项
- `workflow` 禁止修改 `perception` 输出结构。
- `workflow` 禁止修复、补齐、重写 `llm` 决策字段。
- `workflow` 禁止引入解析与容错规则替代 `llm/utils` 协议层。
- `perception` 禁止直接调用 `execution` 或 `tools`。
- `execution` 禁止反向修改上游输入数据。
- `execution` 禁止操作本地文件系统。
- `tools` 禁止操作 Playwright 句柄或浏览器对象。
- `tools` 禁止直接修改 DOM 元素。
- `tools` 禁止跨界调用 `perception` 或 `execution`。
- `llm` 禁止输出非协议化结构给 `workflow`。
- `execution` 禁止生成非标准选择器语法（禁止 jQuery 伪类）。
- `memory` 禁止参与网页执行或改变底座的 ReAct 轮转规则。
- `memory` 禁止直接调用 `perception`、`execution` 或 `tools` 模块。

# 数据流规则（单向）
- 固定主链路：`memory 检索 -> perception -> workflow -> llm -> workflow -> [Action Router]`。
- 前置阶段：`run_agent` 启动时，`memory` 基于任务 `goal` 检索匹配的 Skill 并注入到 `workflow` 上下文。
- Action Router 根据动作类型分发：
  - 浏览器动作（click、type、navigate 等）→ `execution` 模块
  - 本地工具动作（read_file、write_file 等）→ `tools` 模块
- 后置阶段：任务成功完成后，`memory` 对 `action_history` 进行反思并提取通用 Skill 写入本地存储。
- 失败信号以异常/结果状态向上传递，不产生逆向数据回写。
- 各层只读取输入并产出新结果，不对上游对象做就地改写。
- `element_id` 的生命周期为单步 ReAct 级：每轮开始时强制清空会话映射，以应对 SPA 动态渲染。
- `perception` 输出的 `element_id` 必须是 `ElementRegistry` 已注册的持久化 ID。
- `workflow` 负责页面导航边界触发映射重置，不参与映射内容计算。
- `workflow` 引入基于滑动窗口的 Loop Monitor 机制，监控动作熵、状态熵与震荡分数，触发死循环阈值时强制熔断并注入纠偏警告。
- `execution` 和 `tools` 模块互不依赖，各自独立处理不同领域的动作。
- **`workflow` 引入懒感知机制**：本地工具调用后复用缓存的 `page_state` 和元素映射，绕过 `perception` 层的截图、DOM 解析和 SoM 标注，直接进入下一轮 LLM 推理。浏览器动作执行后、页面导航时、异常情况下，强制触发完整感知流程。
- **`workflow` 维护双轨数据流**：
  - `action_history`：记录每个动作的决策和执行结果（简洁版，不包含大数据），用于显示操作历史。每条记录包含 tag 字段（MILESTONE/NORMAL/ERROR），用于上下文压缩时的优先级判断。
  - `context_data`：持久化存储大数据（如文件内容），避免在操作历史中重复，减少 Token 消耗。
  - 对于 `read_file` 等本地工具，文件内容存储在 `context_data["read_file_results"]` 中，并在每轮推理时注入到 LLM 的 system_prompt。
  - **数据流闭环**：LLM 能看到完整的操作历史（动作类型 + 执行状态）和完整的文件内容，避免重复执行相同动作。
- **`workflow` 实现动作里程碑标签系统**：
  - 每条 action_history 记录包含 tag 字段（MILESTONE/NORMAL/ERROR）。
  - tag 优先级严格互斥：ERROR > MILESTONE > NORMAL。
  - MILESTONE 标签触发条件：URL 变化 OR 子目标完成（complete_sub_goal 不为 null）。
  - _format_action_history() 截取规则：MILESTONE 全部保留，ERROR 保留最近3条，NORMAL 保留最近5条。
- **`workflow` 实现感知层元素 Diff 机制**：
  - 缓存上一次元素ID集合（`_last_element_ids`）。
  - URL 未变且 `_browser_needs_update=False` 时，计算元素变化（新增/消失）。
  - 元素无变化时输出简短提示："[页面状态未变化，请基于上次感知继续决策]"。
  - 元素有变化时只输出 diff（新增元素 + 消失元素），而非全量元素列表。
  - URL 变化时强制全量输出，清空 `_last_element_ids` 缓存。
- **`memory` 维护 TaskState 不可压缩原则**：
  - TaskState 对象在任何上下文压缩操作中绝对禁止截断或丢弃。
  - MILESTONE 标签的动作记录同样禁止在压缩中丢弃。
  - 上下文压缩优先级：System > TaskState > MILESTONE动作 > SOP/失败模式摘要 > NORMAL摘要 > 当前感知。
