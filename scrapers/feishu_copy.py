"""
飞书文档抓取器 - 增强鲁棒性版本
支持无人值守长时间运行
"""
import asyncio
import signal
import time
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

from core.state import HarvestState
from core.config import ScraperConfig
from core.browser import BrowserManager
from core.behavioral import HumanBehavior
from core.utils import url_to_folder_path, safe_filename
from core.logger import setup_logger


class ProgressDisplay:
    """专业进度显示器 - 无 emoji，显示真实信息"""
    
    def __init__(self, total: int, logger):
        self.total = total
        self.logger = logger
        self.completed = 0
        self.failed = 0
        self.skipped = 0
        self.start_time = time.time()
        self.last_success_time = time.time()
        self.current_page = ""
        
    def update(self, title: str, status: str = "processing"):
        """更新当前处理状态"""
        self.current_page = title[:40]
        if status == "success":
            self.completed += 1
            self.last_success_time = time.time()
        elif status == "failed":
            self.failed += 1
        elif status == "skipped":
            self.skipped += 1
    
    def get_stats(self) -> str:
        """获取统计信息字符串"""
        elapsed = time.time() - self.start_time
        done = self.completed + self.failed + self.skipped
        remaining = self.total - done
        
        # 计算速率和预计剩余时间
        if self.completed > 0:
            rate = elapsed / self.completed
            eta_seconds = remaining * rate
            eta_str = str(timedelta(seconds=int(eta_seconds)))
        else:
            rate = 0
            eta_str = "calculating..."
        
        elapsed_str = str(timedelta(seconds=int(elapsed)))
        
        return (
            f"[{done}/{self.total}] "
            f"OK:{self.completed} FAIL:{self.failed} SKIP:{self.skipped} | "
            f"Elapsed:{elapsed_str} ETA:{eta_str} | "
            f"{self.current_page}"
        )
    
    def print_progress(self):
        """打印进度行（覆盖式）"""
        stats = self.get_stats()
        # 使用 \r 实现覆盖式更新
        sys.stdout.write(f"\r{stats[:120]:<120}")
        sys.stdout.flush()
    
    def print_line(self, message: str):
        """打印独立行信息"""
        # 先清除当前行，再打印新行
        sys.stdout.write(f"\r{' '*120}\r")
        print(message)


