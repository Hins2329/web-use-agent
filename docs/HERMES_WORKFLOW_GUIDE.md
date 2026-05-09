# Hermes 进化工作流使用指南

## 概述
Hermes 进化工作流是 computer-use-agent 的核心特性，实现了 "检索 -> 执行 -> 反思" 的自我进化机制。

## 快速开始

### 1. 激活虚拟环境
```bash
source venv/bin/activate
```

### 2. 运行 Agent
```bash
python run_agent.py
```

### 3. 查看输出
```
================================================================================
🚀 Hermes 进化工作流启动
================================================================================
📋 任务目标: 在淘宝搜索 RTX 5090 并告诉我第一项的价格
🌐 起始 URL: https://www.taobao.com
================================================================================

🔍 【阶段 1：意图检索】
--------------------------------------------------------------------------------
💭 未找到相关经验，将进行全新探索
--------------------------------------------------------------------------------

⚙️  【阶段 2：执行任务】
--------------------------------------------------------------------------------
... (执行过程)
--------------------------------------------------------------------------------

🧘 【阶段 3：自我反思与学习】
--------------------------------------------------------------------------------
✨ 新技能已习得并写入神经中枢！
--------------------------------------------------------------------------------
```

## 工作流程

### 阶段 1：意图检索 (Retrieval)
Agent 会检索本地技能库，查找是否有相关经验。

**如果找到相关技能**：
```
🧠 触发肌肉记忆！匹配到已有技能:
   📌 技能 ID: 428f7d7e5dc940a6a7dbb8056c59e0a9
   📝 意图描述: 在淘宝搜索商品并告诉我第一项的价格
   ✅ 成功次数: 2
   📖 指导 SOP:
      1. 导航到淘宝首页
      2. 在搜索框中输入商品名称
      3. 点击搜索按钮
      ...
```

**如果未找到相关技能**：
```
💭 未找到相关经验，将进行全新探索
```

### 阶段 2：执行任务 (Execution)
Agent 执行任务，如果有相关技能，会将技能指导注入到系统提示词中。

**执行过程**：
- 感知页面状态
- LLM 推理决策
- 执行动作
- Loop Monitor 监控（防死循环）
- 循环直到完成或失败

**执行结果**：
```
✅ 任务执行成功！
🤖 最终结论: 第一项商品价格为 12999 元
📊 总共耗时 8 步
```

### 阶段 3：自我反思与学习 (Reflection & Evolution)
根据执行结果，Agent 会进行不同的处理。

**情况 A：全新任务探索成功**
```
💡 检测到全新任务探索成功，进入冥想模式...
✨ 新技能已习得并写入神经中枢！
   📌 技能 ID: 428f7d7e5dc940a6a7dbb8056c59e0a9
   📝 意图描述: 在淘宝搜索 RTX 5090 并告诉我第一项的价格
   📖 提炼的 SOP:
      1. 导航到淘宝首页
      2. 在搜索框中输入商品名称
      3. 点击搜索按钮
      4. 等待搜索结果加载
      5. 提取第一项商品的价格信息
```

**情况 B：已有技能复用成功**
```
🎯 已有技能复用成功，增加技能权重
   📌 技能 ID: 428f7d7e5dc940a6a7dbb8056c59e0a9
   ✅ 成功次数: 2 → 3
```

**情况 C：任务失败**
```
💔 任务失败，不记录为技能
```

## 自定义任务

### 修改 run_agent.py
```python
async def main():
    """主入口函数"""
    setup_logger()
    
    # 自定义任务
    goal = "你的任务目标"
    start_url = "起始 URL（可选）"
    
    await run(
        goal=goal,
        start_url=start_url
    )
```

### 示例任务

#### 示例 1：淘宝搜索
```python
goal = "在淘宝搜索 iPhone 15 并告诉我第一项的价格"
start_url = "https://www.taobao.com"
```

#### 示例 2：Google 搜索
```python
goal = "在 Google 搜索 Python 教程并告诉我第一个结果的标题"
start_url = "https://www.google.com"
```

#### 示例 3：信息提取
```python
goal = "打开 GitHub 首页，告诉我 Trending 第一个项目的名称"
start_url = "https://github.com"
```

## 技能库管理

### 查看技能库
```python
from src.agent.memory import SkillManager

manager = SkillManager()
all_skills = manager.get_all_skills()

print(f"技能库包含 {len(all_skills)} 个技能:")
for skill in all_skills:
    print(f"- {skill['intent_description']} (成功次数: {skill['success_count']})")
```

### 手动添加技能
```python
from src.agent.memory import SkillManager

manager = SkillManager()

skill = manager.save_new_skill(
    goal="在淘宝搜索商品",
    sop_text="""1. 导航到淘宝首页
2. 在搜索框中输入商品名称
3. 点击搜索按钮
4. 等待搜索结果加载
5. 提取第一项商品的价格信息"""
)

print(f"技能已保存，ID: {skill['skill_id']}")
```

