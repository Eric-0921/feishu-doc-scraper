# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- [V3] 开发最终优化版抓取脚本 `copy_page_harvest_v3.py`：
  - 网络超时重试 (最多 3 次)
  - 日志文件输出 (`harvest.log`)
  - Ctrl+C 优雅退出（保存进度后退出）
  - 异常文件报告 (`harvest_report.md`)
  - 全局序号前缀 (`0001_标题.md`)
  - URL 路径分类（自动创建子目录）
- 初始化项目结构 `feishu-doc-scraper`。
- 开发目录侦察脚本 `discover_tree.py`，支持递归展开飞书文档侧边栏。
- 完成飞书开放平台“开发指南”目录全量抓取 (1247 个节点)。
- 生成可视化报告 `toc_report.md` 和机器数据 `structure.json`。
- 配置 GitHub 自动化备份流程。
