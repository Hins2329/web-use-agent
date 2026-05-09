# AI_HANDOVER (AI 架构交接与记忆快照)

> **⚠️ TO ALL FUTURE AI AGENTS (给所有后续接手的 AI)：**
> 欢迎来到本项目！在进行任何代码修改前，请务必仔细阅读本文件的【架构铁律】与【已填平的史诗级血坑】，违背这些红线将导致系统崩溃或被重构打回。细节数据契约请查阅 `docs/CONTRACT.md` 和 `docs/ARCHITECTURE.md`。

## 1. 系统灵魂 (System Vision)
本项目是一个 **基于视觉-DOM 双模态的进化型 Hermes Web Agent**。
它具备：SoM [SoM = Set of Mark（标记集合 / 视觉标注集）**SoM 指的是感知层在页面上给元素“画框 + 编号”的那一套机制**。]动态画框感知、物理坐标降维打击执行、基于信息熵的防死循环熔断、以及将成功经验反思提炼为 SOP[SOP = Standard Operating Procedure（标准操作流程）] 的自我进化能力。底座通用纯粹，业务逻辑完全通过动态 Skill 注入。

## 2. 核心枢纽地图 (Core File Map)
- **`src/agent/workflow/workflow.py`**: 系统中枢。负责 ReAct 循环编排、Action Router (当前仅将 `read_file` 路由到本地工具执行器，其余所有动作路由至浏览器执行器)、脏标记缓存机制 (Lazy Perception)、以及 `task_guidance` 动态 Skill 注入。
- **`src/agent/workflow/loop_monitor.py`**: 基于动作熵、状态熵与震荡分数的死循环拦截器。
- **`src/agent/perception/engine.py`**: 注入 JS 进行视口内有效交互元素的提取、动态画红框与数字标号 (Set-of-Mark)，并生成极致压缩的扁平化 DOM 文本。
- **`src/agent/execution/actions.py`**: 负责浏览器动作，内部实现了 **2层兜底执行策略**（首选 Playwright Selector 1秒 Fail Fast，失败则降级为绝对物理坐标点击，含越界滚动保护与拟人化点击序列）。
- **`src/agent/tools/local_executor.py`**: 处理纯本地 OS 操作（如 `read_file`），与 Playwright 物理隔离。
- **`src/agent/llm/llm_client.py`**: 对外的统一 LLM 门面。内置了多模态图像支持与 **Self-Correction (自我修正环路，最多 3 次重试)**，当 LLM 幻觉编造了不存在的 ID 时，门面层会直接拦截并追加红字警告提示它重试。
- **`src/agent/memory/skill_manager.py`**: 充当 Agent 的"海马体"，任务成功后反思提炼出泛化 SOP 并保存在本地，下一次相同意图直接复用（Hermes 机制）。并行维护失败模式库（failure_patterns.json），任务失败时自动提炼保存，任务开始时检索注入 task_guidance。
- **`src/agent/memory/task_state.py`**: 任务状态机。维护 TaskState（goal/子目标/里程碑/阻塞项），每步由 LLM 的 state_update 字段驱动更新，上下文压缩时永不丢弃。
- **`src/agent/memory/context_manager.py`**: 上下文压缩管理器。token 用量超过阈值(默认80%)时按优先级重组：System > TaskState > MILESTONE动作 > SOP/失败模式摘要 > NORMAL摘要 > 当前感知。
- **`tools/replay_viewer.py`**: 任务回放查看器。读取 logs/replay_{task_id}.jsonl，支持 --filter MILESTONE/ERROR 和 --step N 参数，纯标准库实现。
- **`run_agent.py`**: 交互式入口。`while True` 循环读取用户输入，调用三阶段工作流（意图检索→执行→反思）。`save_new_skill` 调用必须有 `await`，否则报 coroutine 错误。

> 💡 **历史设计文档档案库**：
> 过去所有的 Bugfix、需求分析和详细设计文档，均存档在 `.kiro/specs/` 目录下（如 `lazy-perception-optimization`, `element-id-collision-and-coordinate-fix` 等）。如需探究历史决策，可查阅该目录。

## 3. 架构铁律 (Ironclad Rules)
1. **绝对单向数据流**：Perception 产出状态 -> Workflow 注入 Skill -> LLM 决策 -> Execution/Tools 执行 -> 返回 ActionResult。严禁逆向修改或跨层解析。
2. **严守 ActionResult 契约**：所有执行层（无论网页还是本地工具）必须返回标准字典 `{"success": bool, "message": str, "data": dict}`。
3. **保持底座纯洁性**：绝对禁止在 `system_prompt.py` 中硬编码特化业务逻辑（如"上架商品"）。业务 SOP 必须通过 `run_agent.py` 以 `task_guidance` 参数动态注入。
4. **LLM 模块隔离**：LLM 模块绝对禁止引入 Playwright 或读取 ElementRegistry，所需的一切校验白名单（如 `valid_element_ids`）必须由 Workflow 通过方法参数注入。
5. **TaskState 不可压缩原则**: TaskState 对象在任何上下文压缩操作中绝对禁止截断或丢弃，它是 Agent 的工作记忆核心。MILESTONE 标签的动作记录同样禁止在压缩中丢弃。

