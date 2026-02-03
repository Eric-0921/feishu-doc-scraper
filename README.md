# 飞书开放平台文档抓取器 (Feishu Doc Scraper)

本项目用于自动化抓取飞书开放平台文档，并将其转换为保留原始目录结构的 Markdown 知识库。

## 项目架构 (V5.1 鲁棒性增强版)

项目采用了模块化分层架构，支持多栏目扩展和无人值守长时间运行：

```text
feishu-doc-scraper/
├── configs/               # 任务配置与目录结构
│   ├── guide_structure.json      # 开发指南目录 (999 节点)
│   ├── tutorial_structure.json   # 开发教程目录 (191 节点)
│   └── server_api_structure.json # [NEW] 服务端 API 目录 (2678 节点)
├── core/                  # 核心框架层
│   ├── browser.py         # Playwright 管理与反检测
│   ├── behavioral.py      # 人类行为模拟 (混合随机分布)
│   ├── state.py           # 状态管理 (断点续抓)
│   ├── utils.py           # 通用工具函数
│   ├── logger.py          # 日志管理
│   └── config.py          # 全局配置 (延时/退避/心跳)
├── docs/                  # 输出文档库
│   ├── development-guide/ # 开发指南文档 (已完成)
│   ├── tutorial/          # 开发教程文档 (已完成)
│   └── server_api/        # [NEW] 服务端 API 文档
├── scrapers/              # 业务逻辑层
│   └── feishu_copy.py     # 基于"复制页面"按钮的抓取实现
├── tools/                 # [NEW] 独立工具
│   └── discover.py        # 通用目录侦察工具
├── archive/               # 历史版本归档 (v1-v4)
├── logs/                  # 运行日志与状态文件
└── harvest_new.py         # 统一入口脚本
```

## 快速开始

### 1. 环境准备

```bash
conda activate feishu-scraper
pip install playwright tqdm
playwright install chromium
```

### 2. 运行抓取任务

**抓取服务端 API (2678 页)**

```bash
# 全量抓取
python harvest_new.py --structure configs/server_api_structure.json

# 分批抓取 (按 ID 范围)
python harvest_new.py --structure configs/server_api_structure.json --id-range 0-1000

# 试运行 (前 10 页)
python harvest_new.py --structure configs/server_api_structure.json --limit 10
```

> 输出目录：`docs/server_api/`
> 状态记录：`logs/server_api_state.json`

**抓取开发教程 (191 页)**

```bash
python harvest_new.py --structure configs/tutorial_structure.json
```

### 3. 目录侦察 (发现新栏目)

```bash
python tools/discover.py --url "https://open.feishu.cn/document/xxx" --output new_section
```

> 输出：`configs/new_section_structure.json` + `logs/new_section_toc_report.md`

## 核心特性

### 鲁棒性增强 (V5.1)

- **混合随机延时**: 高斯/均匀/指数/突发四种分布组合，2-15秒范围
- **智能休息**: 短休息 (8-20页/15-45秒) + 长休息 (80-120页/2-5分钟)
- **反爬自动应对**: 验证码检测、HTTP 429 指数退避、连续失败冷却
- **优雅退出**: SIGINT/SIGTERM 信号处理，完成当前页后安全退出
- **心跳日志**: 每 30 秒写入 `logs/heartbeat.log`，便于监控

### 基础能力

- **断点续抓**: 状态持久化到 JSON，随时中断随时继续
- **自动分类**: 根据 URL 路径自动构建层级目录
- **权限自动化**: 自动处理剪贴板读取请求

## 抓取进度

| 栏目       | 节点数 | 状态   |
| ---------- | ------ | ------ |
| 开发指南   | 999    | 已完成 |
| 开发教程   | 191    | 已完成 |
| 服务端 API | 2678   | 进行中 |

---

## 历史版本说明

V1-V4 的脚本已归档至 `archive/` 目录，包括：

- `copy_page_harvest_v1.py` - 初版
- `copy_page_harvest_v2.py` - 增加重试
- `copy_page_harvest_v3.py` - 增加日志和报告
- `copy_page_harvest_v4.py` - 增加人类行为模拟
- `discover_tree.py` - 原开发指南侦察脚本
- `discover_tutorial.py` - 原教程侦察脚本