class FeishuCopyScraper:
    """飞书文档抓取器 - 增强鲁棒性版本"""
    
    def __init__(self, config: ScraperConfig, state_file: Path, report_file: Path):
        self.config = config
        self.state = HarvestState(state_file)
        self.report_file = report_file
        self.logger = setup_logger("FeishuScraper", config.LOG_DIR / "scraper.log")
        self.human = HumanBehavior(config)
        self.browser_manager = BrowserManager()
        self.page = None
        self.shutdown_requested = False
        self.progress: Optional[ProgressDisplay] = None
        
        # 退避状态
        self.consecutive_failures = 0
        self.backoff_time = config.BACKOFF_INITIAL
        
        # 心跳
        self.last_heartbeat = time.time()
        
        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """优雅退出：接收信号后完成当前页面再退出"""
        self.progress.print_line(f"[SIGNAL] Received {signum}, finishing current page...")
        self.shutdown_requested = True

    def _write_heartbeat(self):
        """写入心跳日志"""
        now = time.time()
        if now - self.last_heartbeat >= self.config.HEARTBEAT_INTERVAL:
            heartbeat_file = self.config.LOG_DIR / "heartbeat.log"
            with open(heartbeat_file, 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now().isoformat()} | {self.progress.get_stats()}\n")
            self.last_heartbeat = now

    async def run(self, harvest_list: list):
        """主运行循环"""
        self.logger.info("Starting scrape task...")
        
        # 建立目录
        self.config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        try:
            self.page = await self.browser_manager.start()
            self.state.start_time = time.time()
            
            # 过滤待抓取列表
            pending_list = [n for n in harvest_list if not self.state.is_done(n.get('url'))]
            total = len(harvest_list)
            pending = len(pending_list)
            
            print(f"Task: {total} total, {total - pending} done, {pending} pending")
            
            if not pending_list:
                print("All pages already scraped.")
                return
            
            # 初始化进度显示
            self.progress = ProgressDisplay(pending, self.logger)
            pages_since_break = 0
            pages_total = 0

            for i, node in enumerate(pending_list):
                if self.shutdown_requested:
                    break

                # 提取任务信息
                title = node.get('title', 'Unknown')
                url = node.get('url')
                node_id = node.get('id', i)
                
                self.progress.update(title, "processing")
                self.progress.print_progress()

                # 准备输出路径
                folder_path = url_to_folder_path(url)
                output_folder = self.config.OUTPUT_DIR / folder_path
                output_folder.mkdir(parents=True, exist_ok=True)
                
                safe_title = safe_filename(title)
                output_file = output_folder / f"{node_id:04d}_{safe_title}.md"

                # 检查文件存在跳过
                if output_file.exists() and output_file.stat().st_size > 100:
                    self.state.mark_skipped(url)
                    self.progress.update(title, "skipped")
                    continue

                # 执行单页抓取
                success = await self._process_page(url, output_file, title)
                
                if success:
                    self.state.mark_completed(url, output_file.stat().st_size)
                    self.progress.update(title, "success")
                    self.consecutive_failures = 0
                    self.backoff_time = self.config.BACKOFF_INITIAL
                else:
                    self.state.mark_failed(url)
                    self.progress.update(title, "failed")
                    self.consecutive_failures += 1
                    
                    # 连续失败检测
                    if self.consecutive_failures >= 3:
                        wait_time = min(self.backoff_time, self.config.BACKOFF_MAX)
                        self.progress.print_line(
                            f"[BACKOFF] {self.consecutive_failures} consecutive failures, "
                            f"waiting {wait_time}s..."
                        )
                        await asyncio.sleep(wait_time)
                        self.backoff_time = int(self.backoff_time * self.config.BACKOFF_FACTOR)
                
                # 写入心跳
                self._write_heartbeat()
                
                # 休息策略
                pages_since_break += 1
                pages_total += 1
                
                # 长休息检查
                if self.human.should_take_long_break(pages_total):
                    duration = self.human.get_long_break_duration()
                    self.progress.print_line(f"[LONG BREAK] {int(duration)}s pause after {pages_total} pages")
                    await asyncio.sleep(duration)
                # 短休息检查
                elif self.human.should_take_break(pages_since_break):
                    duration = self.human.get_break_duration()
                    self.progress.print_line(f"[BREAK] {int(duration)}s pause")
                    await asyncio.sleep(duration)
                    pages_since_break = 0
                else:
                    delay = self.human.random_delay()
                    await asyncio.sleep(delay)

        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            raise
        finally:
            await self.browser_manager.close()
            self._generate_report(harvest_list)
            print(f"\n[DONE] Completed: {self.progress.completed}, Failed: {self.progress.failed}")

    async def _process_page(self, url: str, output_file: Path, title: str) -> bool:
        """单页处理逻辑 - 带整体超时保护"""
        for retry in range(self.config.MAX_RETRIES):
            try:
                # 使用整体超时包裹，避免永久卡死（60秒）
                return await asyncio.wait_for(
                    self._do_process_page(url, output_file, title),
                    timeout=60.0
                )
            except asyncio.TimeoutError:
                self.logger.warning(f"Retry {retry+1}/{self.config.MAX_RETRIES} {title}: Page processing timeout (60s)")
                # 超时后刷新页面
                try:
                    await self.page.reload(timeout=10000)
                except:
                    pass
                await asyncio.sleep(2 + retry * 2)
            except Exception as e:
                self.logger.warning(f"Retry {retry+1}/{self.config.MAX_RETRIES} {title}: {str(e)[:50]}")
                await asyncio.sleep(2 + retry * 2)
        return False
    
    async def _do_process_page(self, url: str, output_file: Path, title: str) -> bool:
        """实际页面处理逻辑"""
        # 使用 domcontentloaded 而非 networkidle，避免大页面卡死
        response = await self.page.goto(url, wait_until="domcontentloaded", timeout=self.config.TIMEOUT)
        
        # HTTP 状态码检查
        if response and response.status == 429:
            wait_time = min(self.backoff_time, self.config.BACKOFF_MAX)
            self.progress.print_line(f"[HTTP 429] Rate limited, waiting {wait_time}s...")
            await asyncio.sleep(wait_time)
            self.backoff_time = int(self.backoff_time * self.config.BACKOFF_FACTOR)
            return False
        
        # 等待页面内容加载完成（等待复制按钮出现或超时）
        try:
            await self.page.wait_for_selector('button:has-text("复制页面")', timeout=15000)
        except:
            # 如果复制按钮没出现，等待一下内容区域
            await asyncio.sleep(3)
        
        await self.human.simulate_interaction(self.page)
        
        # 检测反爬（简化版：直接跳过，不等待）
        content = await self.page.content()
        if any(kw in content.lower() for kw in self.config.ANTI_BOT_KEYWORDS):
            self.progress.print_line(f"[ANTI-BOT] Detected on {title[:30]}, skipping...")
            return False

        
        # 核心抓取逻辑：寻找"复制页面"按钮
        copy_btn = self.page.locator('button:has-text("复制页面")')
        if await copy_btn.count() > 0:
            await copy_btn.first.click()
            await asyncio.sleep(1.0)  # 大页面需要更长时间复制到剪贴板
            text = await self.page.evaluate("navigator.clipboard.readText()")
        else:
            # 备选方案：全选复制
            await self.page.locator(".doc-content").click()
            await self.page.keyboard.press("Control+a")
            await self.page.keyboard.press("Control+c")
            await asyncio.sleep(1.0)
            text = await self.page.evaluate("navigator.clipboard.readText()")
        
        if text and len(text) > 50:
            header = f"# {title}\n\n> Source: {url}\n\n---\n\n"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(header + text)
            return True
        
        return False


    def _generate_report(self, harvest_list):
        """生成报告 - 包含失败页面的详细信息便于手动补充"""
        elapsed = time.time() - self.state.start_time if self.state.start_time else 0
        elapsed_str = str(timedelta(seconds=int(elapsed)))
        
        # 构建 URL 到节点信息的映射
        url_to_node = {n.get('url'): n for n in harvest_list if n.get('url')}
        
        with open(self.report_file, 'w', encoding='utf-8') as f:
            f.write(f"# Scrape Report\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            f.write(f"Duration: {elapsed_str}\n\n")
            f.write(f"## Summary\n\n")
            f.write(f"- Total: {len(harvest_list)}\n")
            f.write(f"- Completed: {len(self.state.completed)}\n")
            f.write(f"- Failed: {len(self.state.failed)}\n")
            f.write(f"- Skipped: {len(self.state.skipped)}\n\n")
            
            if self.state.failed:
                f.write(f"## Failed Pages (需手动补充)\n\n")
                f.write("| ID | Title | URL | Expected Path |\n")
                f.write("|-----|-------|-----|---------------|\n")
                for url in list(self.state.failed):
                    node = url_to_node.get(url, {})
                    title = node.get('title', 'Unknown')
                    node_id = node.get('id', '?')
                    folder_path = url_to_folder_path(url)
                    safe_title = safe_filename(title)
                    expected_path = f"docs/server_api/{folder_path}/{node_id:04d}_{safe_title}.md" if isinstance(node_id, int) else f"docs/server_api/{folder_path}/{safe_title}.md"
                    f.write(f"| {node_id} | {title[:30]} | {url} | `{expected_path}` |\n")
                f.write("\n")
