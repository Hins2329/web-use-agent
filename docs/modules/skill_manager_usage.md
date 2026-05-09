# SkillManager 使用指南

## 概述
`SkillManager` 是技能管理器，负责经验反思提炼与本地持久化存储，实现 Agent 的 Self-Learning 机制。

## 基本使用

### 初始化
```python
from src.agent.memory import SkillManager

# 使用默认路径（browser_data/skills_library.json）
manager = SkillManager()

# 或指定自定义路径
manager = SkillManager(skills_file_path="path/to/skills.json")
```

### 反思提炼
```python
from src.agent.llm import LLMClient

# 准备数据
goal = "在淘宝搜索商品"
action_history = [
    {
        "action": "navigate",
        "thought": "打开淘宝首页",
        "target": {},
        "input": {"url": "https://www.taobao.com"}
    },
    {
        "action": "click",
        "thought": "点击搜索框",
        "target": {"element_id": 5},
        "input": {}
    },
    {
        "action": "type",
        "thought": "输入商品名称",
        "target": {"element_id": 5},
        "input": {"text": "iPhone 15"}
    },
    {
        "action": "click",
        "thought": "点击搜索按钮",
        "target": {"element_id": 6},
        "input": {}
    },
    {
        "action": "done",
        "thought": "任务完成",
        "target": {},
        "input": {}
    }
]

# 创建 LLMClient
llm_client = LLMClient()

# 反思提炼
sop_text = await manager.reflect_and_extract(
    goal=goal,
    action_history=action_history,
    llm_client=llm_client
)

print(f"提炼的 SOP:\n{sop_text}")
```

### 保存新技能
```python
# 保存技能
skill = manager.save_new_skill(
    goal="在淘宝搜索商品",
    sop_text="1. 导航到淘宝首页\n2. 在搜索框输入商品名称\n3. 点击搜索按钮"
)

print(f"技能已保存，ID: {skill['skill_id']}")
```

### 获取所有技能
```python
all_skills = manager.get_all_skills()
print(f"技能库包含 {len(all_skills)} 个技能")

for skill in all_skills:
    print(f"- {skill['intent_description']}")
```

### 根据 ID 获取技能
```python
skill_id = "428f7d7e5dc940a6a7dbb8056c59e0a9"
skill = manager.get_skill_by_id(skill_id)

if skill:
    print(f"找到技能: {skill['intent_description']}")
    print(f"SOP:\n{skill['guidance_sop']}")
else:
    print("技能不存在")
```

### 增加成功次数
```python
skill_id = "428f7d7e5dc940a6a7dbb8056c59e0a9"
success = manager.increment_success_count(skill_id)

if success:
    print("成功次数已更新")
else:
    print("技能不存在")
```

### 检索技能
```python
# 基于意图检索技能
results = manager.search_skills_by_intent(
    query="搜索商品",
    top_k=3
)

print(f"找到 {len(results)} 个相关技能:")
for i, skill in enumerate(results, 1):
    print(f"{i}. {skill['intent_description']}")
    print(f"   成功次数: {skill['success_count']}")
```

## 完整工作流示例

### 任务执行后的反思与保存
```python
async def execute_task_with_reflection(goal: str, start_url: str):
    """执行任务并进行反思"""
    from src.agent.workflow import AgentWorkflow
    from src.agent.memory import SkillManager
    from src.agent.llm import LLMClient
    
    # 1. 执行任务
    workflow = AgentWorkflow()
    result = await workflow.run_task(goal=goal, start_url=start_url)
    
    # 2. 如果任务成功，进行反思
    if result.success:
        print("任务成功，开始反思...")
        
        # 创建 SkillManager 和 LLMClient
        skill_manager = SkillManager()
        llm_client = LLMClient()
        
        # 反思提炼
        sop_text = await skill_manager.reflect_and_extract(
            goal=goal,
            action_history=result.actions_executed,
            llm_client=llm_client
        )
        
        # 保存技能
        skill = skill_manager.save_new_skill(
            goal=goal,
            sop_text=sop_text
        )
        
        print(f"✓ 技能已保存，ID: {skill['skill_id']}")
        print(f"SOP:\n{sop_text}")
    else:
        print(f"任务失败: {result.error_message}")
    
    return result
```

### 任务执行前的技能检索
```python
async def execute_task_with_skill_retrieval(goal: str, start_url: str):
    """执行任务前检索相关技能"""
    from src.agent.workflow import AgentWorkflow
    from src.agent.memory import SkillManager
    
    # 1. 检索相关技能
    skill_manager = SkillManager()
    relevant_skills = skill_manager.search_skills_by_intent(
        query=goal,
        top_k=3
    )
    
    # 2. 构造任务指导
    task_guidance = ""
    if relevant_skills:
        print(f"找到 {len(relevant_skills)} 个相关技能:")
        guidance_parts = ["【相关经验】"]
        for i, skill in enumerate(relevant_skills, 1):
            print(f"{i}. {skill['intent_description']}")
            guidance_parts.append(f"\n经验 {i}: {skill['intent_description']}")
            guidance_parts.append(skill['guidance_sop'])
        task_guidance = "\n".join(guidance_parts)
    
    # 3. 执行任务（注入技能指导）
    workflow = AgentWorkflow()
    result = await workflow.run_task(
        goal=goal,
        start_url=start_url,
        task_guidance=task_guidance
    )
    
    # 4. 如果使用了技能且任务成功，增加成功次数
    if result.success and relevant_skills:
        for skill in relevant_skills:
            skill_manager.increment_success_count(skill['skill_id'])
    
    return result
```

