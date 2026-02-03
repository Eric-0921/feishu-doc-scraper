#!/usr/bin/env python3
"""
飞书通用目录侦察工具 (Generic Discovery Tool)

功能：递归展开侧边栏，提取目录结构，支持通过 URL 指定任意文档板块。
用法：python tools/discover.py --url <URL> [--output <name>]

作者: AI Assistant
"""
import asyncio
import json
import logging
import os
import random
import argparse
import sys
from pathlib import Path
from playwright.async_api import async_playwright

# 添加父目录到路径以便导入 core (如果需要，目前是独立的)
sys.path.append(str(Path(__file__).parent.parent))

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def expand_all_nodes(page):
    """
    递归展开所有折叠节点
    精准策略：通过 CSS transform 属性判断折叠状态
    """
    logger.info("开始展开所有节点...")
    iteration = 0
    max_retries = 3
    no_change_count = 0
    
    while True:
        iteration += 1
        
        # 获取所有折叠的节点索引
        collapsed_indices = await page.evaluate("""
            () => {
                const btns = Array.from(document.querySelectorAll('.ud__expandButton'));
                const collapsedIdx = [];
                btns.forEach((btn, index) => {
                    const icon = btn.querySelector('.ud__expandButton__icon');
                    if (icon) {
                        const style = window.getComputedStyle(icon);
                        if (style.transform && style.transform.includes('matrix(0, -1, 1, 0, 0, 0)')) {
                            collapsedIdx.push(index);
                        }
                    }
                });
                return collapsedIdx;
            }
        """)
        
        if not collapsed_indices:
            no_change_count += 1
            if no_change_count >= max_retries:
                logger.info("没有更多折叠节点了。")
                break
            logger.info("未发现折叠节点，等待后重试...")
            await page.wait_for_timeout(1000)
            continue
            
        no_change_count = 0
        logger.info(f"第 {iteration} 轮：发现 {len(collapsed_indices)} 个折叠节点，正在展开...")
        
        buttons = await page.query_selector_all(".ud__expandButton")
        
        clicked_count = 0
        for idx in collapsed_indices:
            if idx < len(buttons):
                btn = buttons[idx]
                try:
                    if await btn.is_visible():
                        await btn.click()
                        clicked_count += 1
                        await page.wait_for_timeout(random.randint(50, 150))
                except Exception as e:
                    logger.warning(f"点击按钮失败 (索引 {idx}): {e}")
        
        if clicked_count == 0:
            logger.info("没有可点击的按钮，停止展开。")
            break
            
        await page.wait_for_timeout(2000)


async def discover(url: str, output_name: str):
    """
    主侦察函数
    """
    # 确定输出路径
    base_dir = Path(__file__).parent.parent
    config_dir = base_dir / "configs"
    log_dir = base_dir / "logs"
    
    config_dir.mkdir(exist_ok=True)
    log_dir.mkdir(exist_ok=True)
    
    output_file = config_dir / f"{output_name}_structure.json"
    report_file = log_dir / f"{output_name}_toc_report.md"
    
    logger.info(f"目标 URL: {url}")
    logger.info(f"输出文件: {output_file}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        logger.info(f"正在导航...")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            logger.error(f"导航失败: {e}")
            await browser.close()
            return
        
        try:
            await page.wait_for_selector(".ud__tree", timeout=20000)
            logger.info("侧边栏加载成功。")
        except Exception:
            logger.error("侧边栏未找到！可能页面结构不同或加载超时。")
            await browser.close()
            return

        # 递归展开
        await expand_all_nodes(page)
        
        # 提取最终结构
        logger.info("正在提取目录结构...")
        
        nodes = await page.query_selector_all(".ud__tree__node")
        structure = []
        
        for i, node in enumerate(nodes):
            title_el = await node.query_selector(".ud__tree__node__label") 
            title = await title_el.inner_text() if title_el else "Unknown"
            
            # 获取链接
            try:
                # 显式使用 evaluate 获取 href，如果不存在则返回 null
                node_url = await node.evaluate("node => node.closest('a') ? node.closest('a').href : null")
            except Exception as e:
                logger.warning(f"获取链接失败 (node {i}): {e}")
                node_url = None
            
            has_expand = await node.query_selector(".ud__expandButton")
            is_folder = has_expand is not None
            
            # 尝试推断层级
            level = 0
            try:
                header = await node.query_selector(".ud__tree__node-header") or node
                style = await header.get_attribute("style")
                if style and "padding-left" in style:
                    parts = style.split("padding-left:")
                    if len(parts) > 1:
                        px_val = parts[1].split("px")[0].strip()
                        level = int(float(px_val)) // 20 
            except:
                pass

            node_data = {
                "id": i,
                "title": title.strip(),
                "url": node_url,
                "level": level,
                "is_folder": is_folder,
            }
            structure.append(node_data)
            
        logger.info(f"共找到 {len(structure)} 个节点")
        
        # 保存 JSON
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(structure, f, indent=2, ensure_ascii=False)
        logger.info(f"结构已保存到 {output_file}")
            
        # 生成报告
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(f"# 目录结构报告: {output_name}\n\n")
            f.write(f"**生成时间**: {os.popen('date').read().strip()}\n")
            f.write(f"**源 URL**: {url}\n")
            f.write(f"**总节点数**: {len(structure)}\n\n")
            f.write("| ID | 层级 | 标题 | 类型 | URL |\n")
            f.write("|---|---|---|---|---|\n")
            for node in structure:
                type_icon = "📂" if node['is_folder'] else "📄"
                indent = "&nbsp;&nbsp;" * min(node['level'], 10)
                url_display = node['url'] or '-'
                f.write(f"| {node['id']} | {node['level']} | {indent}{type_icon} {node['title']} | {'文件夹' if node['is_folder'] else '文档'} | {url_display} |\n")
        
        logger.info(f"报告已生成: {report_file}")
        await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="飞书通用目录侦察工具")
    parser.add_argument("--url", type=str, required=True, help="目标页面 URL")
    parser.add_argument("--output", type=str, default="custom", help="输出文件名前缀 (默认: custom -> custom_structure.json)")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(discover(args.url, args.output))
    except KeyboardInterrupt:
        print("\n🛑 用户中断程序")