## 4. 已填平的史诗级血坑 (Traps Avoided) ⚠️【极其重要】
下一个接手的 AI 极容易在以下地方犯错，请将这些"前车之鉴"刻在逻辑中：

- 💥 **Element ID 撞车覆盖陷阱**：
  - **坑**：曾经在 `ElementRegistry` 中使用 `selector` 作为 key 进行去重，导致大量没有选择器的元素（`selector=""`）被全部强制覆盖为同一个 `id`（如 `[1, 1, 1, 1]`）。
  - **解**：现在 `ElementRegistry.register()` **绝对信任并直接使用**感知层传来的原生 `element_id`，禁止再次去重或重新生成！
- 💥 **相对坐标塌陷陷阱 (Viewport Shift)**：
  - **坑**：曾经感知层提取的是视口相对坐标，当大模型思考时页面发生了滚动，执行层去点相对坐标时直接点歪。
  - **解**：感知层的 JS 必须提取 **绝对物理坐标** (`rect.left + scrollX`)；而执行层 `actions.py` 在兜底物理点击前，必须注入 JS 动态计算 `center_x - scrollX` 得到**视口坐标**，且必须做**越界滚动保护**！
- 💥 **Token 爆炸陷阱**：
  - **坑**：曾经把包含坐标和选择器的完整 `page_state` JSON 直接喂给 LLM，导致单步消耗 55K Token。
  - **解**：`workflow.py` 内部实现了 `_format_page_state_to_text`，强制将 DOM 树拍平成极简文本格式（如 `[15] button: "搜索"`），严禁向大模型发送 JSON 树。
- 💥 **配置污染与 SSL 拦截陷阱**：
  - **坑**：全局配置写死了 Zhipu 的 Base URL，导致 Xiaomi 模型实例化时请求发错地方报 400；Mac 环境 Python 严格拦截 HTTPS 证书。
  - **解**：`config.py` 中的 `base_url` 必须默认留空 `""`，真正的官方 URL 兜底逻辑下沉到各自的 Provider `__init__` 内部。且所有 HTTP 客户端必须配置忽略 SSL 校验的黑科技。
- 💥 **上下文压缩递归陷阱**：
  - **坑**：ContextManager 调用 LLM 做 NORMAL 摘要时，如果传入的 context_manager 不为 None，会触发递归压缩，无限循环。
  - **解**：compress() 内部调用 LLM 时必须传入 context_manager=None，斩断递归链。
- 💥 **压缩后连续 user message 兼容性陷阱**：
  - **坑**：compress() 重组后 TaskState/MILESTONE/摘要 都是 role:user，连续多条 user message 无 assistant 间隔，部分模型（尤其 Zhipu）可能表现异常。
  - **解**：如果发现压缩后 LLM 推理质量下降，优先排查此处，解决方案是将优先级2/3/4合并为一条 user message。
- ✅ **MILESTONE 触发信号已补全（Task 9）**：
  - **现状**：MILESTONE 触发信号已完整实现三信号覆盖：URL变化 + 子目标完成 + 执行环境切换。
  - **实现**：workflow.py 的 tag 判断块已补充环境切换检测（本地工具 ↔ 浏览器工具），跨环境操作自动打 MILESTONE。
  - **位置**：workflow.py → run_task() → tag 判断的 elif 分支

- ⚠️ **动态子目标 LLM 递归调用陷阱**：
  - **坑**：`_try_append_sub_goals()` 调用 LLM 时如果传入 `context_manager`，会在压缩流程内部触发二次压缩，无限递归。
  - **解**：所有"内部 LLM 调用"（子目标追加、SOP精简、NORMAL摘要）必须传入 `context_manager=None`。这是系统约定，新增类似功能时必须遵守。

- ⚠️ **Agent 不知道当前日期（已知问题）**：
  - **坑**：Agent 执行"查明天NBA比赛"时，不知道今天是几号，从日期选择器上随机猜测"明天"，导致逐步点击浪费多步。
  - **解**：workflow.py 的 `_reasoning()` 里，在构建 system_prompt 时注入当前日期：
    ```python
    from datetime import datetime
    today = datetime.now().strftime("%Y年%m月%d日")
    ```
    注入到 system_prompt 开头。
  - **状态**：已知未修复，Task 14 修复。

## 5. 系统隐藏的精妙机制 (Hidden Masterpieces) 🔥【绝对禁止破坏】

以下机制是系统稳定性的核心屏障，经过血泪教训打磨而成。后续 AI 在重构或优化时，**绝对禁止删除或简化**这些防呆设计，否则将导致系统在生产环境中崩溃！

### 5.1 坐标转换与越界滚动闭环 (Coordinate Transform & Overflow Protection)
**位置**: `src/agent/execution/actions.py` → `smart_click()` / `smart_type()`

**核心公式**：
```python
viewport_x = center_x - scroll_x
viewport_y = center_y - scroll_y
```

