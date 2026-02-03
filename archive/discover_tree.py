import asyncio
import json
import logging
from playwright.async_api import async_playwright
import os
import random

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TARGET_URL = "https://open.feishu.cn/document/client-docs/intro"
OUTPUT_FILE = "structure.json"
REPORT_FILE = "toc_report.md"

async def expand_all_nodes(page):
    """
    递归展开所有折叠节点
    精准策略：通过 .ud__expandButton__icon 的 transform 属性判断折叠状态
    折叠状态: transform: rotate(-90deg) -> computed: matrix(0, -1, 1, 0, 0, 0)
    展开状态: transform: none
    """
    logger.info("Starting to expand all nodes...")
    iteration = 0
    max_retries = 3  # 如果连续没有新节点，重试几次以防万一
    no_change_count = 0
    
    while True:
        iteration += 1
        
        # 获取所有 expand button 的 icon
        # 注意：我们需要 evalute 所有的 icon 状态
        # 因为 evaluate_all 可能较慢，我们尝试一种混合方法
        
        # 定义一个 JS 函数一次性获取所有未展开的 button index
        collapsed_indices = await page.evaluate("""
            () => {
                const btns = Array.from(document.querySelectorAll('.ud__expandButton'));
                const collapsedIdx = [];
                btns.forEach((btn, index) => {
                    // Check icon transform
                    const icon = btn.querySelector('.ud__expandButton__icon');
                    if (icon) {
                        const style = window.getComputedStyle(icon);
                        // Convert matrix to check rotation
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
                logger.info("No more collapsed nodes found after retries.")
                break
            logger.info("No collapsed nodes found, waiting and checking again...")
            await page.wait_for_timeout(1000)
            continue
            
        no_change_count = 0 # reset
        logger.info(f"Iteration {iteration}: Found {len(collapsed_indices)} collapsed nodes. Expanding...")
        
        # 重新获取最新的 buttons (因为 DOM 可能变化)
        buttons = await page.query_selector_all(".ud__expandButton")
        
        clicked_count = 0
        for idx in collapsed_indices:
            if idx < len(buttons):
                btn = buttons[idx]
                try:
                    if await btn.is_visible():
                        await btn.click()
                        clicked_count += 1
                        # 稍微等待动画，太快可能导致点击无效
                        await page.wait_for_timeout(random.randint(50, 150))
                except Exception as e:
                    logger.warning(f"Failed to click button at index {idx}: {e}")
        
        if clicked_count == 0:
            logger.info("No buttons were clickable. Stopping expansion.")
            break
            
        # 等待重绘
        await page.wait_for_timeout(2000)

async def discover_tree():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) # 可以设为 False 观察过程
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        logger.info(f"Navigating to {TARGET_URL}")
        await page.goto(TARGET_URL)
        
        try:
            await page.wait_for_selector(".ud__tree", timeout=15000)
            logger.info("Sidebar loaded successfully.")
        except Exception:
            logger.error("Sidebar not found!")
            await browser.close()
            return

        # 递归展开
        await expand_all_nodes(page)
        
        # 提取最终结构
        logger.info("Extracting final directory structure...")
        
        # 获取所有可见节点
        nodes = await page.query_selector_all(".ud__tree__node")
        structure = []
        
        for i, node in enumerate(nodes):
            # 获取标题: 在 .ud__tree__node 内部的 .ud__tree__node__label
            title_el = await node.query_selector(".ud__tree__node__label") 
            title = await title_el.inner_text() if title_el else "Unknown"
            
            # 获取链接: 检查 .ud__tree__node 的祖先是否有 <a>
            # 使用 evaluate 在浏览器端执行 closest 查找
            url = await node.evaluate("node => node.closest('a') ? node.closest('a').href : null")
            
            # 判断类型：如果有 expandButton 或者是纯文本 label (无 URL)，则是 目录
            # 即使是文件夹，飞书有时也会包裹 a 标签但 href 可能为空或指向自身
            # 我们主要看是否有 expandButton
            has_expand = await node.query_selector(".ud__expandButton")
            
            # 修正判定：如果 url 为空，肯定是文件夹；如果有 expandButton，也是文件夹（包含子级）
            # 注意：飞书有些节点既有内容（有 URL）又有子级（有 expandButton）
            is_folder = has_expand is not None
            
            # 尝试推断 Level（根据 DOM 嵌套或 padding）
            level = 0
            try:
                # 获取包含 padding 的元素
                header = await node.query_selector(".ud__tree__node-header") or node
                style = await header.get_attribute("style")
                if style and "padding-left" in style:
                    # style="padding-left: 20px;"
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
                "path": title.strip() 
            }
            structure.append(node_data)
            
        logger.info(f"Total nodes found: {len(structure)}")
        
        # 保存
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(structure, f, indent=2, ensure_ascii=False)
            
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write(f"# 飞书文档目录结构验收报告\n\n")
            f.write(f"**生成时间**: {os.popen('date').read().strip()}\n")
            f.write(f"**总节点数**: {len(structure)}\n\n")
            f.write(f"| ID | 层级估算 | 标题 | 类型 | URL |\n")
            f.write(f"|---|---|---|---|---|\n")
            for node in structure:
                type_icon = "📂" if node['is_folder'] else "📄"
                indent = "&nbsp;&nbsp;" * (node['level'] if node['level'] < 10 else 0)
                f.write(f"| {node['id']} | {node['level']} | {indent}{type_icon} {node['title']} | {node['is_folder']} | {node['url'] or '-'} |\n")
        
        logger.info(f"Done. Check {REPORT_FILE}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(discover_tree())