## 技能数据结构

### Skill 字段说明
```json
{
  "skill_id": "428f7d7e5dc940a6a7dbb8056c59e0a9",
  "intent_description": "在淘宝搜索商品",
  "guidance_sop": "1. 导航到淘宝首页\n2. 在搜索框输入商品名称\n3. 点击搜索按钮",
  "created_at": "2026-04-30T07:11:17.307135Z",
  "success_count": 0
}
```

- **skill_id**: 全局唯一标识符（UUID）
- **intent_description**: 意图描述，用于检索匹配
- **guidance_sop**: 通用操作指导（去具体化的 SOP）
- **created_at**: 创建时间（ISO 8601 格式）
- **success_count**: 成功复用次数

### SOP 编写规范
✅ **正确示例**：
```
1. 导航到淘宝首页
2. 在搜索框中输入商品名称
3. 点击搜索按钮
4. 等待搜索结果加载
5. 点击第一个搜索结果
```

❌ **错误示例**：
```
1. 导航到 https://www.taobao.com
2. 点击 element_id=5
3. 在 input[name='q'] 中输入文本
4. 点击 button.search-btn
```

## 反思 Prompt 核心约束

### 1. 去具体化
- ❌ 错误："点击 element_id=5"
- ✅ 正确："点击搜索按钮"

### 2. 过滤废动作
- 过滤 `system_warning`（死循环警告）
- 过滤试错动作
- 过滤兜底动作

### 3. 提炼主线
- 只保留达成目标的核心步骤
- 去除冗余和重复

### 4. 语义描述
- ❌ 错误："在 input[name='q'] 中输入文本"
- ✅ 正确："在搜索框中输入关键词"

### 5. 通用性
- SOP 应适用于类似任务
- 不限于特定页面或元素

## 最佳实践

### 1. 任务成功后立即反思
```python
if result.success:
    await skill_manager.reflect_and_extract(...)
    skill_manager.save_new_skill(...)
```

### 2. 任务执行前检索技能
```python
relevant_skills = skill_manager.search_skills_by_intent(goal)
if relevant_skills:
    # 注入到 task_guidance
    pass
```

### 3. 定期清理低质量技能
```python
# 删除成功次数为 0 且创建时间超过 30 天的技能
# （未来功能）
```

### 4. 技能质量评估
```python
# 根据 success_count 和 created_at 计算质量分数
# （未来功能）
```

## 性能考虑

### 文件操作
- **读取**：初始化时一次性加载
- **写入**：每次保存技能时写入
- **优化**：使用内存缓存，批量写入

### 检索性能
- **当前**：O(n*m) 关键词匹配
- **优化**：使用倒排索引或向量数据库

### 存储空间
- **单个技能**：约 200-500 字节
- **1000 个技能**：约 200-500 KB
- **建议**：定期清理低质量技能

## 常见问题

### Q: 技能库文件在哪里？
A: 默认路径为 `browser_data/skills_library.json`，可以通过参数自定义。

### Q: 如何备份技能库？
A: 直接复制 `skills_library.json` 文件即可。

### Q: 技能库损坏怎么办？
A: SkillManager 会自动检测并修复损坏的文件，重置为空列表。

### Q: 如何删除技能？
A: 当前版本不支持删除，可以手动编辑 JSON 文件。未来版本会添加删除功能。

### Q: 检索不准确怎么办？
A: 当前版本使用简单的关键词匹配，未来会升级为语义检索。

### Q: 可以使用数据库吗？
A: 可以，只需修改 `_load_skills` 和 `_save_skills` 方法即可。

## 未来扩展

### 语义检索
```python
# 使用向量数据库
from chromadb import Client

class SkillManager:
    def __init__(self):
        self.chroma_client = Client()
        self.collection = self.chroma_client.create_collection("skills")
    
    def search_skills_by_intent(self, query, top_k=3):
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k
        )
        return results
```

### LLM 意图匹配
```python
async def search_skills_by_intent_llm(self, query, top_k=3):
    # 使用 LLM 进行意图匹配
    prompt = f"从以下技能中选择与'{query}'最相关的 {top_k} 个..."
    result = await self.llm_client.chat(...)
    return result
```

### 技能评分
```python
def calculate_skill_score(self, skill):
    # 根据 success_count 和 created_at 计算质量分数
    age_days = (datetime.now() - datetime.fromisoformat(skill['created_at'])).days
    score = skill['success_count'] * 10 - age_days * 0.1
    return score
```
