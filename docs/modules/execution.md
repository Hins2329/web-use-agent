# execution 模块

## 输入
- `Action` 对象：
  - `action`
  - `target`
  - `input`
  - `options`

## 输出
- `ActionResult`：
  - `success`
  - `message`
  - `data`

## 职责
- 解释并执行标准动作类型。
- 基于元素映射完成点击、输入、导航、滚动、等待等操作。
- 维护 `ElementRegistry` 的会话映射与持久化映射。
- 基于 `ElementRegistry` 实现“4层梯队执行策略”，支持选择器优选、坐标兜底、异常处理与结果返回。
- 生成和管理可执行选择器，处理选择器冲突。
- 返回结构化执行结果。

## 兜底执行说明
- 优先使用 Playwright selector 执行动作。
- 若主路径失败或超时，自动降级为使用 `center_x` 和 `center_y` 的物理鼠标点击 (`page.mouse.click`)。
- 该策略彻底解决前端动态类名与代码混淆防爬问题，保证在视觉感知坐标存在时仍能完成点击。

## 禁止做的事情
- 禁止生成或修正 LLM 决策。
- 禁止直接解析页面为 PageSchema。
- 禁止回写上游模块数据结构。
- 禁止使用非标准选择器语法（如 jQuery 伪类 `:contains()`）。