**完整闭环**：
1. 感知层提取 **绝对物理坐标**（`rect.left + window.scrollX`）
2. 执行层物理点击前，动态注入 JS 获取当前 `window.scrollX/scrollY`
3. 计算视口相对坐标：`viewport_x = center_x - scrollX`
4. **越界检测**：若 `viewport_x/y` 超出视口范围，执行 `window.scrollTo()` 将元素滚动到视口中央
5. **重新获取** 最新的 `scrollX/scrollY`（因为滚动后偏移量已改变）
6. **重新计算** 精确的视口相对坐标
7. 执行物理点击

**红线警告**：
- ❌ 禁止直接使用 `center_x/y` 作为点击坐标（会因滚动偏移而点歪）
- ❌ 禁止在滚动后不重新获取 `scrollX/scrollY`（会使用过期的偏移量）
- ❌ 禁止跳过越界检测（会点击到视口外的虚空）

### 5.2 拟人化物理点击序列 (Anti-Bot Humanized Click)
**位置**: `src/agent/execution/actions.py` → `smart_click()` / `smart_type()`

**强制序列**：
```python
# 第一步：移动鼠标到目标位置
await self.browser._page.mouse.move(viewport_x, viewport_y)
# 第二步：悬停缓冲（让浏览器感知鼠标）
await asyncio.sleep(0.2)
# 第三步：带 150ms 按压延迟的点击（模拟人类手速）
await self.browser._page.mouse.click(viewport_x, viewport_y, delay=150)
```

**设计哲学**：
- 0.2 秒悬停：模拟人类鼠标移动后的短暂停顿，触发前端的 `mouseover` 事件
- 150ms 按压延迟：模拟人类手指按下到抬起的物理时间，规避反爬虫的"瞬点检测"

**红线警告**：
- ❌ 禁止使用 `delay=0` 的机器人瞬点（会被反爬虫系统识别）
- ❌ 禁止跳过 `mouse.move()` 直接点击（会触发"鼠标瞬移"检测）
- ❌ 禁止删除 0.2 秒悬停（会导致前端 hover 事件未触发，某些按钮无法激活）

### 5.3 Fail Fast 策略 (1秒快速失败)
**位置**: `src/agent/execution/actions.py` → `smart_click()` / `smart_type()`

**核心超时**：
```python
await self.browser._page.wait_for_selector(
    selector, state="visible", timeout=1000  # Fail Fast: 1秒超时
)
```

**设计哲学**：
- 首选策略（Playwright Selector）使用 **极短的 1 秒超时**
- 快速失败后立即降级到物理坐标兜底，避免长时间等待无效选择器
- 总执行时间：1秒（首选失败）+ 2秒（坐标兜底）= 3秒，远优于传统的 10秒超时

**红线警告**：
- ❌ 禁止将超时时间改为 5 秒或 10 秒（会导致兜底策略延迟触发）
- ❌ 禁止删除 Fail Fast 机制（会导致系统在选择器失效时长时间卡死）

### 5.4 文件上传的物理铁律 (Upload DOM Constraint)
**位置**: `src/agent/execution/actions.py` → `smart_upload()`

**硬约束**：
```python
# 文件上传强依赖 DOM 节点（<input type="file">），
# 无法使用物理坐标兜底！
```

**技术原因**：
- `<input type="file">` 的文件选择必须通过浏览器原生 API（`set_input_files()`）
- 物理坐标点击无法触发系统文件选择对话框（浏览器安全限制）
- 如果 selector 失效，文件上传动作**必须直接失败**，不能尝试坐标兜底

**红线警告**：
- ❌ 禁止为 `upload_file` 动作添加坐标兜底逻辑（技术上不可行）
- ❌ 禁止在 selector 失效时静默返回成功（会导致后续流程基于错误假设继续执行）

### 5.5 懒感知的脏标记更新规则 (Lazy Perception Dirty Flag)
**位置**: `src/agent/workflow/workflow.py` → `run_task()`

**精细规则**：
```python
# 浏览器动作后：强制标脏
if action_type in ["click", "type", "navigate", "scroll", ...]:
    self._browser_needs_update = True

# 本地工具成功后：保持干净（复用缓存）
if action_type == "read_file" and result.success:
    self._browser_needs_update = False

# 本地工具失败后：强制标脏
if action_type == "read_file" and not result.success:
    self._browser_needs_update = True

# 任何异常后：强制标脏
except Exception:
    self._browser_needs_update = True
```

**设计哲学**：
- 浏览器动作会改变页面状态，必须重新感知
- 本地工具（如读文件）不影响浏览器，可以复用缓存，节省 Token
- 任何异常都可能导致状态不一致，必须强制重新感知

**红线警告**：
- ❌ 禁止在浏览器动作后保持 `_browser_needs_update = False`（会导致 Agent 看到过期的页面状态）
- ❌ 禁止在异常后不重置脏标记（会导致缓存污染）

### 5.6 死循环监控器的自动重置 (Loop Monitor Auto-Reset)
**位置**: `src/agent/workflow/workflow.py` → `_get_page_state()`

