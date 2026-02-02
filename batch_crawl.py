import os
import json
import asyncio
import random
import sys
from pathlib import Path

# 强制挂载本地 crawl4ai 源码
project_root = Path(__file__).parent.absolute()
crawl4ai_src = project_root / "crawl4ai"
if crawl4ai_src.exists():
    sys.path.insert(0, str(crawl4ai_src))
    print(f"DEBUG: Added {crawl4ai_src} to sys.path")

# 配置环境检查
if os.environ.get('CONDA_DEFAULT_ENV') is None:
    pass

# 集成 Crawl4AI
try:
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
except ImportError as e:
    print(f"Error: Crawl4AI not found even with sys.path. {e}")
    sys.exit(1)

async def batch_harvest():
    # 1. 加载目录结构
    structure_path = Path("structure.json")
    if not structure_path.exists():
        print(f"Error: {structure_path} not found. Run discover_tree.py first.")
        return

    with open(structure_path, 'r', encoding='utf-8') as f:
        nodes = json.load(f)

    # 过滤掉没有 URL 的目录节点
    harvest_list = [n for n in nodes if n['url'] and n['url'].startswith('http')]
    
    print(f"Total pages to harvest: {len(harvest_list)}")

    # 2. 定义抓取配置
    run_config = CrawlerRunConfig(
        css_selector=".doc-content", # 飞书文档正文容器
        wait_for=".md-render",      # 等待正文渲染完成
        cache_mode=CacheMode.BYPASS, 
        magic=True                  # 启用智能模式
    )

    # 3. 初始化爬虫
    async with AsyncWebCrawler(verbose=True) as crawler:
        for i, node in enumerate(harvest_list):
            title = node['title'].replace('/', '_').replace('\\', '_') # 安全文件名
            url = node['url']
            
            # 构建保存路径 (简化版，后续可根据 level 构建)
            output_dir = Path("docs")
            output_dir.mkdir(exist_ok=True)
            output_file = output_dir / f"{i:04d}_{title}.md"

            # 断点续传
            if output_file.exists() and output_file.stat().st_size > 0:
                print(f"Skipping {title} (already exists)")
                continue

            print(f"[{i+1}/{len(harvest_list)}] Harvesting: {title} ({url})")

            try:
                # 执行抓取
                # 修正：显式使用 CrawlerRunConfig
                result = await crawler.arun(
                    url=url,
                    config=run_config
                )

                if result.success:
                    # 获取 Markdown
                    # 飞书正文在 result.markdown 中 (Crawl4AI 会根据 css_selector 自动过滤)
                    content = result.markdown
                    
                    if not content or len(content) < 100:
                         # 如果抓取到的内容太短，可能是选择器问题或加载不全
                         print(f"Warning: Content for {title} seems too short ({len(content) if content else 0} chars).")

                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(f"# {node['title']}\n\nSource: {url}\n\n---\n\n")
                        f.write(content)
                    print(f"Successfully saved to {output_file} (Length: {len(content)})")
                else:
                    print(f"Failed to crawl {url}: {result.error_message}")

            except Exception as e:
                print(f"Error harvesting {url}: {e}")

            # 随机延迟，防止被封
            await asyncio.sleep(random.uniform(1, 3))

            # 试运行限制 (用户规则：大任务必须先试运行)
            if i >= 4: # 只抓 5 篇试运行
                print("\n[Trial Run] Finished 5 pages. Please check the 'docs' directory.")
                break

if __name__ == "__main__":
    asyncio.run(batch_harvest())
