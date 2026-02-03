import asyncio
import time
from pathlib import Path
from typing import Optional

from core.state import HarvestState
from core.config import ScraperConfig
from core.browser import BrowserManager
from core.behavioral import HumanBehavior
from core.utils import url_to_folder_path, safe_filename
from core.logger import setup_logger

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

class FeishuCopyScraper:
    def __init__(self, config: ScraperConfig, state_file: Path, report_file: Path):
        self.config = config
        self.state = HarvestState(state_file)
        self.report_file = report_file
        self.logger = setup_logger("FeishuScraper", config.LOG_DIR / "scraper.log")
        self.human = HumanBehavior(config)
        self.browser_manager = BrowserManager()
        self.page = None
        self.shutdown_requested = False

    async def run(self, harvest_list: list):
        """主运行循环"""
        self.logger.info("启动抓取任务...")
        
        # 建立目录
        self.config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        try:
            self.page = await self.browser_manager.start()
            self.state.start_time = time.time()
            
            # 过滤待抓取列表
            pending_list = [n for n in harvest_list if not self.state.is_done(n.get('url'))]
            total = len(harvest_list)
            
            if not pending_list:
                self.logger.info("🎉 所有页面已抓取完成！")
                return

            # 初始化进度条
            progress = tqdm(pending_list, unit="页") if tqdm else pending_list
            pages_since_break = 0

            for i, node in enumerate(progress):
                if self.shutdown_requested:
                    break

                # 提取任务信息
                title = node.get('title', 'Unknown')
                url = node.get('url')
                node_id = node.get('id', i)
                
                if tqdm:
                    progress.set_postfix_str(f"当前: {title[:15]}...")

                # 准备输出路径
                folder_path = url_to_folder_path(url)
                output_folder = self.config.OUTPUT_DIR / folder_path
                output_folder.mkdir(parents=True, exist_ok=True)
                
                safe_title = safe_filename(title)
                output_file = output_folder / f"{node_id:04d}_{safe_title}.md"

                # 检查文件存在跳过
                if output_file.exists() and output_file.stat().st_size > 100:
                    self.state.mark_skipped(url)
                    continue

                # 执行单页抓取
                success = await self._process_page(url, output_file, title)
                
                if success:
                    self.state.mark_completed(url, output_file.stat().st_size)
                else:
                    self.state.mark_failed(url)

                # 休息策略
                pages_since_break += 1
                if self.human.should_take_break(pages_since_break):
                    duration = self.human.get_break_duration()
                    if tqdm: progress.write(f"  ☕ 休息 {duration:.1f} 秒...")
                    await asyncio.sleep(duration)
                    pages_since_break = 0
                else:
                    await asyncio.sleep(self.human.random_delay())

        finally:
            await self.browser_manager.close()
            self._generate_report(harvest_list)

    async def _process_page(self, url: str, output_file: Path, title: str) -> bool:
        """单页处理逻辑"""
        for retry in range(self.config.MAX_RETRIES):
            try:
                await self.page.goto(url, wait_until="networkidle", timeout=self.config.TIMEOUT)
                await self.human.simulate_interaction(self.page)
                
                # 检测反爬
                content = await self.page.content()
                if any(kw in content.lower() for kw in self.config.ANTI_BOT_KEYWORDS):
                    action = await self.browser_manager.wait_for_user_resume()
                    if action == 'quit':
                        self.shutdown_requested = True
                        return False
                    elif action == 'skip':
                        return False
                
                # 核心抓取逻辑：寻找“复制页面”按钮
                copy_btn = self.page.locator('button:has-text("复制页面")')
                if await copy_btn.count() > 0:
                    await copy_btn.first.click()
                    await asyncio.sleep(0.5)
                    text = await self.page.evaluate("navigator.clipboard.readText()")
                else:
                    # 备选方案：全选复制
                    await self.page.locator(".doc-content").click()
                    await self.page.keyboard.press("Control+a")
                    await self.page.keyboard.press("Control+c")
                    await asyncio.sleep(0.5)
                    text = await self.page.evaluate("navigator.clipboard.readText()")
                
                if text and len(text) > 50:
                    content = f"# {title}\n\n> Source: {url}\n\n---\n\n{text}"
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                    return True
                
            except Exception as e:
                self.logger.warning(f"重试 {retry+1}/{self.config.MAX_RETRIES} {title}: {str(e)[:50]}")
                await asyncio.sleep(2)
        
        return False

    def _generate_report(self, harvest_list):
        """生成简单报告"""
        with open(self.report_file, 'w', encoding='utf-8') as f:
            f.write(f"# 抓取报告\n\n已完成: {len(self.state.completed)}\n失败: {len(self.state.failed)}\n")
