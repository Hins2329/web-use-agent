# memory 模块

## 输入
- **反思模式**：成功的任务 `goal` 与 `action_history`（用于经验提炼与技能总结）。
- **检索模式**：新任务 `goal`（用于意图匹配与技能检索）。

## 输出
- **反思模式**：提炼后的通用泛化 SOP (Skill) 文本，写入本地 `skills_library.json`。
- **检索模式**：匹配的 Skill 列表（包含 `skill_id`、`intent_description`、`guidance_sop`）。

## 职责
- 负责将长序列历史总结为无特定 `element_id` 的通用指导规则（去具体化）。
- 负责基于意图语义检索本地 `skills_library.json`，为新任务提供经验复用。
- 负责智能体的经验反思、技能提取与检索（Self-Learning 机制）。
- 负责维护本地技能库的持久化存储与版本管理。

## 禁止做的事情
- 禁止参与网页执行或改变底座的 ReAct 轮转规则。
- 禁止直接调用 `perception`、`execution` 或 `tools` 模块。
- 禁止修改 `workflow` 的循环控制逻辑。
- 禁止在技能中硬编码特定的 `element_id` 或页面结构细节。
- 禁止干预 LLM 的实时决策生成过程。
