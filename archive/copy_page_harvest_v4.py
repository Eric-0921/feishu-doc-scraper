#!/usr/bin/env python3
"""
飞书文档官方 Markdown 抓取器 V4 (人类行为模拟版)

相比 V3 的改进：
- 更加随机化的延迟模式，模拟真实人类行为
- 使用高斯分布而非均匀分布的延迟
- 偶尔较长的"休息"停顿
- 随机的鼠标移动和滚动

延迟策略：
- 基础延迟: 1.5-3.5秒 (高斯分布，中心2.5秒)
- 每 5-15 页: 额外 5-15 秒"休息"停顿
- 随机页面滚动和鼠标移动

作者: AI Assistant
最后更新: 2026-02-03
"""
import os
import sys
import json
import asyncio
import random
import signal
import time
import logging
import math
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime

from playwright.async_api import async_playwright

try:
    from tqdm import tqdm
except ImportError:
    print("[警告] tqdm 未安装，使用简化进度显示")
    tqdm = None


# ============ 配置 ============
OUTPUT_DIR = Path("docs")
# 默认值，将在 main 中根据 structure 参数更新
STATE_FILE = Path("harvest_state.json")
LOG_FILE = Path("harvest.log")
REPORT_FILE = Path("harvest_report.md")
ANTI_BOT_KEYWORDS = ["captcha", "challenge", "human verification", "请完成验证"]

# 更自然的延迟配置
DELAY_BASE = 2.5      # 基础延迟中心值 (秒)
DELAY_SIGMA = 1.0     # 高斯分布标准差
DELAY_MIN = 1.0       # 最小延迟
DELAY_MAX = 6.0       # 最大延迟
BREAK_INTERVAL = (5, 15)   # 每 N 页休息一次的范围
BREAK_DURATION = (5, 15)   # 休息时长范围 (秒)

MAX_RETRIES = 3
MIN_CONTENT_SIZE = 200

# ============ 日志设置 ============
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ============ 全局中断标志 ============
shutdown_requested = False


def signal_handler(signum, frame):
    global shutdown_requested
    if shutdown_requested:
        logger.warning("强制退出...")
        sys.exit(1)
    logger.warning("\n收到中断信号，正在保存进度并优雅退出...")
    logger.warning("再次按 Ctrl+C 强制退出")
    shutdown_requested = True


signal.signal(signal.SIGINT, signal_handler)


def random_delay() -> float:
    """
    生成模拟人类行为的随机延迟
    使用截断高斯分布
    """
    delay = random.gauss(DELAY_BASE, DELAY_SIGMA)
    delay = max(DELAY_MIN, min(DELAY_MAX, delay))
    return delay


def should_take_break(page_count: int) -> bool:
    """
    判断是否需要休息
    每隔随机 5-15 页休息一次
    """
    interval = random.randint(*BREAK_INTERVAL)
    return page_count > 0 and page_count % interval == 0


async def simulate_human_behavior(page):
    """
    模拟人类行为：随机滚动、鼠标移动
    """
    behaviors = ['scroll', 'mouse', 'wait']
    action = random.choice(behaviors)
    
    if action == 'scroll':
        # 随机滚动页面
        scroll_amount = random.randint(-200, 200)
        await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        await asyncio.sleep(0.2)
    elif action == 'mouse':
        # 随机鼠标移动
        x = random.randint(100, 800)
        y = random.randint(100, 600)
        try:
            await page.mouse.move(x, y)
        except:
            pass
    else:
        # 短暂等待
        await asyncio.sleep(random.uniform(0.1, 0.5))


