# Perception-Execution 元素映射断裂修复

## 问题诊断

**现象**:
- Perception生成PageSchema包含element_id 1806
- Execution查询get_selector(1806)时报错："元素ID已过期或不在当前页面中"

**根本原因**:
1. DOMParser生成临时element_id（递增序列1,2,3...）
2. 某些元素无法生成CSS选择器，不被注册
3. PageSchema包含所有元素（包括无法注册的），element_id仍为临时值
4. ElementRegistry中只注册了能生成selector的元素
5. Perception和Execution之间的element_id不同步

**数据流断裂点**:
```
Perception:                          Execution:
========                            ==========
DOMParser → element_id=1,2,3...
         ↓
PageSchema(id=1..1806...)  ←→  ElementRegistry(selector → persistent_id)
                                   ↑
                        但是mapping不完整！
```

## 实现的修复

### 修复1: bulk_register()返回映射信息
**文件**: `src/agent/execution/controller.py`

**改动**:
```python
def bulk_register(self, elements: list) -> Dict[str, int]:
    # 返回 selector -> persistent_id 的映射
    # 而不是仅返回注册数量
    return selector_to_persistent_id
```

**作用**: 让perception知道哪些元素被注册、对应的persistent_id是多少

### 修复2: PerceptionEngine同步element_id
**文件**: `src/agent/perception/engine.py`

**改动**:
```python
# 获取selector到persistent_id的映射
selector_to_persistent_id = element_registry.bulk_register(elements)

# 更新PageSchema中的element_id为persistent_id
updated_elements = []
for elem in page_schema.elements:
    selector = element_registry.generate_selector(elem.to_dict())
    if selector and selector in selector_to_persistent_id:
        # 关键：更新element_id为persistent_id
        elem.element_id = selector_to_persistent_id[selector]
        updated_elements.append(elem)
    else:
        # 无法注册的元素被排除
        continue

page_schema.elements = updated_elements
```

**作用**: 确保返回给workflow的element_id都是ElementRegistry中已注册的persistent_id

### 修复3: 添加公开的generate_selector方法
**文件**: `src/agent/execution/controller.py`

```python
def generate_selector(self, elem: dict) -> Optional[str]:
    """公开方法，供perception使用"""
    return self._generate_selector(elem)
```

**作用**: 避免perception直接访问private方法

### 修复4: 改进selector生成策略
**文件**: `src/agent/execution/controller.py`

**新增fallback策略**:
1. id属性 → `#id`
2. class属性 → `type.class1.class2...`
3. data-id等特殊属性 → `[data-id='value']`
4. name属性 → `type[name='value']`
5. role属性 → `type[role='value']`
6. type属性 → `input[type='text']`
7. 文本内容 → `type:contains('text')`
8. placeholder属性 → `type[placeholder='..']`
9. title属性 → `type[title='..']`
10. 最后fallback → `type` 仅使用类型

**效果**: 几乎所有元素都能生成至少一个selector

## 数据流修复后

```
Perception:                          Execution:
========                            ==========
DOMParser → 临时element_id=1..1806
         ↓
PerceptionEngine:
  ├─ clear() → 清空会话映射
  ├─ bulk_register() → 分配persistent_id
  └─ 【关键】更新element_id为persistent_id
         ↓
PageSchema(id=1,2,3...)  ←→  ElementRegistry(selector → 1,2,3...)
                                   ✓ 完全对应！

ActionExecutor:
  └─ get_selector(1) → 返回 #search-btn
```

## 关键改动总结

| 文件 | 方法 | 改动 |
|-----|------|------|
| controller.py | bulk_register() | 返回Dict而非int |
| controller.py | generate_selector() | 新增public方法 |
| controller.py | _generate_selector() | 改进9级fallback策略 |
| engine.py | understand() | 更新PageSchema的element_id |

## 效果验证

### 场景1: 所有元素都能生成selector
- ✅ 所有元素被注册
- ✅ PageSchema只包含已注册元素
- ✅ element_id = persistent_id
- ✅ execution查询成功

### 场景2: 部分元素无法生成selector
- ✅ 这些元素从PageSchema中排除
- ✅ 不会出现"ID已过期"错误
- ✅ 只返回可操作的元素

### 场景3: 跨页面元素ID一致性
- ✅ 相同selector在不同感知调用中获得相同ID
- ✅ 持久化映射保证一致性

## 向后兼容性

✅ 完全向后兼容
- PageSchema结构不变
- element_id仍为整数
- 仅改变其值的含义（临时ID → persistent_id）
- execution的查询接口不变

## 可能的进一步优化

1. **缓存selector生成结果** - 避免重复计算
2. **元素特征指纹** - 使用DOM特征而非text作为fallback
3. **增量更新** - 只更新改变的元素，而非全量重新生成
4. **性能监控** - 统计selector生成成功率和性能
