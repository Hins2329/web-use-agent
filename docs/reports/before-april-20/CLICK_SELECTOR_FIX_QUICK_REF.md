# Click方法Selector冲突修复 - 快速参考

## 问题
- **element_id 6** 被映射到通用selector **"button[role='button']"**
- 多个不同的按钮生成相同selector，导致点击错误的元素

## 根本原因

```
多个DOM元素没有唯一标识 (id/class)
    ↓
都生成相同的selector: button[role='button']
    ↓
bulk_register()时，后续元素复用第一个的persistent_id
    ↓
导致多个不同element_id映射到同一个selector
```

## 修复内容

### 改动1：改进_generate_selector()
**文件**: `src/agent/execution/controller.py`

**变更**：
- 提前使用type+role组合（相比单独role更具体）
- 添加多属性组合fallback（type+placeholder、type+title等）
- 减少生成通用selector的可能性

**效果**: 即使没有唯一标识，也能通过属性组合区分

### 改动2：bulk_register()冲突检测与解决
**文件**: `src/agent/execution/controller.py`

**变更**：
```python
# 第一遍：识别冲突（selector被多个元素使用）
selector_usage_count[selector] += 1

# 第二遍：为冲突selector添加标识
if selector_usage_count[selector] > 1:
    # 添加文本、属性或位置标识
```

**冲突解决优先级**：
1. 文本内容：`button[role='button']:contains('保存')`
2. 属性补充：`button[role='button'][title='xxx']`
3. 位置索引：`button[role='button']:nth-of-type(2)`

**效果**: 每个element都获得唯一的selector标识

### 改动3：bulk_register()返回值重构
**文件**: `src/agent/execution/controller.py`

**变更**：
```python
# 原来
def bulk_register(...) -> Dict[str, int]:  # selector → id
    return selector_to_persistent_id

# 改进后
def bulk_register(...) -> Dict[int, int]:  # element_index → id
    return index_to_persistent_id
```

**原因**: 保留元素顺序，防止selector冲突导致的映射丢失

**效果**: Perception准确更新每个element的element_id

### 改动4：PerceptionEngine同步逻辑
**文件**: `src/agent/perception/engine.py`

**变更**：
```python
# 按元素索引更新element_id
for idx, elem in enumerate(page_schema.elements):
    if idx in index_to_persistent_id:
        elem.element_id = index_to_persistent_id[idx]
```

**效果**: 返回给LLM的element_id都是有效的persistent_id

## 数据流对比

### 修复前 ❌
```
element_id 6 → selector="button[role='button']"
element_id 7 → selector="button[role='button']" (复用了6的ID)
                ↓
             click(6) 可能点击了element_id 7
```

### 修复后 ✅
```
element_id 6 → selector="button[role='button']:contains('保存')"
element_id 7 → selector="button[role='button']:contains('取消')"
                ↓
             click(6) 准确点击保存按钮
```

## 验证检查清单

- ✅ Selector冲突检测工作正常
- ✅ 多个相同类型元素能通过属性/文本区分
- ✅ bulk_register()返回Dict[index → id]格式
- ✅ PerceptionEngine按索引同步element_id
- ✅ Execution.click()获得正确的selector
- ✅ 无syntax错误

## 已知限制

1. **:contains()在Firefox不支持**
   - 可能需要XPath fallback

2. **:nth-of-type()依赖元素位置**
   - 动态添加/移除元素时可能失效

3. **文本内容可能改变**
   - 需定期重新感知

## 相关代码位置

| 文件 | 行数 | 改动 |
|------|------|------|
| controller.py | 150-250 | _generate_selector()改进 |
| controller.py | 88-190 | bulk_register()冲突检测 |
| engine.py | 60-90 | 同步逻辑更新 |

## 文档链接

- [CLICK_SELECTOR_FIX.md](CLICK_SELECTOR_FIX.md) - 详细说明
- [ELEMENT_MAPPING_SYNC.md](ELEMENT_MAPPING_SYNC.md) - 前期修复
- [DATA_FLOW_FIX_SUMMARY.md](DATA_FLOW_FIX_SUMMARY.md) - 整体总结

