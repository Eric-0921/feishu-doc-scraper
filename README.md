# 飞书开放平台文档抓取器 (Feishu Doc Scraper)

本项目用于自动化抓取飞书开放平台文档，并将其转换为保留原始目录结构的 Markdown 知识库。

## 🏗️ 项目架构 (V5 重构版)

项目采用了模块化分层架构，旨在支持多栏目扩展和长期维护：

```text
feishu-doc-scraper/
├── configs/               # 任务配置与目录结构
│   ├── guide_structure.json    # 开发指南目录结构
│   └── tutorial_structure.json # 开发教程目录结构
├── core/                  # 核心框架层
│   ├── browser.py         # Playwright 管理与反检测
│   ├── behavioral.py      # 人类行为模拟 (随机延迟/鼠标模拟)
│   ├── state.py           # 状态管理 (断点续抓)
│   ├── utils.py           # 通用工具函数
│   ├── logger.py          # 日志管理
│   └── config.py          # 全局配置
├── docs/                  # 输出文档库
│   ├── development-guide/ # 开发指南文档 (已归档)
│   └── tutorial/          # [NEW] 开发教程文档
├── scrapers/              # 业务逻辑层
│   └── feishu_copy.py     # 基于"复制页面"按钮的抓取实现
└── harvest_new.py         # 统一入口脚本
```

## 🚀 快速开始

### 1. 环境准备

确保已安装 Conda 环境：

```bash
conda activate feishu-scraper
# 如果是新环境，安装依赖
pip install playwright tqdm
playwright install chromium
```

### 2. 运行抓取任务

**示例 A：抓取“开发教程” (新任务)**

```bash
python harvest_new.py --structure configs/tutorial_structure.json
```

> 输出目录：`docs/tutorial/`
> 状态记录：`logs/tutorial_state.json`

**示例 B：抓取“开发指南” (旧任务复现)**

```bash
python harvest_new.py --structure configs/guide_structure.json --limit 5
```

> 输出目录：`docs/guide/` (如果不指定)
> _注：由于历史原因，之前抓取的 999 个文件已归档在 `docs/development-guide/`_

## ✅ 核心特性

- **人类行为模拟**: 高斯分布随机延迟、随机休息、鼠标轨迹模拟。
- **断点续抓**: 自动记录成功/失败/跳过的页面，随时中断随时继续。
- **自动分类**: 根据 URL 路径自动构建层级目录。
- **权限自动化**: 自动处理剪贴板读取请求。