**重置触发**：
```python
if current_url != self._last_url:
    self.loop_monitor.clear()
    logger.debug("✓ 死循环监控器已重置（页面导航）")
```

**设计哲学**：
- 页面 URL 变化代表用户导航到新页面，旧的动作模式已失效
- 死循环监控器的滑动窗口必须清空，避免误判新页面的正常操作为循环
- 同时清空 ElementRegistry 的持久化映射，适应新页面的元素结构

**红线警告**：
- ❌ 禁止在页面导航后不清空死循环监控器（会导致新页面的正常操作被误判为循环）
- ❌ 禁止删除 URL 变化检测逻辑（会导致跨页面的死循环无法破除）

### 5.7 LLM 幻觉拦截的重试机制 (Hallucination Retry)
**位置**: `src/agent/llm/llm_client.py` → `chat()`

**重试配置**：
```python
max_retries = 3  # 最多重试 3 次
for attempt in range(max_retries):
    if element_id not in valid_element_ids:
        feedback = f"\n\n[系统反馈]: 你选择的 element_id {element_id} 不存在..."
        current_user_input = user_input + feedback
        continue  # 重试
```

**设计哲学**：
- LLM 可能幻觉编造不存在的 element_id（如页面只有 [1,2,3]，它返回 [99]）
- 门面层拦截后，追加红字系统反馈到 prompt，引导 LLM 重新观察图片
- 最多重试 3 次，避免无限循环

**红线警告**：
- ❌ 禁止删除 `valid_element_ids` 校验逻辑（会导致 Agent 尝试点击不存在的元素）
- ❌ 禁止将重试次数改为 1 次（LLM 需要多次尝试才能纠正幻觉）
- ❌ 禁止在重试时不追加系统反馈（LLM 会重复相同的错误）

### 5.8 Token 优化的多重策略 (Token Optimization)
**位置**: `src/agent/workflow/workflow.py` → `_format_page_state_to_text()`

**优化策略**：
```python
# 策略 1：元素数量截断（只显示前 50 个）
if len(elements) > 50:
    elements = elements[:50]

# 策略 2：文本长度截断（30 字符）
if len(safe_text) > 30:
    safe_text = safe_text[:30] + "..."

# 策略 3：操作历史截断（只保留最近 5 步）
recent_history = list(self.action_history)[-5:]

# 策略 4：空文本元素使用简洁格式
if safe_text:
    lines.append(f"[{element_id}] {elem_type}: \"{safe_text}\"")
else:
    lines.append(f"[{element_id}] {elem_type}")
```

**设计哲学**：
- 原始 `page_state` JSON 包含完整坐标和选择器，单步消耗 55K Token
- 拍平为极简文本后，单步降至 5K Token，节省 90% Token
- 牺牲部分细节（如坐标、选择器），但保留核心信息（element_id、type、text）

**红线警告**：
- ❌ 禁止向 LLM 发送完整的 `page_state` JSON（会导致 Token 爆炸）
- ❌ 禁止删除元素数量截断（会导致超长页面消耗数十万 Token）
- ❌ 禁止删除操作历史截断（会导致长任务的历史累积到数万 Token）

### 5.9 GPU 渲染防抖等待 (GPU Render Debounce)
**位置**: `src/agent/perception/engine.py` → `understand()`

**强制等待**：
```python
await asyncio.sleep(0.8)  # 画框完成后，截图前
```

**设计哲学**：
- 0.8 秒是经过实战调优的最优值，平衡了渲染完整性和执行速度
- 给浏览器 GPU 充足时间完成红色边框的渲染（CSS border 绘制需要时间）
- 为淘宝等 SPA 页面的突发重绘留出缓冲时间（防止截图时页面正在重绘）

**红线警告**：
- ❌ 禁止删除或缩短这个等待（会导致截图中红框未完全渲染，VLM 无法识别标注）
- ❌ 禁止延长到 1 秒以上（会显著增加每步执行时间，影响用户体验）
- ❌ 禁止将其改为可配置参数（这是经过血泪教训调优的魔法数字，不应随意修改）

### 5.10 淘宝登录页面特殊处理 (Taobao Login Handler)
**位置**: `src/agent/workflow/workflow.py` → `run_task()`

**检测逻辑**：
```python
if "login.taobao.com" in current_url:
    await asyncio.sleep(pause_duration)  # 默认 30 秒
```

**设计哲学**：
- 淘宝登录需要扫码，Agent 无法自动完成
- 检测到登录页面后，自动暂停 30 秒，给用户足够时间扫码
- 暂停时间可通过 `config.yaml` 中的 `agent.login_pause_duration` 配置

**红线警告**：
- ❌ 禁止删除这个检测逻辑（会导致 Agent 在登录页面卡死）
- ❌ 禁止将暂停时间缩短到 15 秒以下（用户可能来不及扫码）
- ⚠️  **技术债务警告**：这是业务特化逻辑，违反了"底座纯洁性"原则，未来必须重构为 Skill 注入实现

