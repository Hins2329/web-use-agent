# Selector语法修复 - 快速参考

## 问题
**selector包含非Playwright语法导致错误**

```
❌ 错误: 'button[role="button"]:contains("搜索")'
         SyntaxError: :contains() 不是有效的Playwright选择器
```

## 修复方案

### 改动1：_generate_selector()简化

**原理**：避免在selector中编码文本内容，而是返回稳定的属性选择器

```python
# 8级优先级（全为CSS标准选择器）
1. id属性        → "#my-btn"
2. class属性     → ".btn.primary"
3. data-*属性    → "[data-id='123']"
4. name属性      → "input[name='search']"
5. type属性      → "input[type='text']"
6. placeholder   → "input[placeholder='搜索']"
7. title属性     → "div[title='description']"
8. role属性      → "button[role='button']"

# ❌ 移除：
- 文本内容 (:contains())
- 位置索引 (:nth-of-type())
```

### 改动2：bulk_register()冲突处理

**原理**：冲突时转换为XPath进行文本匹配

```python
# 冲突解决优先级
1. 尝试CSS属性添加     {base_selector}[attr='value']
2. 降级到XPath文本     //button[contains(text(), '保存')]
3. 最终使用位置选择    (//button)[1]
```

## 有效的Selector格式

### ✅ CSS Selectors（推荐用于属性选择）
```
#id                        # ID选择器
.class                     # Class选择器
element                    # 元素类型
[attr='value']            # 属性选择器
element[attr='value']     # 元素+属性
.class1.class2            # 多class组合
```

### ✅ XPath（推荐用于复杂查询）
```
//element                  # 任意位置的元素
//element[@attr='value']   # 带属性的元素
//element[contains(text(), 'text')]  # 文本匹配
(//element)[1]            # 位置选择
```

### ❌ 不再支持
```
:contains('text')         # jQuery语法
:nth-of-type(n)          # CSS伪类（不支持）
:visible                 # jQuery伪类
:text=pattern            # 非标准格式
```

## 代码示例

### 修复前
```python
# 错误：使用jQuery语法
if elem_text:
    return f"{elem_type}:contains('{elem_text}')"
```

### 修复后
```python
# 正确：使用XPath处理冲突
if selector_usage_count[base_selector] > 1:
    if elem_text:
        # 转换为XPath格式
        return f"//{elem_type}[contains(text(), '{elem_text}')]"
```

## 修改文件

| 文件 | 改动 |
|------|------|
| controller.py:_generate_selector() | 移除:contains()，简化为8级优先级 |
| controller.py:bulk_register() | 改用XPath处理冲突 |

## 验证

✅ **无Syntax错误**
```
controller.py - No errors found
perception/engine.py - No errors found
```

✅ **所有selector都符合标准**
```
CSS: "button[role='button']" ✓
XPath: "//button[contains(text(), '搜索')]" ✓
```

✅ **向后兼容**
```
- 不改变selector返回值的数据类型
- 不改变Execution的click()接口
- 完全透明的修复
```

## 相关文档

- [SELECTOR_SYNTAX_FIX.md](SELECTOR_SYNTAX_FIX.md) - 详细说明
- [CLICK_SELECTOR_FIX.md](CLICK_SELECTOR_FIX.md) - Selector冲突修复
- [CURRENT.md](CURRENT.md) - 进度追踪

