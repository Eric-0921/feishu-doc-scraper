#!/usr/bin/env python3
"""
飞书开发教程目录侦察脚本

目标：https://open.feishu.cn/document/course
功能：递归展开侧边栏，提取所有教程节点的标题和 URL

输出：
- tutorial_structure.json: 机器可读数据
- tutorial_toc_report.md: 人工核对报告

作者: AI Assistant
最后更新: 2026-02-03
"""
import asyncio
import json
import logging
import os
import random
from pathlib import Path
from playwright.async_api import async_playwright

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============ 配置 ============
TARGET_URL = "https://open.feishu.cn/document/course"
OUTPUT_FILE = Path("tutorial_structure.json")
REPORT_FILE = Path("tutorial_toc_report.md")


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


async def discover_tutorial():
    """
    主侦察函数
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        logger.info(f"正在导航到 {TARGET_URL}")
        await page.goto(TARGET_URL)
        
        try:
            await page.wait_for_selector(".ud__tree", timeout=15000)
            logger.info("侧边栏加载成功。")
        except Exception:
            logger.error("侧边栏未找到！")
            await browser.close()
            return

        # 递归展开
        await expand_all_nodes(page)
        
        # 提取最终结构
        logger.info("正在提取教程目录结构...")
        
        nodes = await page.query_selector_all(".ud__tree__node")
        structure = []
        
        for i, node in enumerate(nodes):
            title_el = await node.query_selector(".ud__tree__node__label") 
            title = await title_el.inner_text() if title_el else "Unknown"
            
            url = await node.evaluate("node => node.closest('a') ? node.closest('a').href : null")
            
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
                "url": url,
                "level": level,
                "is_folder": is_folder,
            }
            structure.append(node_data)
            
        logger.info(f"共找到 {len(structure)} 个教程节点")
        
        # 保存 JSON
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(structure, f, indent=2, ensure_ascii=False)
        logger.info(f"结构已保存到 {OUTPUT_FILE}")
            
        # 生成报告
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write("# 飞书开发教程目录结构验收报告\n\n")
            f.write(f"**生成时间**: {os.popen('date').read().strip()}\n")
            f.write(f"**总节点数**: {len(structure)}\n\n")
            f.write("| ID | 层级 | 标题 | 类型 | URL |\n")
            f.write("|---|---|---|---|---|\n")
            for node in structure:
                type_icon = "📂" if node['is_folder'] else "📄"
                indent = "&nbsp;&nbsp;" * min(node['level'], 10)
                url_display = node['url'] or '-'
                f.write(f"| {node['id']} | {node['level']} | {indent}{type_icon} {node['title']} | {'文件夹' if node['is_folder'] else '文档'} | {url_display} |\n")
        
        logger.info(f"报告已生成: {REPORT_FILE}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(discover_tutorial())