### 5.11 页面导航超时容错 (Navigation Timeout Tolerance)
**位置**: `src/agent/execution/controller.py` → `navigate()`

**降级策略**：
```python
try:
    await self._page.goto(url, wait_until="networkidle", timeout=15000)
except PlaywrightTimeoutError:
    # 静默降级：记录警告但不抛出异常
    logger.warning(f"⚠️  导航超时（networkidle），但继续执行: {url}")
```

**设计哲学**：
- `networkidle` 策略要求网络完全空闲（500ms 内无请求）
- 淘宝等 SPA 页面有长连接或轮询请求，导致永久无法 idle
- 捕获超时异常后继续执行，依靠后续的 3 秒固定延迟确保页面加载完成

**红线警告**：
- ❌ 禁止删除 `PlaywrightTimeoutError` 的捕获（会导致 Agent 在淘宝等页面崩溃）
- ❌ 禁止将超时时间延长到 30 秒以上（会显著增加导航时间）
- ❌ 禁止将降级策略改为抛出异常（会破坏对 SPA 页面的兼容性）

### 5.12 动作执行后的智能等待 (Post-Action Smart Wait)
**位置**: `src/agent/workflow/workflow.py` → `run_task()`

**双重保险**：
```python
# 第一重：等待 DOM 树构建完成
await self.browser._page.wait_for_load_state("domcontentloaded", timeout=5000)
# 第二重：固定延迟给动态渲染留出时间
await asyncio.sleep(2)  # 普通动作
await asyncio.sleep(3)  # 人工干预动作
```

**设计哲学**：
- `domcontentloaded` 确保 DOM 树构建完成（但不等待图片、CSS 等资源）
- 固定延迟给 React/Vue 等框架的动态渲染留出时间
- 人工干预动作需要更长的等待时间（3 秒），因为用户操作可能触发复杂的页面变化

**红线警告**：
- ❌ 禁止删除 `domcontentloaded` 等待（会导致下一轮感知获取到不完整的 DOM）
- ❌ 禁止删除固定延迟（会导致动态渲染未完成时就进行感知，获取到过期状态）
- ❌ 禁止将固定延迟缩短到 1 秒以下（React/Vue 渲染需要时间）

### 5.13 滚动到底部检测 (Scroll-to-Bottom Detection)
**位置**: `src/agent/execution/actions.py` → `scroll_into_view()`

**检测逻辑**：
```python
is_at_bottom = (
    scroll_y + viewport_height >= scroll_height - 10  # 10px 容差
)
if is_at_bottom:
    raise BrowserError("已滚动到页面底部，目标元素可能不存在")
```

**设计哲学**：
- 10px 容差是为了处理浮点数精度问题（`scrollY + viewportHeight` 可能不完全等于 `scrollHeight`）
- 检测到底部后立即抛出异常，防止 Agent 陷入无限滚动死循环
- 配合死循环监控器（`LoopMonitor`），双重保险防止滚动死循环

**红线警告**：
- ❌ 禁止删除这个检测逻辑（会导致 Agent 在页面底部陷入死循环）
- ❌ 禁止将容差改为 0（会因为浮点数精度问题导致误判）
- ❌ 禁止将容差扩大到 50px 以上（会导致提前触发底部检测，无法滚动到真正的底部）

### 5.14 滚动有效性检测 (Scroll Effectiveness Check)
**位置**: `src/agent/execution/actions.py` → `scroll_into_view()`

**检测逻辑**：
```python
actual_scroll = after_scroll_y - before_scroll_y
if abs(actual_scroll) < 10:  # 10px 最小有效滚动距离
    raise BrowserError("页面无法滚动，可能已到达底部或页面不可滚动")
```

**设计哲学**：
- 10px 是最小有效滚动距离，低于这个值认为滚动失败
- 检测滚动前后的 `scrollY` 差值，判断滚动是否真正生效
- 配合"滚动到底部检测"，双重保险防止滚动死循环

**红线警告**：
- ❌ 禁止删除这个检测逻辑（会导致 Agent 在不可滚动的页面上陷入死循环）
- ❌ 禁止将最小距离改为 1px（会因为浏览器的微小抖动导致误判）
- ❌ 禁止将最小距离扩大到 50px 以上（会导致小幅度滚动被误判为无效）

### 5.15 Parser 的多层 Fallback 链 (Parser Fallback Chain)
**位置**: `src/agent/utils/parser.py` → `parse_llm_response()`

**4 层 Fallback**：
```python
# 第 1 层：Markdown 代码块提取
json_dict = _extract_from_markdown(response_text)
# 第 2 层：直接 JSON 解析
json_dict = _extract_json(response_text)
# 第 3 层：文本中查找 JSON 对象
json_dict = _find_json_in_text(response_text)
# 第 4 层：兜底默认值
return _default_response("解析异常")
```

**设计哲学**：
- LLM 返回格式不可控，可能是 Markdown 代码块、纯 JSON、混合文本等
- 4 层 Fallback 确保任何格式都能被解析，最后一层兜底返回安全的默认值
- 默认值是 `{"action": "wait", "target": {}, "input": {"delay": 1000}}`，确保系统不会崩溃

