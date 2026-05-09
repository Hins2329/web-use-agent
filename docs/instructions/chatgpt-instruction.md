# computer-use-agent 使用与维护规范（instruction.md）

## 1. 系统本质

本项目是一个基于 ReAct 循环的网页自动化智能体系统：

数据流结构：

Perception（页面感知）
→ LLM（决策）
→ Execution（执行）
→ 循环

---

## 2. 系统使用方式（运行层）

### 2.1 手动模式（开发/调试）

- 使用 playwright 截图
- 手动将截图输入 VLM（或模拟 VLM）
- 手动输入 LLM JSON 决策
- 系统执行 action

适用于：
- 开发调试
- prompt 测试
- 行为验证

---

### 2.2 自动模式（未来）

- Playwright 自动截图
- API 调用 VLM
- API 调用 LLM
- 自动执行 action

---

## 3. 开发规则（非常重要）

### 3.1 数据流原则

- 数据必须单向流动：
  Perception → LLM → Execution
- 禁止任何模块修改上游数据

---

### 3.2 模块职责

- perception：只负责生成 page schema
- llm：只负责生成 decision JSON
- execution：只负责执行 action
- workflow：只负责调度，不做逻辑处理

---

### 3.3 禁止行为

- workflow 不得修改 LLM 输出
- 不得在执行层修复数据结构
- 不得在 perception 注入 workflow 信息
- 不得跨模块“补字段”

---

## 4. 系统演进方式

### 4.1 增加功能

- 只允许新增模块或扩展 execution action
- 必须先更新 CONTRACT.md

---

### 4.2 修改行为

- 先修改 ARCHITECTURE.md
- 再修改对应模块代码

---

### 4.3 修改数据结构

- 必须先修改 CONTRACT.md
- 再同步所有模块

---

## 5. 长期维护原则

- 文档优先于代码
- 协议优先于实现
- 模块独立，不允许耦合
- workflow 永远保持最薄

---

## 6. 核心目标

保持系统：

- 可扩展
- 可替换 LLM/VLM
- 可迁移自动模式
- 可长期维护
