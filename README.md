# 🤖 Web Agent

> **基于视觉-DOM双模态的进化型智能网页代理**  
> 具备Set-of-Mark视觉感知、物理坐标降维打击执行、防死循环熔断、以及自我进化能力

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Playwright](https://img.shields.io/badge/playwright-1.40+-green.svg)](https://playwright.dev/)

---

## 📺 演示视频

> **🎬 查看完整演示**: [点击这里观看](./demo/demo.mp4)  
> *(视频展示了Agent自动完成复杂网页任务的全过程)*

---

## ✨ 核心特性

### 🎯 **双模态感知系统**
- **Set-of-Mark (SoM) 视觉标注**: 动态在页面元素上画红框+数字标号,让VLM精准识别交互目标
- **极致压缩的DOM文本**: 将完整DOM树拍平为极简文本格式,单步Token从55K降至5K (节省90%)
- **懒感知机制**: 基于脏标记的智能缓存,本地工具操作时复用缓存,避免无效感知

### 🛡️ **防呆执行系统**
- **2层兜底策略**: 
  1. 首选Playwright Selector (1秒Fail Fast)
  2. 失败后降级为绝对物理坐标点击 (含越界滚动保护)
- **拟人化点击序列**: 0.2秒悬停 + 150ms按压延迟,规避反爬虫检测
- **坐标转换闭环**: 感知层提取绝对物理坐标,执行层动态计算视口相对坐标,防止滚动偏移导致点歪

### 🔥 **智能熔断系统**
- **基于信息熵的死循环检测**: 监控动作熵、状态熵与震荡分数,自动拦截重复无效操作
- **LLM幻觉拦截**: 门面层校验element_id合法性,幻觉时追加红字反馈并重试(最多3次)
- **滚动到底部检测**: 防止Agent在页面底部陷入无限滚动死循环

### 🧠 **自我进化系统**
- **任务成功后自动反思**: 提炼泛化SOP并保存到本地"海马体"
- **相同意图直接复用**: 下次遇到相似任务,直接注入历史成功经验
- **底座纯洁性**: 业务逻辑完全通过动态Skill注入,核心系统保持通用

---

## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                      Workflow (中枢)                         │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ ReAct Loop  │  │ Action Router│  │ Lazy Perception│      │
│  └─────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────┘
           │                    │                    │
           ▼                    ▼                    ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Perception      │  │  Execution       │  │  Tools           │
│  ┌────────────┐  │  │  ┌────────────┐  │  │  ┌────────────┐  │
│  │ SoM Engine │  │  │  │ Actions    │  │  │  │ Local Exec │  │
│  │ (视觉标注)  │  │  │  │ (2层兜底)  │  │  │  │ (本地工具)  │  │
│  └────────────┘  │  │  └────────────┘  │  │  └────────────┘  │
└──────────────────┘  └──────────────────┘  └──────────────────┘
           │                    │                    │
           └────────────────────┼────────────────────┘
                                ▼
                    ┌──────────────────────┐
                    │  LLM Client (门面)    │
                    │  ┌────────────────┐  │
                    │  │ Self-Correction│  │
                    │  │ (幻觉拦截)      │  │
                    │  └────────────────┘  │
                    └──────────────────────┘
                                ▼
                    ┌──────────────────────┐
                    │  Loop Monitor        │
                    │  (死循环熔断)         │
                    └──────────────────────┘
```

---

## 🚀 快速开始

### 1. 环境要求

- Python 3.8+
- macOS / Linux / Windows
- 稳定的网络连接

### 2. 安装依赖

```bash
# 克隆仓库
git clone https://github.com/Hins2329/web-use-agent.git
cd web-use-agent

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 安装Playwright浏览器
playwright install chromium
```

### 3. 配置API密钥

复制 `.env.example` 为 `.env` 并填入你的API密钥:

```bash
cp .env.example .env
```

编辑 `.env` 文件:

```env
# 智谱AI (推荐用于VLM)
ZHIPU_API_KEY="your_zhipu_api_key"

# 小米AI (可选)
XIAOMI_API_KEY="your_xiaomi_api_key"

# Browser Use API (可选)
BROWSER_USE_API_KEY="your_browser_use_api_key"
```

### 4. 运行Agent

**交互式模式**:

```bash
python run_agent.py
```

运行后会出现交互式输入提示：

```
================================================================================
🤖 Web Agent - 交互式模式
================================================================================
💡 输入任务目标开始执行，输入 'quit' 或 'exit' 退出
================================================================================

📝 请输入任务目标: 在淘宝搜索 RTX 5090 并告诉我第一项的价格

[Agent开始执行任务...]
```

**使用说明**:
- 输入任务目标后按回车开始执行
- 任务完成后可继续输入下一个任务
- 输入 `quit`、`exit` 或 `q` 退出程序
- 按 `Ctrl+C` 也可随时退出

---

## 📖 使用示例

### 示例1: 自动搜索商品

```python
from src.agent.workflow.workflow import Workflow
from src.config.settings import AppConfig

config = AppConfig()
workflow = Workflow(config)

await workflow.run_task(
    task="在淘宝搜索'机械键盘',找到价格在500-1000元的商品"
)
```

### 示例2: 注入业务Skill

```python
task_guidance = """
任务: 上架商品到淘宝
步骤:
1. 导航到卖家中心
2. 点击"发布商品"
3. 填写商品信息
4. 上传商品图片
5. 设置价格和库存
6. 提交发布
"""

await workflow.run_task(
    task="上架商品",
    task_guidance=task_guidance
)
```

---

## 🔧 配置说明

主要配置文件: `config.yaml`

```yaml
agent:
  max_steps: 30                    # 最大执行步数
  login_pause_duration: 30         # 登录页面暂停时长(秒)
  
browser:
  headless: false                  # 是否无头模式
  viewport_width: 1280             # 视口宽度
  viewport_height: 720             # 视口高度
  
llm:
  provider: "zhipu"                # LLM提供商
  model: "glm-4-plus"              # 模型名称
  temperature: 0.1                 # 温度参数
  
vlm:
  provider: "zhipu"                # VLM提供商
  model: "glm-4v-plus"             # 视觉模型名称
```

---

## 📄 许可证

本项目采用 [MIT License](./LICENSE)

---

## 📧 联系方式

- **GitHub**: [@Hins2329](https://github.com/Hins2329)
- **Issues**: [提交问题](https://github.com/Hins2329/web-use-agent/issues)

---

<div align="center">

**⭐ 如果这个项目对你有帮助,请给个Star! ⭐**

Made with ❤️ by Hins2329

</div>