**红线警告**：
- ❌ 禁止删除任何一层 Fallback（会导致某些格式的 LLM 响应无法解析）
- ❌ 禁止修改兜底默认值的 action 为 "done"（会导致解析失败时任务直接结束）
- ❌ 禁止在解析失败时抛出异常（会导致系统崩溃，应该返回兜底值让 Agent 继续运行）

### 5.16 配置加载的静默降级 (Config Silent Fallback)
**位置**: `src/config/settings.py` → `AppConfig.__init__()`

**降级策略**：
```python
try:
    yaml_config = self.from_yaml(str(config_yaml_path))
    data = {**self._extract_dict_recursive(yaml_config), **data}
except Exception:
    # 静默降级：YAML 解析失败时继续使用默认值
    pass
```

**设计哲学**：
- YAML 解析失败时不抛出异常，静默降级到硬编码的默认值
- 确保系统的鲁棒性，即使配置文件损坏也能启动
- 但也可能掩盖配置错误，用户不知道配置未生效

**红线警告**：
- ⚠️  这是一个双刃剑机制，提高了鲁棒性但降低了可调试性
- ❌ 禁止删除这个 try-except（会导致配置文件损坏时系统无法启动）
- ⚠️  建议在 except 块中添加日志警告，告知用户配置加载失败

### 5.17 动作里程碑标签系统 (Action Milestone Tagging)
**位置**: `src/agent/workflow/workflow.py` → `run_task()` 的 action_history 写入处

**tag 优先级（严格互斥，禁止两个独立 if 导致覆盖）**：
```python
# ERROR > MILESTONE > NORMAL
if not result.success:
    tag = "ERROR"
elif completed_sub_goal or url_changed:
    tag = "MILESTONE"
else:
    tag = "NORMAL"
```

**_format_action_history() 截取规则**：
- MILESTONE: 全部保留
- ERROR: 保留最近3条
- NORMAL: 保留最近5条

**红线警告**：
- ❌ 禁止用两个独立 if 判断 tag（会导致 ERROR 被 MILESTONE 覆盖）
- ❌ 禁止在压缩时丢弃 MILESTONE 记录（会导致 Agent 遗忘已完成的关键步骤）
- ❌ 禁止将所有动作都标记为 MILESTONE（会导致压缩失效，上下文爆炸）

### 5.18 感知层元素 Diff 机制 (Element Diff)
**位置**: `src/agent/workflow/workflow.py` → `_format_page_state_to_text()`

**三种输出模式（按顺序判断）**：
1. **URL变化** → 强制全量输出，清空 `_last_element_ids` 缓存
2. **_browser_needs_update=False 且元素集合无变化** → 输出 `"[页面状态未变化，请基于上次感知继续决策]"` 简短提示
3. **_browser_needs_update=False 且元素有变化** → 只输出 diff（新增/消失元素）

**Diff 输出格式**：
```
[页面无导航，元素变化如下]

新增元素 (2 个):
[4] button: "新按钮"
[5] input: "新输入框"

消失元素 (1 个):
[2]

其余元素不变
```

**红线警告**：
- ❌ 禁止在 URL 变化时走 diff 模式（新页面必须全量感知）
- ❌ 禁止删除 `_last_element_ids` 缓存更新逻辑（会导致 diff 计算错误）
- ❌ 禁止在异常时不清空 `_last_element_ids`（会导致缓存污染）

### 5.19 任务回放日志系统 (Replay Log)
**位置**: `workflow.py` → `_write_replay_log()` / 所有 `action_history.append()` 之后

**日志路径**: `logs/replay_{task_id}.jsonl`

**每行记录结构**：
```json
{
  "timestamp": "2026-05-07T10:30:00.123Z",
  "step": 3,
  "action": "click",
  "target": {"element_id": 15},
  "input": {},
  "result_success": true,
  "result_message": "点击成功",
  "tag": "MILESTONE",
  "url": "https://taobao.com/search",
  "task_state_snapshot": {
    "task_id": "task_1",
    "goal": "...",
    "sub_goals": [...],
    "milestones": [...],
    "blockers": [],
    "step_count": 3
  }
}
```

**设计哲学**：
- 追加写，不覆盖，零架构侵入
- 写入失败只 log warning，绝对不抛异常影响主流程
- `task_state_snapshot` 是 `TaskState.to_dict()` 的完整快照，压缩恢复时可用

**红线警告**：
- ❌ 禁止在写入失败时抛异常（会导致主流程中断）
- ❌ 禁止改为覆盖写（会丢失历史步骤，无法回放）

### 5.20 执行环境切换 MILESTONE 信号 (Env Switch Milestone)
**位置**: `workflow.py` → `run_task()` → tag 判断块

**类常量**：
```python
LOCAL_ACTIONS = {"read_file", "write_file", "create_file"}
BROWSER_ACTIONS = {"click", "type", "navigate", "scroll", "wait", "upload_file", "select_option", "human_intervene", "done"}
```