class HarvestState:
    """抓取状态管理器"""
    
    def __init__(self):
        self.completed = set()
        self.failed = set()
        self.skipped = set()
        self.file_sizes = {}
        self.start_time = None
        self.load()
    
    def load(self):
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.completed = set(data.get('completed', []))
                    self.failed = set(data.get('failed', []))
                    self.skipped = set(data.get('skipped', []))
                    self.file_sizes = data.get('file_sizes', {})
                logger.info(f"已加载历史进度: {len(self.completed)} 完成, {len(self.failed)} 失败")
            except Exception as e:
                logger.warning(f"无法加载状态文件: {e}")
    
    def save(self):
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    'completed': list(self.completed),
                    'failed': list(self.failed),
                    'skipped': list(self.skipped),
                    'file_sizes': self.file_sizes,
                    'last_updated': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"无法保存状态: {e}")
    
    def is_done(self, url):
        return url in self.completed or url in self.skipped
    
    def mark_completed(self, url, file_size=0):
        self.completed.add(url)
        self.file_sizes[url] = file_size
        self.save()
    
    def mark_failed(self, url):
        self.failed.add(url)
        self.save()
    
    def mark_skipped(self, url):
        self.skipped.add(url)
        self.save()


def url_to_folder_path(url: str) -> str:
    try:
        parsed = urlparse(url)
        path_parts = parsed.path.strip('/').split('/')
        if path_parts and path_parts[0] == 'document':
            path_parts = path_parts[1:]
        if len(path_parts) > 1:
            return '/'.join(path_parts[:-1])
        elif len(path_parts) == 1:
            return 'root'
        else:
            return 'uncategorized'
    except:
        return 'uncategorized'


def safe_filename(name: str) -> str:
    illegal_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    for char in illegal_chars:
        name = name.replace(char, '_')
    return name[:100]


def detect_anti_bot(page_content: str) -> bool:
    content_lower = page_content.lower()
    for keyword in ANTI_BOT_KEYWORDS:
        if keyword.lower() in content_lower:
            return True
    return False


async def wait_for_user_resume(page):
    print("\n" + "=" * 60)
    print("⚠️  检测到反自动化验证页面！")
    print("请在浏览器中手动完成验证。")
    print("完成后按 Enter 继续，输入 'skip' 跳过，输入 'quit' 退出")
    print("=" * 60 + "\n")
    
    loop = asyncio.get_event_loop()
    user_input = await loop.run_in_executor(None, input)
    
    if user_input.strip().lower() == 'quit':
        return 'quit'
    elif user_input.strip().lower() == 'skip':
        return 'skip'
    return 'continue'


def generate_report(state: HarvestState, harvest_list: list, elapsed: float):
    small_files = []
    for url, size in state.file_sizes.items():
        if size < MIN_CONTENT_SIZE:
            title = "Unknown"
            for node in harvest_list:
                if node.get('url') == url:
                    title = node.get('title', 'Unknown')
                    break
            small_files.append({'title': title, 'url': url, 'size': size})
    
    small_files.sort(key=lambda x: x['size'])
    
    report = f"""# 飞书文档抓取报告

**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**耗时**: {elapsed/60:.1f} 分钟

## 📊 统计摘要

| 项目 | 数量 |
|---|---|
| 成功 | {len(state.completed)} |
| 失败 | {len(state.failed)} |
| 跳过 | {len(state.skipped)} |

## ⚠️ 文件大小异常列表 (< {MIN_CONTENT_SIZE} 字节)

以下文件内容过小，可能需要手动核对：

| 标题 | 大小 (字节) | 链接 |
|---|---|---|
"""
    
    if small_files:
        for f in small_files:
            report += f"| {f['title']} | {f['size']} | [链接]({f['url']}) |\n"
    else:
        report += "| ✅ 无异常文件 | - | - |\n"
    
    if state.failed:
        report += "\n## ❌ 抓取失败列表\n\n"
        report += "| 链接 |\n|---|\n"
        for url in state.failed:
            title = "Unknown"
            for node in harvest_list:
                if node.get('url') == url:
                    title = node.get('title', 'Unknown')
                    break
            report += f"| [{title}]({url}) |\n"
    
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(report)
    
    logger.info(f"报告已生成: {REPORT_FILE}")
    return report


