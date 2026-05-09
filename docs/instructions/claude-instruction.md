## 1. 任务颗粒度原则

**三层任务结构：**

```
Epic (史诗) → Feature (功能) → Task (任务)
```

**你的记忆模块例子：**

```
Epic: 引入记忆模块
├── Feature: 调研现有方案 (1-2天)
├── Feature: 设计记忆接口 (符合CONTRACT) (1天)
├── Feature: 实现核心功能 (3-5天)
└── Feature: 集成测试 (1天)
```

## 2. 精简文档方案

**只在现有基础上加一个文件：`docs/CURRENT.md`**

``` Markdown
# 当前开发状态

## 本周目标
- [ ] Epic: 引入记忆模块

## 进行中 (最多3个)
- [ ] 调研现有记忆方案
  - GitHub搜索: agent memory, conversation memory
  - 决策记录在本文件底部

## 下一步 (不超过5个)
- [ ] 设计记忆接口 (要符合CONTRACT.md)
- [ ] 优化perception模块性能
- [ ] 添加错误重试机制

## 决策记录
### 2026-04-19: 记忆模块技术选型
问题: 用现有库还是自己写?
调研: langchain memory, mem0, custom solution
决策: 待定
原因: 还在调研阶段
```

## 3. CONTRACT.md 就是真理

是的，你的CONTRACT.md定义了：

- **数据格式标准** - 不能变
- **模块边界** - 不能突破
- **协议约束** - 必须遵守

任何代码变更都要先问：**违反CONTRACT了吗？**

## 4. Task示例 (基于你的架构)

**一个项目一个CURRENT.md，不按模块分:**

```Markdown
## 进行中
- [ ] perception模块: 添加元素置信度评分
  - 输入: screenshot_path 
  - 输出: PageSchema (新增confidence字段)
  - 约束: 不能违反CONTRACT.md的PageSchema格式
  - 时间: 1天

- [ ] llm模块: 优化prompt提高决策准确性  
  - 输入: PageSchema + 任务描述
  - 输出: LLM JSON (符合CONTRACT格式)
  - 测试: 至少3个页面验证
  - 时间: 2天
```

## 5. 完整工作流程

### 开始编码前 (5分钟)

1. **读CONTRACT.md** - 确认边界
2. **看CURRENT.md** - 选择一个进行中任务
3. **写注释** - 在代码里先写TODO

### 编码时

```Python
def new_feature():
    """
    按CURRENT.md里的任务描述:
    输入: XXX (符合CONTRACT)
    输出: XXX (符合CONTRACT) 
    """
    # TODO: 步骤1
    # TODO: 步骤2
    pass
```

### 编码后 (5分钟)

1. **自检CONTRACT** - 没违反吗？
2. **更新CURRENT.md** - 完成就移到"下一步"
3. **commit消息** - 写清楚改了什么

### 每天结束 (5分钟)

更新CURRENT.md的决策记录部分

## 6. 记忆模块具体执行

**今天做：**

```Markdown
## 进行中
- [ ] Epic分解: 记忆模块调研
  - GitHub搜索相关项目
  - 看3个主要方案的API设计
  - 写决策记录 (本文档底部)
```

**调研完成后：**

```Markdown
## 进行中  
- [ ] 设计记忆接口 (符合CONTRACT约束)
  - 定义MemorySchema
  - 确认与现有模块的集成点
  - 更新ARCHITECTURE.md (如果需要)
```



# 当前开发状态

## 本周目标
- [ ] Epic: [大功能名称]

## 进行中 (最多3个)
- [ ] [任务名]: [具体描述]
  - 输入: [数据格式，符合CONTRACT]
  - 输出: [数据格式，符合CONTRACT]
  - 约束: [不能违反的规则]
  - 时间: [预估]

## 下一步 (不超过5个)
- [ ] [Feature名]: [描述]
- [ ] [Task名]: [描述]

## 待办 (Epics)
- [ ] 引入记忆模块
- [ ] 自动模式实现

---
## 大目标
- [ ] Epic: []

## 进行中 (最多3个)
- [ ] []: []
  - 输入: [ , ]
  - 输出: [ , ]
  - 约束: []

## 下一步 (不超过5个)
- [ ]  :
- [ ]  :

## 待办 (Epics)
- [ ] 
- [ ] 
---
---

## 决策记录
### YYYY-MM-DD: [决策主题]
问题: [要解决的问题]
调研: [调研的方案]
决策: [最终决定]
原因: [为什么这么选择]

---

## Note: 工作流程指引

### 三层任务结构
Epic (史诗) → Feature (功能) → Task (任务)

### 每日工作流
**开始编码前 (5分钟):**
1. 读CONTRACT.md - 确认边界
2. 看本文档 - 选择一个进行中任务
3. 在代码里写TODO注释

**编码后 (5分钟):**
1. 自检CONTRACT - 没违反吗？
2. 更新本文档 - 完成就移到"下一步"
3. commit消息 - 写清楚改了什么

### 任务拆分原则
- Epic放待办，当进行中有空位时拆分第一个Feature
- 进行中最多2-3个任务，保持专注
- 每个任务要明确：输入、输出、约束、时间

### 核心原则
CONTRACT.md = 真理，任何变更都要先问：违反CONTRACT了吗？