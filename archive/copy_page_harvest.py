#!/usr/bin/env python3
"""
飞书文档官方 Markdown 抓取器 (基于"复制页面"按钮)

策略：
1. 读取 structure.json
2. 使用 Playwright 打开每个文档页面
3. 点击"复制页面"按钮获取官方 Markdown
4. 从剪贴板读取内容并保存到本地

优势：
- 使用飞书官方提供的 Markdown 导出功能
- 质量远超第三方 HTML 转换
"""
import os
import sys
import json
import asyncio
import random
from pathlib import Path

# 环境检查（遵守全局规则）
if os.environ.get('CONDA_DEFAULT_ENV') is None:
    pass  # 调试时跳过

from playwright.async_api import async_playwright

async def copy_page_harvest(limit: int = 5):
    """
    使用官方"复制页面"按钮抓取 Markdown
    
    Args:
        limit: 试运行页面数量限制 (设为 0 表示全量)
    """
    # 1. 加载目录结构
    structure_path = Path("structure.json")
    if not structure_path.exists():
        print(f"Error: {structure_path} not found. Run discover_tree.py first.")
        return

    with open(structure_path, 'r', encoding='utf-8') as f:
        nodes = json.load(f)

    # 过滤掉没有 URL 的目录节点
    harvest_list = [n for n in nodes if n.get('url') and n['url'].startswith('http')]
    
    if limit > 0:
        harvest_list = harvest_list[:limit]
        print(f"[Trial Run] Limiting to {limit} pages.")
    
    print(f"Total pages to harvest: {len(harvest_list)}")
    
    # 确保输出目录存在
    output_dir = Path("docs")
    output_dir.mkdir(exist_ok=True)

    # 2. 启动 Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False) # 非无头模式方便调试
        context = await browser.new_context()
        # 授权剪贴板访问
        page = await context.new_page()
        
        success_count = 0
        fail_count = 0
        
        for i, node in enumerate(harvest_list):
            title = node['title'].replace('/', '_').replace('\\', '_').replace(':', '_')
            url = node['url']
            output_file = output_dir / f"{i:04d}_{title}.md"
            
            # 断点续传
            if output_file.exists() and output_file.stat().st_size > 100:
                print(f"Skipping {title} (already exists)")
                continue
            
            print(f"[{i+1}/{len(harvest_list)}] Harvesting: {title}")
            
            try:
                # 打开页面
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_selector(".doc-content", timeout=10000)
                
                # 等待页面稳定
                await asyncio.sleep(1)
                
                # 找到并点击"复制页面"按钮
                # 飞书的复制按钮通常在右上角，包含"复制页面"文字
                copy_btn = page.locator('button:has-text("复制页面")')
                
                if await copy_btn.count() > 0:
                    await copy_btn.first.click()
                    await asyncio.sleep(0.5) # 等待剪贴板填充
                    
                    # 从剪贴板获取内容
                    clipboard_content = await page.evaluate("navigator.clipboard.readText()")
                    
                    if clipboard_content and len(clipboard_content) > 50:
                        with open(output_file, 'w', encoding='utf-8') as f:
                            f.write(f"# {node['title']}\n\n")
                            f.write(f"Source: {url}\n\n---\n\n")
                            f.write(clipboard_content)
                        print(f"  ✓ Saved to {output_file} ({len(clipboard_content)} chars)")
                        success_count += 1
                    else:
                        print(f"  ✗ Clipboard content too short or empty")
                        fail_count += 1
                else:
                    # 如果没有"复制页面"按钮，尝试其他方式（如 Ctrl+A, Ctrl+C）
                    print(f"  ⚠ No '复制页面' button found, trying fallback...")
                    # Fallback: 选中正文并复制
                    await page.locator(".doc-content").click()
                    await page.keyboard.press("Control+a")
                    await page.keyboard.press("Control+c")
                    await asyncio.sleep(0.5)
                    clipboard_content = await page.evaluate("navigator.clipboard.readText()")
                    
                    if clipboard_content and len(clipboard_content) > 50:
                        with open(output_file, 'w', encoding='utf-8') as f:
                            f.write(f"# {node['title']}\n\n")
                            f.write(f"Source: {url}\n\n---\n\n")
                            f.write(clipboard_content)
                        print(f"  ✓ Saved (fallback) to {output_file}")
                        success_count += 1
                    else:
                        print(f"  ✗ Fallback also failed")
                        fail_count += 1
                
            except Exception as e:
                print(f"  ✗ Error: {e}")
                fail_count += 1
            
            # 随机延迟
            await asyncio.sleep(random.uniform(1, 2))
        
        await browser.close()
        
    print(f"\n=== Summary ===")
    print(f"Success: {success_count}")
    print(f"Failed: {fail_count}")

if __name__ == "__main__":
    # 默认试运行 5 个页面
    asyncio.run(copy_page_harvest(limit=5))
