# workflow 模块

## 输入
- 任务目标 `goal`。
- 可选起始 URL `start_url`。

## 输出
- `TaskResult`：
  - `success`
  - `final_thought`
  - `steps_taken`
  - `actions_executed`
  - `final_page_state`
  - `error_message`

## 职责
- 组织 ReAct 循环。
- 按顺序调用 `perception -> llm -> execution`。
- 在每个单步循环开始前强制清理 `ElementRegistry` 的会话映射。
- 在动作执行后根据动作类型执行分级页面等待（如普通动作等待 2 秒、人工干预等待 3 秒）。
- 提取 `page_state` 中的 `valid_element_ids` 列表和 `image_path`，并通过依赖注入传给 `llm` 模块。
- 控制终止条件（`done` 或步数上限）。
- 维护页面 URL 边界并在导航变化时触发映射重置流程。
- 引入基于"动作熵 (Action Entropy)"、"状态熵 (State Entropy)" 和 "震荡分数 (Oscillation Score)" 的 Loop Monitor 滑动窗口机制（Window Size=6）。
- 监控最近 6 步动作的 Action Signature（`action` + 核心参数）和 Cognitive State（Gathering/Interacting/Navigating）。
- 当触发死循环阈值时，执行熔断处置：强制中断当前动作执行，并将血红警告追加至 LLM 下一轮的 Context 中进行纠偏。
- **引入基于脏标记 (Dirty Flag) 的懒感知 (Lazy Perception) 机制**：
  - 维护 `_browser_needs_update` 脏标记和 `_last_page_state` 状态缓存。
  - 本地工具调用成功后，设置脏标记为 False，下一轮复用缓存的页面状态和元素映射，跳过截图、DOM 解析和 SoM 标注。
  - 浏览器动作执行后、页面导航时、异常情况下，强制设置脏标记为 True，下一轮执行完整感知。
  - **性能收益**：减少 20% 执行时间和 30% Token 消耗（避免无意义的重复感知）。
- **维护操作历史 (action_history) 和上下文数据 (context_data)**：
  - `action_history`：记录每个动作的决策和执行结果，格式为 `{"decision": {...}, "result": {...}}`。
  - `context_data`：持久化存储大数据（如文件内容），避免在操作历史中重复，减少 Token 消耗。
  - 对于 `read_file` 等本地工具，文件内容存储在 `context_data["read_file_results"]` 中，并在每轮推理时注入到 LLM 的 system_prompt。
  - **数据流闭环**：LLM 能看到完整的操作历史（动作类型 + 执行状态）和完整的文件内容，避免重复执行相同动作。

## 禁止做的事情
- 禁止修改 perception 输出数据。
- 禁止修复或补齐 llm 决策字段。
- 禁止实现解析、规范化、兜底修复逻辑。
- 禁止干预 `element_id` 分配与 selector 生成策略。
