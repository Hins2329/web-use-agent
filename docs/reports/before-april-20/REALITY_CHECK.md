# Reality Check

## 当前系统 vs Protocol 偏差

### 1. LLMClient
- 当前：workflow 直接依赖 LLMClient
- 问题：manual / API 未解耦

---

### 2. Parser
- 当前：workflow 内处理格式转换
- 问题：违反 parser 层职责

---

### 3. Prompt
- 当前：写在 workflow 中
- 问题：属于 protocol，但未隔离

---

### 4. Page State
- 当前：workflow 修改 page_schema
- 问题：数据流不纯

---

## 结论

当前系统基本符合 ReAct 架构，但存在职责混乱问题。

需要在不改变行为的前提下进行结构重构。
