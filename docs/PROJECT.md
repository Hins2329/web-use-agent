# 项目定义
computer-use-agent 是一个多模态、自进化的 LLM Agent 框架，通过 SoM（Set-of-Mark）视觉标注机制对网页进行感知降维，结合 ReAct 推理与浏览器执行闭环，实现复杂 Web 任务的自主完成。系统通过 SOP（Standard Operating Procedure）技能记忆实现经验沉淀，并结合幻觉校验、动作熵死循环检测、状态熵死循环检测与懒感知（Lazy Perception）等机制，在保证低 Token 成本的同时提升执行稳定性与泛化能力。

## 项目词条
- 基于 SoM（Set-of-Mark）视觉标注将网页交互元素结构化编号，构建视觉-DOM 双模态感知体系。
- 设计 ReAct Agent 工作流，实现 LLM 决策 + 浏览器执行闭环。
- 构建 SOP（Standard Operating Procedure）技能记忆模块，自动沉淀任务经验并实现跨任务复用。
- 实现 LLM 幻觉拦截与自修正机制（多轮重试 + ID 校验），提升决策可靠性。
- 引入动作熵 + 状态熵死循环检测与懒感知（Lazy Perception）策略，降低无效调用与 Token 消耗。
- 设计 Selector + 物理坐标双通道执行引擎，提升复杂网页自动化鲁棒性。

## 未来优化
- 通过 CDP + WebSocket 直接控制浏览器内核执行逻辑，进一步节省 Token 消耗。
- 持续完善任务状态机（TaskState），用于跟踪目标、子任务与执行进度，提升 Agent 的长程任务一致性与可控性。

# 系统整体架构（ReAct Loop + Self-Evolution + Context Management）
1. **前置检索阶段 (Retrieval)**：`memory` 基于任务 `goal` 检索匹配的 Skill 和失败模式并注入到 `workflow` 上下文。
2. **任务状态初始化**：`workflow` 调用 LLM 生成初始 TaskState（goal/子目标列表），维护任务执行状态。
3. **感知阶段**：`workflow` 驱动循环并请求 `perception` 获取页面状态（支持懒感知和元素 Diff 优化）。
4. **推理阶段**：`workflow` 使用页面状态、历史、TaskState 与检索到的 Skill 构造提示并调用 `llm`。
5. **上下文压缩**：`memory` 的 ContextManager 监控 token 用量，超过阈值时按优先级重组（System > TaskState > MILESTONE > SOP摘要 > NORMAL摘要 > 当前感知）。
6. **执行阶段**：`workflow` 将 `llm` 决策转交 `execution` 或 `tools` 执行动作，并根据执行结果更新 TaskState。
7. **监控阶段**：`workflow` 的 Loop Monitor 基于滑动窗口监控动作熵、状态熵与震荡分数，触发死循环阈值时执行熔断纠偏。
8. **反思阶段 (Reflection)**：任务成功完成后，`memory` 对 `action_history` 进行反思并提取通用 Skill 写入本地存储；任务失败时提炼失败模式并保存。
9. 执行后进入下一轮感知，直到 `done` 或达到步数限制。

# 三层结构
## 感知层（perception）
- 负责 DOM 解析与视觉兜底。
- 产出可执行的页面结构，并完成 `element_id` 与执行层映射同步。

## 推理层（llm）
- 负责将提示转换为标准决策 JSON。
- 统一 manual/auto 路径并保证输出协议一致。

## 执行层（execution + tools）
### execution（浏览器执行层）
- 负责消费浏览器相关的 `Action` 并执行浏览器操作。
- 通过 `ElementRegistry` 解析 `element_id -> selector`。
- 专注于网页交互（click、type、navigate、upload_file 等）。

### tools（本地工具层）
- 负责消费本地工具相关的 `Action` 并执行本地 OS 操作。
- 作为执行动作的平行旁支，负责弥补智能体与本地 OS 的交互能力。
- 专注于本地环境交互（read_file、write_file、list_directory 等）。
- 与 `execution` 模块物理隔离，互不依赖。

### memory（经验记忆层）
- 负责智能体的经验反思、技能提取与检索（Self-Learning 机制）。
- 在任务启动前基于 `goal` 检索匹配的 Skill 和失败模式并注入到 `workflow` 上下文。
- 在任务成功后对 `action_history` 进行反思并提取通用 Skill 写入本地存储。
- 在任务失败后提炼失败模式（失败特征 + 规避建议）并保存到 failure_patterns.json。
- 维护 TaskState 任务状态机（goal/子目标/里程碑/阻塞项），每步由 LLM 的 state_update 字段驱动更新。
- 提供 ContextManager 上下文压缩管理，token 用量超过阈值时按优先级重组。
- 与 `workflow` 松耦合，不参与 ReAct 循环的实时决策。

# 数据流原则
- 主链路固定：`memory 检索 -> perception -> workflow -> llm -> workflow -> [Action Router]`。
- 前置阶段：`run_agent` 启动时，`memory` 基于任务 `goal` 检索匹配的 Skill 和失败模式并注入到 `workflow` 上下文。
- Action Router 根据动作类型分发：
  - 浏览器动作 → `execution` 模块
  - 本地工具动作 → `tools` 模块
- 后置阶段：任务成功完成后，`memory` 对 `action_history` 进行反思并提取通用 Skill 写入本地存储；任务失败时提炼失败模式并保存。
- `element_id` 的生命周期仅维持在单次 ReAct 循环（单步）内；每步开始时强制清空映射以应对 SPA 动态渲染。
- `workflow` 不做字段修复、不做结构注入、不做数据纠偏。
- `workflow` 引入基于滑动窗口的 Loop Monitor 机制，监控动作熵、状态熵与震荡分数，触发死循环阈值时强制熔断并注入纠偏警告。
- `workflow` 维护 action_history 的 tag 标签系统（MILESTONE/NORMAL/ERROR），用于上下文压缩时的优先级判断。
- `memory` 的 ContextManager 监控 token 用量，超过阈值时按优先级重组：System > TaskState > MILESTONE动作 > SOP/失败模式摘要 > NORMAL摘要 > 当前感知。
- TaskState 对象在任何上下文压缩操作中绝对禁止截断或丢弃，MILESTONE 标签的动作记录同样禁止丢弃。
- 选择器仅允许标准 CSS 或 XPath。
- `execution` 和 `tools` 模块互不依赖，各自独立处理不同领域的动作。
