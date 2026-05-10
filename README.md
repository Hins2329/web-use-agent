# 🌐 Web-Use-Agent

一个具备自进化记忆能力的 Vision-DOM 多模态网页 Agent。  
给它一个目标——它会自动浏览、阅读、点击并学习。

**Task 1:网页搜索 + 读取本地文件 Q&A**
![Demo](demo.gif)
**Task 2:读取本地文件 -> 自动填写电商表格**
![Demo2](demo2.gif)
---

## ✨ 功能特性

- **网页自动化** —— 搜索、导航、填写表单、执行多步骤网页流程
- **本地 + Web 联动任务** —— 读取本地文件，并根据其内容在网页上执行操作
- **信息检索** —— 查询体育比分、天气、新闻等跨站点信息
- **电商操作** —— 商品搜索、商品发布与表单填写

---

## 🧠 工作原理

### 感知系统：Vision + DOM 双模态
在每一步中，Agent 会对可交互元素添加编号边界框（Set-of-Mark），提取压缩后的 DOM 树，并将带标注的网页截图与结构化文本一起发送给 LLM —— 让模型同时获得页面的视觉视图与结构视图。

### 记忆系统：三层记忆结构
| 层级 | 存储内容 | 持续时间 |
|-------|---------------|----------|
| 长期记忆 | 成功 SOP 与失败模式 | 跨会话持久化 |
| 中期记忆 | TaskState（目标、子目标、里程碑、阻塞信息） | 当前任务 |
| 短期记忆 | 带有 MILESTONE 标记的最近操作 | 当前上下文窗口 |

### 自进化能力
任务成功后，Agent 会反思自己的操作历史，并提炼出可复用 SOP。  
下一次遇到类似目标时，它会自动加载 SOP，跳过探索过程，从而随着使用不断变快。

### 上下文压缩
当上下文窗口接近容量上限（80% 阈值）时，Context Manager 会保留 TaskState 与 MILESTONE 操作，压缩常规步骤，并重建一个更精简但仍保持逻辑一致性的上下文。

### 防循环熔断机制
基于熵值的循环监控器会检测重复动作模式，并在 Agent 陷入死循环前触发回退策略（人工介入或策略切换）。

---

## 🛠️ 技术栈

- **浏览器控制** —— Playwright
- **感知系统** —— Set-of-Mark (SoM) 视觉定位 + DOM 提取
- **LLM 提供商** —— Xiaomi MiMo、Zhipu GLM、Ollama（本地 Qwen3）
- **架构** —— 带有懒感知与 dirty-flag 缓存机制的 ReAct Loop

---

## 🚀 快速开始

```bash
# 安装依赖
pip install -r requirements.txt
playwright install chromium

# 配置模型
cp config.yaml.example config.yaml
# 编辑 config.yaml 并填写 API Key

# 运行
python run_agent.py
```

然后输入任意任务目标：

📝 请输入任务目标: 查询今天NBA比赛结果，读取 note.md 里的留言并回答

---

## 📁 项目结构

```text
src/
├── agent/
│   ├── workflow/      # ReAct Loop、循环监控
│   ├── perception/    # SoM 提取、DOM 解析
│   ├── execution/     # 浏览器操作、坐标系统
│   ├── memory/        # TaskState、ContextManager、SkillManager
│   └── llm/           # 多模型提供商客户端
tools/
└── replay_viewer.py   # 任务步骤回放工具
```

---

## 🔍 回放任意任务

```bash
python tools/replay_viewer.py logs/replay_task_1.jsonl --filter MILESTONE
```

---

## 📌 注意

该项目目前仍处于积极开发阶段。  
`main-dev` 分支包含最新的开发代码。