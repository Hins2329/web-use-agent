# 任务回放日志系统

## 概述

任务回放日志系统为 Web Agent 提供了完整的任务执行记录功能，可以回放和分析 Agent 的每一步操作。

## 功能特性

- **自动记录**：在 `workflow.py` 中自动记录每个动作的执行情况
- **零架构改动**：只追加写入，不影响现有代码逻辑
- **标准库实现**：只使用 Python 标准库（json/pathlib/datetime）
- **JSONL 格式**：每行一个 JSON 对象，易于解析和处理
- **命令行查看器**：提供友好的命令行工具查看回放日志

## 日志文件位置

```
logs/replay_{task_id}.jsonl
```

例如：`logs/replay_task_1.jsonl`

## 日志格式

每行一个 JSON 对象，包含以下字段：

```json
{
  "timestamp": "2026-05-07T10:30:00.123Z",
  "step": 3,
  "action": "click",
  "target": {"element_id": 15},
  "input": {"text": "Python书籍"},
  "result_success": true,
  "result_message": "点击成功",
  "tag": "MILESTONE",
  "url": "https://taobao.com/search",
  "task_state_snapshot": {
    "task_id": "task_1",
    "goal": "在淘宝上搜索Python书籍",
    "sub_goals": [
      {"description": "打开淘宝首页", "status": "completed"},
      {"description": "在搜索框输入'Python书籍'", "status": "completed"},
      {"description": "浏览搜索结果", "status": "pending"}
    ],
    "milestones": ["已登录", "已搜索"],
    "blockers": [],
    "step_count": 3
  }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamp` | string | ISO 8601 格式的时间戳 |
| `step` | int | 步骤编号 |
| `action` | string | 动作类型（click/type/navigate/scroll/wait/done等） |
| `target` | object | 动作目标（element_id/url/selector等） |
| `input` | object | 输入参数（text/file_path等） |
| `result_success` | boolean | 执行是否成功 |
| `result_message` | string | 执行结果消息 |
| `tag` | string | 标签（MILESTONE/ERROR/NORMAL） |
| `url` | string | 当前页面 URL |
| `task_state_snapshot` | object | 任务状态快照 |

### 标签说明

- **MILESTONE**：里程碑步骤（完成子目标、URL变化、任务完成）
- **ERROR**：错误步骤（执行失败、异常、死循环熔断）
- **NORMAL**：普通步骤（正常执行）

## 使用回放查看器

### 基本用法

```bash
python tools/replay_viewer.py logs/replay_task_1.jsonl
```

### 过滤显示

只显示里程碑步骤：

```bash
python tools/replay_viewer.py logs/replay_task_1.jsonl --filter MILESTONE
```

只显示错误步骤：

```bash
python tools/replay_viewer.py logs/replay_task_1.jsonl --filter ERROR
```

### 跳转到指定步骤

从第 5 步开始显示：

```bash
python tools/replay_viewer.py logs/replay_task_1.jsonl --step 5
```

### 组合使用

从第 3 步开始，只显示里程碑：

```bash
python tools/replay_viewer.py logs/replay_task_1.jsonl --step 3 --filter MILESTONE
```

## 输出示例

```
加载了 5 条日志记录

────────────────────────────────────────────────────────────
Step 3 | 2026-05-07 10:30:00 | MILESTONE
Action : click → element_id=15
Result : ✓ 点击成功
URL    : https://taobao.com/search
State  : 子目标 2/4 完成, 里程碑: ['已登录', '已搜索']
────────────────────────────────────────────────────────────

共显示 5 条记录
```

## 实现细节

### workflow.py 修改

1. **导入依赖**：添加 `pathlib` 和 `datetime` 导入
2. **新增方法**：`_write_replay_log()` 方法负责写入日志
3. **调用点**：在所有 `action_history.append()` 后立即调用日志写入

### 写入逻辑

```python
def _write_replay_log(self, action_record: Dict[str, Any]) -> None:
    """将动作记录写入回放日志文件"""
    try:
        # 构建日志目录和文件路径
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / f"replay_{self.task_state.task_id}.jsonl"
        
        # 构建日志记录
        log_entry = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "step": self.step_count,
            "action": decision.get("action", "unknown"),
            "target": decision.get("target", {}),
            "input": decision.get("input", {}),
            "result_success": result.get("success", False),
            "result_message": result.get("message", ""),
            "tag": tag,
            "url": current_url,
            "task_state_snapshot": self.task_state.to_dict()
        }
        
        # 追加写入（单行 JSON）
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
    except Exception as e:
        # 写入失败只记录警告，不影响主流程
        logger.warning(f"写入回放日志失败: {e}")
```

### 错误处理

- 写入失败时只记录 warning 日志
- 绝对不会抛出异常影响主流程
- 确保 Agent 执行的稳定性

## 应用场景

1. **调试分析**：回放任务执行过程，定位问题
2. **性能优化**：分析步骤耗时，优化执行效率
3. **行为审计**：记录 Agent 的所有操作，便于审计
4. **失败分析**：快速定位失败原因和错误步骤
5. **学习训练**：收集成功案例，用于模型训练

## 注意事项

1. 日志文件会持续增长，建议定期清理
2. 每个任务一个独立的日志文件
3. 日志文件采用追加写入，不会覆盖
4. task_state_snapshot 包含完整的任务状态，可能较大

## 扩展建议

1. **日志轮转**：实现日志文件大小限制和自动轮转
2. **压缩存储**：对历史日志进行压缩存储
3. **Web 界面**：开发 Web 界面可视化回放
4. **统计分析**：添加统计分析功能（成功率、平均步数等）
5. **导出功能**：支持导出为其他格式（CSV、HTML等）
