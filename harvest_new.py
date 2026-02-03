#!/usr/bin/env python3
import argparse
import asyncio
import json
import sys
from pathlib import Path

# 添加当前目录到 path 以便导入 core
sys.path.append(str(Path(__file__).parent))

from core.config import ScraperConfig
from scrapers.feishu_copy import FeishuCopyScraper

async def main():
    parser = argparse.ArgumentParser(description="飞书文档抓取器 V5 (架构重构版)")
    parser.add_argument("--structure", type=str, required=True, help="目录结构文件路径 (例如: configs/tutorial_structure.json)")
    parser.add_argument("--limit", type=int, default=0, help="限制抓取页面数 (0=全量)")
    parser.add_argument("--output-dir", type=str, default=None, help="自定义输出目录名 (默认根据 structure 文件名自动生成)")
    
    args = parser.parse_args()
    
    # 初始化配置
    config = ScraperConfig()
    
    # 路径处理
    structure_path = Path(args.structure)
    if not structure_path.exists():
        print(f"❌ 错误: 找不到结构文件 {structure_path}")
        sys.exit(1)
        
    # 动态确定输出目录和状态文件名
    # 例如 guide_structure.json -> guide
    task_name = structure_path.stem.replace('_structure', '')
    
    # 如果指定了 output-dir，优先级最高；否则根据 task_name 自动在 docs/ 下创建
    if args.output_dir:
        config.OUTPUT_DIR = Path(args.output_dir)
    else:
        # e.g., docs/tutorial
        config.OUTPUT_DIR = config.BASE_DIR / "docs" / task_name
    
    # 状态文件放在 logs/ 下，避免污染根目录
    state_file = config.LOG_DIR / f"{task_name}_state.json"
    report_file = config.LOG_DIR / f"{task_name}_report.md"
    
    print(f"🚀 启动任务: {task_name}")
    print(f"📂 输出目录: {config.OUTPUT_DIR}")
    print(f"📝 状态文件: {state_file}")
    
    # 加载任务列表
    with open(structure_path, 'r', encoding='utf-8') as f:
        nodes = json.load(f)
        
    # 过滤有效 URL
    harvest_list = [n for n in nodes if n.get('url') and n['url'].startswith('http')]
    
    if args.limit > 0:
        harvest_list = harvest_list[:args.limit]
        print(f"⚠️  测试模式限制: 仅抓取前 {args.limit} 页")
    
    # 启动抓取器
    scraper = FeishuCopyScraper(config, state_file, report_file)
    await scraper.run(harvest_list)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 用户中断程序")
