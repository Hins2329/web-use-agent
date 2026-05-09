# 文档更新总结 (2026-05-07)

## 概述

根据 AI_HANDOVER.md 中已完成功能的更新，对三个核心文档进行了增量修改，确保文档与代码实现保持一致。

## 修改的文档

### 1. docs/ARCHITECTURE.md（架构文档）

#### 修改点 1: memory 模块职责扩展
**位置**: "每层职责" > "memory" 部分

**新增内容**:
- 维护失败模式库（failure_patterns.json）
- 维护 TaskState 任务状态机
- 上下文压缩管理（ContextManager）

#### 修改点 2: 数据流规则扩展
**位置**: "数据流规则（单向）" 部分末尾

**新增内容**:
- **动作里程碑标签系统**: action_history 的 tag 字段（MILESTONE/NORMAL/ERROR）及其优先级规则
- **感知层元素 Diff 机制**: 元素ID集合缓存、diff 计算、三种输出模式
- **TaskState 不可压缩原则**: 上下文压缩优先级规则

---

### 2. docs/CONTRACT.md（数据协议文档）

#### 修改点 1: LLM 输出格式扩展
**位置**: "LLM 输出 JSON 标准格式" 部分

**新增字段**:
```json
"state_update": {
  "complete_sub_goal": 0,
  "add_milestone": "string",
  "add_blocker": "string"
}
```

用于 LLM 驱动 TaskState 更新。

#### 修改点 2: 新增失败模式数据结构
**位置**: "Skill 数据结构规范" 之后

**新增内容**:
```json
{
  "pattern_id": "string",
  "goal": "string",
  "failure_summary": "string",
  "suggestion": "string",
  "created_at": "string"
}
```

定义失败模式的标准数据结构。

#### 修改点 3: 新增 TaskState 数据结构
**位置**: "失败模式数据结构规范" 之后

**新增内容**:
```json
{
  "task_id": "string",
  "goal": "string",
  "sub_goals": [...],
  "milestones": [...],
  "blockers": [...],
  "step_count": "int"
}
```

定义任务状态机的标准数据结构，并强调不可压缩原则。

#### 修改点 4: 新增 ActionHistory 记录结构
**位置**: "TaskState 数据结构规范" 之后

**新增内容**:
```json
{
  "decision": {...},
  "result": {...},
  "tag": "MILESTONE|NORMAL|ERROR"
}
```

定义动作历史记录的标准结构，包含 tag 字段及其优先级规则。

---

### 3. docs/PROJECT.md（项目定义文档）

#### 修改点 1: 系统架构流程扩展
**位置**: "系统整体架构" 部分

**更新内容**:
1. 前置检索阶段：增加"失败模式"检索
2. 新增"任务状态初始化"阶段
3. 感知阶段：补充"懒感知和元素 Diff 优化"
4. 新增"上下文压缩"阶段
5. 执行阶段：补充"更新 TaskState"
6. 反思阶段：补充"失败时提炼失败模式"

#### 修改点 2: memory 层职责扩展
**位置**: "三层结构" > "memory（经验记忆层）" 部分

**新增内容**:
- 检索和保存失败模式
- 维护 TaskState 任务状态机
- 提供 ContextManager 上下文压缩管理

#### 修改点 3: 数据流原则扩展
**位置**: "数据流原则" 部分

**新增内容**:
- 前置/后置阶段包含失败模式处理
- action_history 的 tag 标签系统
- ContextManager 的上下文压缩优先级规则
- TaskState 和 MILESTONE 的不可压缩原则

---

## 核心更新要点

### 1. TaskState 任务状态机 ✅
- 维护 goal/子目标/里程碑/阻塞项
- 由 LLM 的 state_update 字段驱动更新
- 上下文压缩时永不丢弃

### 2. 失败模式库 ✅
- 任务失败时自动提炼保存
- 任务开始时检索注入 task_guidance
- 存储在 failure_patterns.json

### 3. 上下文压缩管理 ✅
- ContextManager 监控 token 用量
- 超过阈值时按优先级重组
- 优先级：System > TaskState > MILESTONE > SOP摘要 > NORMAL摘要 > 当前感知

### 4. 动作里程碑标签系统 ✅
- 每条 action_history 包含 tag 字段
- tag 优先级：ERROR > MILESTONE > NORMAL
- 截取规则：MILESTONE 全部保留，ERROR 保留3条，NORMAL 保留5条

### 5. 感知层元素 Diff 机制 ✅
- 缓存上一次元素ID集合
- 元素无变化时输出简短提示
- 元素有变化时只输出 diff
- URL 变化时强制全量输出

---

## 文档一致性保证

所有修改都严格遵循以下原则：

1. **增量修改**: 只添加新内容，不删除或修改原有内容
2. **协议严谨**: CONTRACT.md 的数据结构定义精确、完整
3. **架构清晰**: ARCHITECTURE.md 的职责划分明确、无歧义
4. **流程完整**: PROJECT.md 的系统流程覆盖所有阶段

---

## 验证清单

- [x] ARCHITECTURE.md 更新完成
- [x] CONTRACT.md 更新完成
- [x] PROJECT.md 更新完成
- [x] 所有新增功能都有对应的数据结构定义
- [x] 所有数据流规则都已更新
- [x] 文档间的引用关系保持一致

---

**更新日期**: 2026-05-07  
**更新者**: Kiro AI Assistant  
**状态**: ✅ 完成并验证