### 检索技能
```python
from src.agent.memory import SkillManager

manager = SkillManager()

results = manager.search_skills_by_intent(
    query="搜索商品",
    top_k=3
)

print(f"找到 {len(results)} 个相关技能:")
for skill in results:
    print(f"- {skill['intent_description']}")
```

### 技能库位置
技能库存储在：`browser_data/skills_library.json`

## 防死循环机制

### 自动检测
Agent 会自动检测以下循环模式：
1. **单一动作重复**：连续 6 次执行相同动作
2. **二元震荡**：A-B-A-B-A-B 模式
3. **低多样性循环**：在少数几个动作之间循环

### 熔断行为
当检测到循环时，Agent 会：
1. 记录 WARNING 日志
2. 构造系统警告决策
3. 跳过本轮执行
4. 将警告注入到 LLM 下一轮的 Context 中

### 警告示例
```
⚠️ 【死循环警告】你已陷入循环模式！
- 动作熵: 0.00 (阈值: 0.5)
- 状态熵: 0.00 (阈值: 0.3)
- 震荡分数: 0 (阈值: 2)
- 最近 6 步动作: [...]

请立即改变策略：尝试不同的动作、切换页面、或请求人工介入。
```

## 最佳实践

### 1. 任务目标要明确
✅ 好的目标：
```
"在淘宝搜索 RTX 5090 并告诉我第一项的价格"
```

❌ 不好的目标：
```
"帮我找点东西"
```

### 2. 提供起始 URL
如果任务有明确的起始页面，建议提供 `start_url`：
```python
await run(
    goal="在淘宝搜索商品",
    start_url="https://www.taobao.com"  # 提供起始 URL
)
```

### 3. 定期清理技能库
如果技能库过大，可以手动清理低质量技能：
```python
from src.agent.memory import SkillManager

manager = SkillManager()
all_skills = manager.get_all_skills()

# 删除成功次数为 0 的技能
# （当前版本需要手动编辑 JSON 文件）
```

### 4. 监控执行日志
查看日志可以了解 Agent 的思考过程：
```bash
tail -f logs/agent.log
```

## 常见问题

### Q: 为什么第一次执行很慢？
A: 第一次执行是全新探索，需要更多步数。第二次执行会复用已有技能，速度会快很多。

### Q: 如何查看技能库？
A: 技能库存储在 `browser_data/skills_library.json`，可以直接打开查看。

### Q: 技能库会自动清理吗？
A: 当前版本不会自动清理，未来版本会添加自动淘汰低质量技能的功能。

### Q: 如何禁用技能检索？
A: 可以在调用 `run()` 时提供 `task_guidance` 参数，跳过检索阶段：
```python
await run(
    goal="任务目标",
    task_guidance=""  # 跳过检索
)
```

### Q: 如何禁用防死循环？
A: 不建议禁用，但如果确实需要，可以修改 `workflow.py`，注释掉 Loop Monitor 的调用。

### Q: 反思提炼失败怎么办？
A: 反思提炼失败不会影响任务执行，只是不会保存新技能。可以查看日志了解失败原因。

## 进阶使用

### 自定义反思 Prompt
修改 `src/agent/memory/skill_manager.py` 中的 `REFLECTION_SYSTEM_PROMPT`：
```python
REFLECTION_SYSTEM_PROMPT = """
你的自定义反思提示词...
"""
```

### 自定义检索策略
修改 `src/agent/memory/skill_manager.py` 中的 `search_skills_by_intent()` 方法：
```python
def search_skills_by_intent(self, query, top_k=3):
    # 你的自定义检索逻辑
    pass
```

### 自定义熔断阈值
修改 `src/agent/workflow/loop_monitor.py` 中的阈值：
```python
ACTION_ENTROPY_THRESHOLD = 0.5  # 动作熵阈值
STATE_ENTROPY_THRESHOLD = 0.3   # 状态熵阈值
OSCILLATION_THRESHOLD = 2       # 震荡阈值
```

## 性能优化

### 1. 使用更快的 LLM
修改 `.env` 文件，使用更快的 LLM 模型：
```
LLM_PROVIDER=openai
LLM_MODEL=gpt-4-turbo
```

### 2. 减少反思频率
如果不需要每次都反思，可以修改 `run_agent.py`，添加条件判断：
```python
if result.success and matched_skill is None and result.steps_taken > 5:
    # 只有步数超过 5 步才反思
    await skill_manager.reflect_and_extract(...)
```

### 3. 使用向量数据库
未来版本会支持向量数据库进行语义检索，性能会大幅提升。

## 总结
Hermes 进化工作流让 Agent 具备了自我学习和进化的能力。通过不断积累经验，Agent 会越用越聪明，执行效率也会不断提升。

祝你使用愉快！🚀
