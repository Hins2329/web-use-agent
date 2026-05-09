# LoopMonitor 使用指南

## 概述
`LoopMonitor` 是一个基于信息熵算法的死循环监控器，用于检测 Agent 的循环行为并触发熔断。

## 基本使用

### 初始化
```python
from src.agent.workflow.loop_monitor import LoopMonitor

# 创建监控器实例（默认窗口大小为 6）
monitor = LoopMonitor(window_size=6)
```

### 检测循环
```python
# 在每次 LLM 决策后调用
decision = {
    "action": "click",
    "target": {"element_id": 42},
    "input": {"text": "submit"},
    "options": {}
}

warning = monitor.check_and_add(decision)

if warning:
    # 触发熔断，warning 包含详细的警告信息
    print(warning)
    # 采取纠偏措施（如跳过本轮执行）
else:
    # 正常执行动作
    pass
```

### 清空监控器
```python
# 当页面导航发生变化时，应清空监控器
monitor.clear()
```

## 核心概念

### 认知状态分类
LoopMonitor 将动作分为两类认知状态：

**Exploration（探索）**：
- `read_file`：读取本地文件
- `scroll`：滚动页面
- `wait`：等待

**Interaction（交互）**：
- `click`：点击元素
- `type`：输入文本
- `upload_file`：上传文件
- `select_option`：选择下拉选项
- `navigate`：导航到新页面
- `done`：任务完成
- `human_intervene`：请求人工介入

### 动作签名
动作签名用于唯一标识一个动作，格式为：
```
action_type_{element_id}_{text/url/file_path}
```

示例：
- `click_42_submit`
- `type_10_hello world`
- `navigate__https://example.com`

### 熵计算
使用 Shannon 熵衡量动作和状态的多样性：
```
H(X) = -Σ p(x) * log2(p(x))
```

- **动作熵**：衡量动作的多样性
  - 最大值：log2(6) ≈ 2.58（6 个完全不同的动作）
  - 阈值：0.5（低于此值视为动作单一化）

- **状态熵**：衡量认知状态的多样性
  - 最大值：log2(2) = 1.0（两种状态均匀分布）
  - 阈值：0.3（低于此值视为状态固化）

### 震荡检测
检测 A-B-A-B 模式的震荡行为：
- 统计窗口内相邻动作对的反向重复次数
- 阈值：2（检测到 2 次以上震荡即触发）

## 熔断触发条件

满足以下任一条件时触发熔断：

1. **低熵条件**：
   ```
   (Action Entropy < 0.5) AND (State Entropy < 0.3)
   ```

2. **震荡条件**：
   ```
   Oscillation Score >= 2
   ```

## 警告信息格式

触发熔断时，`check_and_add()` 返回格式化的警告信息：

```
================================================================================
⚠️  【死循环警告】你已陷入循环模式！
================================================================================

📊 监控指标：
  • 动作熵 (Action Entropy): 0.00 (阈值: 0.5)
  • 状态熵 (State Entropy): 0.00 (阈值: 0.3)
  • 震荡分数 (Oscillation Score): 0 (阈值: 2)

🔄 最近 6 步动作签名：
  1. click_1_
  2. click_1_
  3. click_1_
  4. click_1_
  5. click_1_
  6. click_1_

💡 建议策略：
  1. 尝试不同的动作（避免重复相同操作）
  2. 切换到不同的页面或元素
  3. 使用 scroll 探索页面其他区域
  4. 如果确实无法继续，请使用 human_intervene 请求人工介入

================================================================================
```

## 在 Workflow 中的集成

### 初始化
```python
class AgentWorkflow:
    def __init__(self):
        # ...
        self.loop_monitor = LoopMonitor()
```

### URL 变化时清空
```python
async def _get_page_state(self):
    current_url = self.browser._page.url
    if self._last_url is not None and current_url != self._last_url:
        # 页面导航，清空监控器
        self.loop_monitor.clear()
```

### ReAct 循环中的拦截
```python
# 获取 LLM 决策
decision = await self._reasoning(goal, page_state)

# 检测死循环
loop_warning = self.loop_monitor.check_and_add(decision)
if loop_warning:
    # 触发熔断
    logger.warning("🔥 死循环熔断触发！")
    logger.warning(loop_warning)
    
    # 构造系统警告决策
    warning_decision = {
        "action": "system_warning",
        "thought": "系统强制熔断：检测到死循环模式",
        "target": {},
        "input": {"warning": loop_warning},
        "options": {}
    }
    self.action_history.append(warning_decision)
    
    # 跳过本轮执行
    continue

# 正常执行动作
action_type = decision["action"]
# ...
```

## 最佳实践

### 1. 及时清空监控器
当检测到页面导航（URL 变化）时，应立即清空监控器：
```python
if current_url != last_url:
    monitor.clear()
```

### 2. 不要终止任务
熔断时不应抛出异常或终止任务，而是：
- 记录警告日志
- 将警告注入到 action_history
- 跳过本轮执行，让 LLM 看到警告并调整策略

### 3. 容错处理
LoopMonitor 已内置容错处理，可以安全处理：
- 缺失的 `target` 字段
- 缺失的 `input` 字段
- 空的 `decision` 字典

### 4. 调整阈值（可选）
如果需要调整熔断灵敏度，可以修改类属性：
```python
monitor = LoopMonitor()
monitor.ACTION_ENTROPY_THRESHOLD = 0.3  # 更严格
monitor.STATE_ENTROPY_THRESHOLD = 0.2   # 更严格
monitor.OSCILLATION_THRESHOLD = 3       # 更宽松
```

## 性能考虑

- **时间复杂度**：O(n)，其中 n 是窗口大小（固定为 6）
- **空间复杂度**：O(n)，使用 deque 固定长度队列
- **计算开销**：极小，每次调用仅需几微秒

## 调试技巧

### 查看当前窗口状态
```python
print(f"动作签名: {list(monitor.action_signatures)}")
print(f"认知状态: {list(monitor.cognitive_states)}")
```

### 手动计算熵
```python
action_entropy = monitor._calculate_entropy(list(monitor.action_signatures))
state_entropy = monitor._calculate_entropy(list(monitor.cognitive_states))
print(f"动作熵: {action_entropy:.2f}")
print(f"状态熵: {state_entropy:.2f}")
```

### 手动计算震荡分数
```python
oscillation_score = monitor._calculate_oscillation(list(monitor.action_signatures))
print(f"震荡分数: {oscillation_score}")
```

## 常见问题

### Q: 为什么窗口大小是 6？
A: 6 是一个经验值，既能捕捉短期循环模式，又不会因为偶然重复而误报。可以根据实际情况调整。

### Q: 如何避免误报？
A: 
1. 确保窗口已满（前 5 步不会触发检测）
2. 页面导航时及时清空监控器
3. 使用多样化的动作序列

### Q: 熔断后如何恢复？
A: 熔断不会终止任务，LLM 会在下一轮看到警告信息并调整策略。如果 LLM 改变了动作模式，监控器会自动解除熔断状态。

### Q: 可以禁用监控器吗？
A: 可以，只需在 workflow 中不调用 `check_and_add()` 即可。但不建议禁用，因为它是防止 Agent 陷入死循环的重要保障。
