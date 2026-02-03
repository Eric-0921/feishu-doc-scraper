# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- [DONE] **服务端 API 专项抓取**: 完成了全部 2065 个页面的抓取任务，成功率 99.9% (2063 成功, 2 失败)，历时约 8.5 小时。
- [FIX] **大页面超时优化**: 引入 `domcontentloaded` 策略与 60s 强制超时保护，解决了包含大量内容的页面卡死问题。
- [Feat] **通用目录发现工具**: 开发了 `tools/discover.py`，支持任意飞书文档根路径的自动层级扫描。
- [V5.1] 鲁棒性增强版，支持无人值守长时间抓取：
  - 延时随机性增强：混合使用高斯/均匀/指数/突发四种分布
  - 延时范围扩展：2-15秒（原 1-6秒）
  - 长休息机制：每 80-120 页休息 2-5 分钟
  - 反爬自动应对：验证码检测、HTTP 429 指数退避、连续失败冷却
  - 信号处理：SIGINT/SIGTERM 优雅退出
  - 心跳日志：每 30 秒写入存活状态
  - 专业进度显示：实时统计 OK/FAIL/SKIP，无 emoji
- 通用目录侦察工具 `tools/discover.py`：支持任意飞书文档 URL
- 服务端 API 目录侦察完成（2678 个节点）
- `harvest_new.py` 新增 `--id-range` 参数，支持分批抓取

### Changed

- `core/config.py`: 延时参数调整，新增退避和心跳配置
- `core/behavioral.py`: 重写随机延时算法
- `scrapers/feishu_copy.py`: 重写抓取主逻辑，增加故障恢复

---

## [V5.0] - 2026-02-02 (历史版本)

### Added

- [V4] 开发人类行为模拟版抓取脚本 `copy_page_harvest_v4.py`：
  - 高斯分布延迟（更自然的随机模式）
  - 随机休息停顿（每 5-15 页休息 5-15 秒）
  - 模拟鼠标移动和页面滚动
- 开发教程目录侦察脚本 `discover_tutorial.py`（针对 /document/course）
- 完成开发教程目录抓取（221 个节点，191 个可抓取）
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