async def copy_page_harvest_v4(limit: int = 0, structure_file: str = "structure.json"):
    """
    人类行为模拟版抓取主函数
    
    Args:
        limit: 页面数量限制 (0 = 全量抓取)
        structure_file: 目录结构文件路径
    """
    global shutdown_requested
    
    state = HarvestState()
    state.start_time = time.time()
    
    structure_path = Path(structure_file)
    if not structure_path.exists():
        logger.error(f"{structure_path} 不存在，请先运行目录侦察脚本")
        return

    with open(structure_path, 'r', encoding='utf-8') as f:
        nodes = json.load(f)

    harvest_list = [n for n in nodes if n.get('url') and n['url'].startswith('http')]
    pending_list = [n for n in harvest_list if not state.is_done(n.get('url'))]
    
    if limit > 0:
        pending_list = pending_list[:limit]
        logger.info(f"[模式] 限制抓取 {limit} 页")
    
    total = len(harvest_list)
    pending = len(pending_list)
    done = len(state.completed)
    
    print(f"\n{'=' * 50}")
    print(f"📊 抓取统计 (V4 人类模拟版)")
    print(f"   总页面: {total}")
    print(f"   已完成: {done}")
    print(f"   待抓取: {pending}")
    print(f"{'=' * 50}\n")
    
    if pending == 0:
        logger.info("✅ 所有页面已抓取完成！")
        generate_report(state, harvest_list, time.time() - state.start_time)
        return
    
    OUTPUT_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        await context.grant_permissions(['clipboard-read', 'clipboard-write'])
        page = await context.new_page()
        
        success_count = 0
        fail_count = 0
        skip_count = 0
        pages_since_break = 0
        
        if tqdm:
            progress = tqdm(pending_list, desc="抓取进度", unit="页")
        else:
            progress = pending_list
        
        for i, node in enumerate(progress):
            if shutdown_requested:
                logger.warning("收到中断信号，保存进度并退出...")
                break
            
            title = node.get('title', 'Unknown')
            url = node.get('url')
            node_id = node.get('id', i)
            
            if tqdm:
                progress.set_postfix_str(f"当前: {title[:25]}...")
            else:
                elapsed = time.time() - state.start_time
                eta = (elapsed / (i + 1)) * (pending - i - 1) if i > 0 else 0
                print(f"[{i+1}/{pending}] {title} (ETA: {eta/60:.1f}分钟)")
            
            folder_path = url_to_folder_path(url)
            output_folder = OUTPUT_DIR / folder_path
            output_folder.mkdir(parents=True, exist_ok=True)
            
            safe_title = safe_filename(title)
            output_file = output_folder / f"{node_id:04d}_{safe_title}.md"
            
            if output_file.exists() and output_file.stat().st_size > 100:
                if tqdm:
                    progress.write(f"  ⏭️  跳过: {title} (文件已存在)")
                skip_count += 1
                state.mark_skipped(url)
                continue
            
            # 带重试的抓取逻辑
            success = False
            last_error = None
            
            for retry in range(MAX_RETRIES):
                if shutdown_requested:
                    break
                    
                try:
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    
                    # 模拟人类行为
                    await simulate_human_behavior(page)
                    
                    page_content = await page.content()
                    if detect_anti_bot(page_content):
                        action = await wait_for_user_resume(page)
                        if action == 'quit':
                            shutdown_requested = True
                            break
                        elif action == 'skip':
                            state.mark_skipped(url)
                            skip_count += 1
                            success = True
                            break
                    
                    try:
                        await page.wait_for_selector(".doc-content", timeout=10000)
                    except:
                        pass
                    
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                    
                    copy_btn = page.locator('button:has-text("复制页面")')
                    
                    if await copy_btn.count() > 0:
                        await copy_btn.first.click()
                        await asyncio.sleep(random.uniform(0.3, 0.8))
                        
                        clipboard_content = await page.evaluate("navigator.clipboard.readText()")
                        
                        if clipboard_content and len(clipboard_content) > 50:
                            content_to_write = f"# {title}\n\n> Source: {url}\n\n---\n\n{clipboard_content}"
                            with open(output_file, 'w', encoding='utf-8') as f:
                                f.write(content_to_write)
                            
                            file_size = len(content_to_write)
                            if tqdm:
                                if file_size < MIN_CONTENT_SIZE:
                                    progress.write(f"  ⚠️  {title} ({file_size} 字节 - 内容过小)")
                                else:
                                    progress.write(f"  ✅ {title} ({file_size} 字节)")
                            
                            success_count += 1
                            state.mark_completed(url, file_size)
                            success = True
                            break
                        else:
                            last_error = "剪贴板内容为空"
                            if retry < MAX_RETRIES - 1:
                                logger.warning(f"  重试 {retry+1}/{MAX_RETRIES}: {title} - {last_error}")
                                await asyncio.sleep(2)
                    else:
                        await page.locator(".doc-content").click()
                        await page.keyboard.press("Control+a")
                        await page.keyboard.press("Control+c")
                        await asyncio.sleep(0.5)
                        
                        clipboard_content = await page.evaluate("navigator.clipboard.readText()")
                        
                        if clipboard_content and len(clipboard_content) > 50:
                            content_to_write = f"# {title}\n\n> Source: {url}\n\n---\n\n{clipboard_content}"
                            with open(output_file, 'w', encoding='utf-8') as f:
                                f.write(content_to_write)
                            file_size = len(content_to_write)
                            success_count += 1
                            state.mark_completed(url, file_size)
                            success = True
                            break
                        else:
                            last_error = "备用方案也失败"
                            
                except Exception as e:
                    last_error = str(e)[:80]
                    if retry < MAX_RETRIES - 1:
                        logger.warning(f"  重试 {retry+1}/{MAX_RETRIES}: {title} - {last_error}")
                        await asyncio.sleep(2)
            
            if not success and not shutdown_requested:
                if tqdm:
                    progress.write(f"  ❌ {title} (失败: {last_error})")
                logger.error(f"抓取失败: {title} - {last_error}")
                fail_count += 1
                state.mark_failed(url)
            
            # 更自然的随机延迟
            if not shutdown_requested:
                pages_since_break += 1
                
                # 检查是否需要休息
                if should_take_break(pages_since_break):
                    break_duration = random.uniform(*BREAK_DURATION)
                    if tqdm:
                        progress.write(f"  ☕ 休息 {break_duration:.1f} 秒...")
                    await asyncio.sleep(break_duration)
                    pages_since_break = 0
                else:
                    # 正常随机延迟
                    delay = random_delay()
                    await asyncio.sleep(delay)
        
        await browser.close()
    
    elapsed = time.time() - state.start_time
    print(f"\n{'=' * 50}")
    print(f"📊 抓取完成报告 (V4 人类模拟版)")
    print(f"   耗时: {elapsed/60:.1f} 分钟")
    print(f"   成功: {success_count}")
    print(f"   失败: {fail_count}")
    print(f"   跳过: {skip_count}")
    print(f"   总完成: {len(state.completed)}/{total}")
    print(f"{'=' * 50}")
    
    generate_report(state, harvest_list, elapsed)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="飞书文档抓取器 V4 (人类行为模拟版)")
    parser.add_argument("--limit", type=int, default=0, help="限制抓取页面数 (0=全量)")
    parser.add_argument("--structure", type=str, default="structure.json", help="目录结构文件路径")
    args = parser.parse_args()
    
    # 根据 structure 文件名动态调整状态和报告文件名
    prefix = Path(args.structure).stem
    STATE_FILE = Path(f"{prefix}_state.json")
    LOG_FILE = Path(f"{prefix}_harvest.log")
    REPORT_FILE = Path(f"{prefix}_report.md")
    
    # 更新全局配置中的 Path 对象
    # 注意：由于我们在 main 中修改了全局变量，这在脚本模式下是可以工作的
    # 但更安全的方式是传入这些路径
    
    asyncio.run(copy_page_harvest_v4(limit=args.limit, structure_file=args.structure))