**触发条件（完整三信号）**：
```python
MILESTONE = completed_sub_goal OR url_changed OR env_switched
```

其中 `env_switched` 判断逻辑：
```python
env_switched = (
    prev_action_type 和 curr_action_type 一个在 LOCAL_ACTIONS 一个在 BROWSER_ACTIONS
)
```

**重置时机**：
- 任务完成时：`self._prev_action_type = None`
- 任务超时时：`self._prev_action_type = None`
- 任务异常时：`self._prev_action_type = None`

**红线警告**：
- ❌ 禁止删除任何一个重置点（任务结束/超时/异常三处都要重置）
- ❌ 禁止把 `env_switched` 判断放在 ERROR 之前（破坏优先级：ERROR > MILESTONE > NORMAL）

### 5.21 动态子目标追加与数量上限 (Dynamic SubGoal Append)
**位置**: `task_state.py` → `add_sub_goal()` / `workflow.py` → `_try_append_sub_goals()`

**数量上限**：
- `MAX_SUB_GOALS = 10`（类常量）
- `add_sub_goal()` 返回 bool，达到上限时返回 False 并 log warning

**动态追加触发条件（两个同时满足）**：
1. 所有现有子目标 status 均为 completed
2. 本轮 diff 新增元素数量 > 15（`self._last_added_count`）

**触发后调用 LLM 续写最多 3 个子目标**，prompt 明确"不重复已完成内容"

**调用位置**: `run_task()` → `_get_page_state()` 之后、`_reasoning()` 之前

**红线警告**：
- ❌ 禁止删除上限检查（LLM 会无限追加子目标导致列表膨胀）
- ❌ 禁止在 `_try_append_sub_goals()` 里抛异常（影响主流程）
- ❌ 禁止传入非 None 的 `context_manager`（会触发递归压缩）

### 5.22 SOP 二次精简反思 (SOP Refinement)
**位置**: `skill_manager.py` → `_refine_sop()` / `save_new_skill()`

**存储字段**：
- `guidance_sop`: 精简后的 SOP，注入给 Agent 使用
- `sop_raw`: 原始备份，不注入，仅供人工审查

**精简策略**：
- 去除连续失败后才成功的试错序列，只保留最终成功那步
- 去除重复操作
- 保留所有必要步骤

**降级**: LLM 调用失败时静默返回 `raw_sop`，log warning

**红线警告**：
- ❌ 禁止把 `sop_raw` 注入给 Agent（会包含试错噪音）
- ❌ 禁止在精简失败时抛异常（会导致 SOP 无法保存）

### 5.23 截图像素 Diff 缓存 (Screenshot Hash Cache)
**位置**: `perception/engine.py` → `_compute_screenshot_hash()` / `understand()`  
`workflow.py` → `_get_page_state()`（URL变化时清空）

**实现**: PIL 缩放到 16x16 灰度图 + MD5，完全相同才复用（保守策略）

**缓存清空时机**: URL 变化时在 `workflow.py` 的 `_get_page_state()` 里强制清空：
```python
self.perception_engine._last_screenshot_hash = None
```

**红线警告**：
- ❌ 绝对禁止动 `asyncio.sleep(0.8)` 防抖等待
- ❌ 禁止在 URL 变化后不清空缓存（会导致新页面复用旧截图）
- ❌ 禁止在异常时不降级（应该降级使用新截图，不抛异常）

## 6.5 已规划未实现 (Planned But Not Implemented) 【技术债务追踪】

以下功能已完成设计和规划，但尚未实现。这些是系统的下一步演进方向：

### 核心功能（P0 优先级）
- [x] **TaskState 任务状态机** (`src/agent/memory/task_state.py`)
  - 维护结构化的任务状态（goal/子目标列表/里程碑/阻塞项）
  - 每步由 LLM 输出 state_update 字段更新
  - 上下文压缩时永不丢弃
  - **状态**: ✅ 已完成
  - ✅ 静态子目标生成、state_update 驱动更新、serialize_for_prompt
  - ✅ 动态追加子目标链路已实现（Task 10）
  - ❌ 缺：task_id 固定为 "task_1"，TaskStack 未实现

### 高优先级功能（P1 优先级）
- [x] **动作 MILESTONE 标签系统** (`src/agent/workflow/workflow.py`)
  - action_history 的每条记录新增 tag 字段（MILESTONE/NORMAL/ERROR）
  - URL 变化时自动打 MILESTONE 标签
  - 压缩逻辑里 MILESTONE 记录永不丢弃
  - **状态**: ✅ 完全完成（Task 9 补全环境切换信号）

- [x] **ContextManager 上下文压缩** (`src/agent/memory/context_manager.py`)
  - 监控每次发给 LLM 的 token 数（用 tiktoken 估算）
  - 超过阈值时按优先级重组：System > TaskState > MILESTONE > SOP摘要 > 压缩普通动作 > 当前感知
  - "压缩普通动作"步骤调用轻量 LLM 生成摘要句
  - **状态**: ✅ 已完成

