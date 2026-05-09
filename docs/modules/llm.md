# llm 模块

## 输入
- `system_prompt`（完整系统提示词）。
- `user_input`（当前步骤任务指令）。
- 采样参数（`temperature`、`max_tokens`）。

## 输出
- 标准化决策 JSON：
  - `thought`
  - `action`
  - `target`
  - `input`
  - `options`
  - `confidence`（可选）

## 职责
- 统一推理接口入口（单一 `chat`）。
- 提供支持 `image_path` 和 `valid_element_ids` 的多模态 `chat` 门面。
- 根据配置执行 manual/auto 路径。
- 对外保证协议化输出。
- 实现内部自我修正环路（Self-Correction），拦截 LLM 编造的不存在 `element_id` 的幻觉，自动追加系统反馈并重试，绝不将错数据抛给下游。
- 保证输出可被 workflow 直接消费，无需后处理纠偏。

## 禁止做的事情
- 禁止访问浏览器执行能力。
- 禁止读取/修改页面 DOM。
- 禁止向 workflow 暴露非协议化中间格式。
