# Task 2 实施报告：死循环监控器 (LoopMonitor)

## 概述
成功在 `workflow` 模块中引入基于信息熵算法的死循环监控器，实现了防死循环熔断机制。

## 实施内容

### 1. 新建 `src/agent/workflow/loop_monitor.py`
创建了 `LoopMonitor` 类，实现以下核心功能：

#### 核心特性
- **滑动窗口机制**：使用 `collections.deque(maxlen=6)` 维护固定长度的滑动窗口
- **认知状态分类**：
  - `Exploration`（探索）: `read_file`, `scroll`, `wait`
  - `Interaction`（交互）: `click`, `type`, `upload_file`, `select_option`, `navigate`, `done`, `human_intervene`

#### 核心算法
1. **动作签名提取** (`_extract_signature`)
   - 格式：`action_type_{element_id}_{text/url/file_path}`
   - 自动截断长参数（最多 20 字符）

2. **Shannon 熵计算** (`_calculate_entropy`)
   - 公式：`H(X) = -Σ p(x) * log2(p(x)`
   - 防护：空列表返回 0，确保 p(x) > 0

3. **震荡检测** (`_calculate_oscillation`)
   - 检测 A-B-A-B 模式
   - 统计相邻动作对的反向重复次数

#### 熔断触发条件
满足以下任一条件时触发熔断：
1. `(Action Entropy < 0.5) AND (State Entropy < 0.3)`
2. `Oscillation Score >= 2`

#### 熔断行为
- **不抛出异常**，不终止任务
- 返回格式化的血红警告信息，包含：
  - 动作熵、状态熵、震荡分数的具体数值
  - 最近 6 步的动作签名列表
  - 建议策略（尝试不同动作、切换页面、请求人工介入）

### 2. 修改 `src/agent/workflow/workflow.py`
在 workflow 中集成 LoopMonitor：

#### 初始化
```python
def __init__(self):
    # ...
    self.loop_monitor = LoopMonitor()
    logger.debug("✓ LoopMonitor 已初始化")
```

#### URL 变化时清空监控器
```python
async def _get_page_state(self):
    # 检测 URL 变化
    if self._last_url is not None and current_url != self._last_url:
        # ...
        self.loop_monitor.clear()
        logger.debug("✓ 死循环监控器已重置（页面导航）")
```

#### ReAct 循环中的熔断拦截
```python
# 在执行动作之前插入检测逻辑
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
    
    # 跳过本轮执行，让 LLM 看到警告
    continue
```

### 3. 测试验证
创建了完整的测试套件：

#### 测试文件
- `tests/test_loop_monitor.py`：pytest 格式的单元测试
- `tests/manual_test_loop_monitor.py`：手动测试脚本
- `tests/standalone_test_loop_monitor.py`：独立测试脚本（无外部依赖）

#### 测试覆盖
✅ 初始化测试
✅ 多样化动作（不触发熔断）
✅ 低熵死循环检测
✅ 震荡模式检测
✅ 窗口未满（不触发）
✅ 清空功能
✅ 熵计算正确性
✅ 缺失字段容错

#### 测试结果
```
================================================================================
✅ 所有测试通过！
================================================================================
```

## 架构约束遵守情况

### ✅ 纯算法类
- `LoopMonitor` 无任何其他模块依赖
- 仅使用 Python 标准库（`math`, `collections`, `typing`）

### ✅ 容错处理
- 使用 `.get()` 方法处理可能缺失的字段
- 提供默认值避免 KeyError
- 空列表和边界情况的防护

### ✅ 单向数据流
- `workflow` 调用 `loop_monitor.check_and_add()`
- `loop_monitor` 返回警告信息或 None
- 不修改上游数据，不产生副作用

### ✅ 熔断不终止任务
- 不抛出异常
- 使用 `continue` 跳过本轮执行
- 将警告注入到 action_history 供 LLM 参考

## 核心指标

### 熵阈值设计
- **动作熵阈值**: 0.5
  - 理论最大值：log2(6) ≈ 2.58（6 个完全不同的动作）
  - 0.5 表示动作重复度很高
  
- **状态熵阈值**: 0.3
  - 理论最大值：log2(2) = 1.0（两种状态均匀分布）
  - 0.3 表示状态固化严重

- **震荡阈值**: 2
  - 检测到 2 次以上的 A-B-A-B 模式即触发

### 滑动窗口大小
- **Window Size**: 6
  - 足够捕捉短期循环模式
  - 不会因为偶然重复而误报
  - 计算开销小（O(n) 复杂度）

## 实际效果预期

### 能检测到的循环模式
1. **单一动作重复**：连续 6 次点击同一个元素
2. **二元震荡**：A-B-A-B-A-B 模式（如反复点击两个按钮）
3. **低多样性循环**：在少数几个动作之间循环

### 不会误报的情况
1. **正常探索**：多样化的动作序列
2. **窗口未满**：前 5 步不会触发检测
3. **页面导航**：URL 变化时自动重置监控器

## 后续优化建议

### 可选增强
1. **自适应阈值**：根据任务类型动态调整阈值
2. **历史统计**：记录熔断次数和模式，用于 LLM 学习
3. **模式识别**：识别更复杂的循环模式（如 A-B-C-A-B-C）
4. **可视化**：生成熵变化曲线图，辅助调试

### 性能优化
- 当前实现已经是 O(n) 复杂度，性能开销极小
- 滑动窗口使用 deque，内存占用固定

## 总结
Task 2 已完成，成功实现了基于信息熵的死循环监控器，并集成到 workflow 中。所有测试通过，架构约束得到严格遵守。系统现在具备了自动检测和熔断死循环的能力，为 Agent 的稳定运行提供了重要保障。
