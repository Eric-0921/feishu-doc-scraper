# Feishu Documentation Scraper

自动化抓取飞书开放平台文档并转换为 Markdown 知识库。

## 🎯 当前进度

- [x] Phase 1: 目录结构侦察 (完成，共 1247 个节点)
- [ ] Phase 2: 批量内容抓取 (待开始)

## 🛠 开发环境

- Python 3.x
- Playwright (侧边栏展开)
- Crawl4AI (正文提取)

## 📁 关键文件

- `discover_tree.py`: 目录侦察工具。
- `structure.json`: 侦察到的完整目录树结构。
- `toc_report.md`: 可视化验收报告。