- [x] **Task 8 — 任务回放日志** (`tools/replay_viewer.py`, `logs/replay_{task_id}.jsonl`)
  - 在 workflow.py 的所有 action_history.append() 后追加写入 JSONL 日志
  - 每行记录包含 timestamp/step/action/target/input/result/tag/url/task_state_snapshot
  - 提供命令行查看器支持 --filter MILESTONE/ERROR 和 --step N 参数
  - **状态**: ✅ 已完成

- [x] **Task 9 — MILESTONE 触发信号补全** (`workflow.py`)
  - 补充执行环境切换信号（本地工具 ↔ 浏览器工具）
  - 完整三信号：URL变化 + 子目标完成 + 环境切换
  - 在任务完成/超时/异常时重置 _prev_action_type
  - **状态**: ✅ 已完成

- [x] **Task 10 — 动态子目标追加 + 数量上限** (`task_state.py`, `workflow.py`)
  - MAX_SUB_GOALS = 10，add_sub_goal() 返回 bool
  - 触发条件：所有子目标完成 AND 新增元素 > 15
  - 调用 LLM 续写最多 3 个子目标，传入 context_manager=None
  - **状态**: ✅ 已完成

- [x] **Task 11 — SOP 二次精简反思** (`skill_manager.py`)
  - guidance_sop（精简后，注入 Agent）+ sop_raw（原始备份）双字段
  - 去除试错步骤、重复操作，保留必要步骤
  - LLM 失败时静默降级返回 raw_sop
  - **状态**: ✅ 已完成

### 中优先级功能（P2 优先级）
- [x] **失败模式库** (`src/agent/memory/skill_manager.py` 扩展)
  - 新增 save_failure_pattern() 和 search_failure_patterns()
  - 任务失败时由 LLM 提炼"失败特征+原因+规避建议"写入
  - 任务开始时与 SOP 一起检索注入
  - **状态**: ✅ 已完成

### 低优先级功能（P3 优先级）
- [x] **感知层元素 Diff 机制** (`src/agent/workflow/workflow.py`)
  - 缓存上一次元素ID集合（`_last_element_ids`）
  - URL 未变且元素集合无变化时，只向 LLM 发送简短提示
  - 元素有变化时，只发送 diff（新增元素 + 消失元素）
  - 与现有 lazy perception 脏标记配合使用
  - **状态**: ✅ 已完成
  - **注意**: 已保留 5.9 GPU 渲染防抖等待

- [x] **Task 12 — 截图像素 Diff** (`perception/engine.py`, `workflow.py`)
  - 16x16 灰度图 MD5 哈希，完全相同才复用（保守策略）
  - URL 变化时在 workflow.py 强制清空缓存
  - 异常时降级使用新截图，不抛异常
  - **状态**: ✅ 已完成
  - **注意**: 已保留 5.9 GPU 渲染防抖等待

- [x] **coroutine bug 修复** (`run_agent.py` 阶段3)
  - `save_new_skill` 是 async 方法但调用处缺 `await`
  - 导致 `'coroutine' object is not subscriptable` 报错
  - **状态**: ✅ 已修复

- [x] **端到端验证通过**
  - 17步完成复合任务（读本地文件 + 网页填写 + 浏览器搜索）
  - TaskState 子目标生成和更新正常
  - MILESTONE 标签在正确时机打标
  - 上下文压缩触发后 Agent 正常推理
  - 回放日志完整生成
  - SOP 在任务成功后保存，guidance_sop 比 sop_raw 短
  - **状态**: ✅ 验证通过

- [ ] **Task 14 — 注入当前日期到 system prompt** [P1]
  - 问题：Agent 不知道今天日期，"明天"等相对时间概念无法正确理解
  - 解法：workflow.py 的 `_reasoning()` 里注入
    `f"【当前日期】{datetime.now().strftime('%Y年%m月%d日')}\n"` 到 system_prompt 开头
  - 文件：只改 workflow.py，3 行
  - **依赖**: 无
  - **阻塞**: 无

- [ ] **SOP库分层检索策略**
  - 当前: 全量注入，阈值50条升级
  - 未来: 基于任务意图的分层检索
  - **依赖**: 无
  - **阻塞**: 无

- [ ] **多轮对话 TaskStack** (`src/agent/memory/task_stack.py`)
  - TaskState 预留 task_id 字段（Task1 里已做）
  - 新增 TaskStack 管理器，支持 push/pop/list
  - Task 切换时序列化当前 TaskState（含当前 URL）到栈
  - 恢复时重新导航 + 重新感知 + 恢复 TaskState 注入
  - 意图跳变检测用轻量 LLM classifier 实现
  - **依赖**: TaskState (已完成)
  - **阻塞**: 无
  - **备注**: 下个版本功能

## 6. 接下来做什么 (Next Steps)
请读取本项目根目录或 docs 目录下的 `CURRENT.md` 获取当前正在进行的 Task 信息。

---

**📅 最后更新**: 2026-05-07  
**✅ 审计状态**: 已通过第三方架构审计，代码-文档一致性 100%  
**🔒 保护级别**: 核心机制已锁定，禁止未经审计的修改
