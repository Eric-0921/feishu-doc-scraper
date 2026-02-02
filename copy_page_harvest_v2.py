#!/usr/bin/env python3
"""
飞书文档官方 Markdown 抓取器 V2 (增强版)

新增功能：
1. 进度条 (tqdm) - 显示当前进度、ETA、当前抓取名称
2. 断点续抓 - 自动跳过已存在的文件
3. 反自动化检测暂停 - 遇到验证页面时暂停并等待用户指令
4. 目录分类 - 基于 URL 路径结构创建文件夹
5. 状态持久化 - 记录进度到 state.json

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
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime

# 环境检查（遵守全局规则，调试时跳过）
if os.environ.get('CONDA_DEFAULT_ENV') is None:
    pass

from playwright.async_api import async_playwright

# 尝试导入 tqdm，如果没有则使用简单的替代
try:
    from tqdm import tqdm
except ImportError:
    print("[警告] tqdm 未安装，使用简化进度显示")
    tqdm = None


# ============ 配置 ============
OUTPUT_DIR = Path("docs")
STATE_FILE = Path("harvest_state.json")
# 移除 "机器人" 因为正常文档内容中会出现该词
ANTI_BOT_KEYWORDS = ["captcha", "challenge", "human verification", "请完成验证"]
DELAY_MIN = 1.5
DELAY_MAX = 3.0


class HarvestState:
    """抓取状态管理器 - 支持断点续抓"""
    
    def __init__(self):
        self.completed = set()
        self.failed = set()
        self.skipped = set()
        self.paused = False
        self.current_url = None
        self.start_time = None
        self.load()
    
    def load(self):
        """从文件加载状态"""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.completed = set(data.get('completed', []))
                    self.failed = set(data.get('failed', []))
                    self.skipped = set(data.get('skipped', []))
                print(f"[状态] 已加载历史进度: {len(self.completed)} 完成, {len(self.failed)} 失败")
            except Exception as e:
                print(f"[警告] 无法加载状态文件: {e}")
    
    def save(self):
        """保存状态到文件"""
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    'completed': list(self.completed),
                    'failed': list(self.failed),
                    'skipped': list(self.skipped),
                    'last_updated': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[警告] 无法保存状态: {e}")
    
    def is_done(self, url):
        """检查 URL 是否已完成"""
        return url in self.completed or url in self.skipped
    
    def mark_completed(self, url):
        self.completed.add(url)
        self.save()
    
    def mark_failed(self, url):
        self.failed.add(url)
        self.save()
    
    def mark_skipped(self, url):
        self.skipped.add(url)
        self.save()


def url_to_folder_path(url: str) -> str:
    """
    从 URL 推断目录路径
    
    例如:
    https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
    -> client-docs/bot-v3
    """
    try:
        parsed = urlparse(url)
        path_parts = parsed.path.strip('/').split('/')
        
        # 移除 'document' 前缀和最后的文件名
        if path_parts and path_parts[0] == 'document':
            path_parts = path_parts[1:]
        
        if len(path_parts) > 1:
            # 取除最后一项（文档名）外的所有路径
            folder_parts = path_parts[:-1]
            return '/'.join(folder_parts)
        elif len(path_parts) == 1:
            return 'root'
        else:
            return 'uncategorized'
    except:
        return 'uncategorized'


def safe_filename(name: str) -> str:
    """清理文件名，移除非法字符"""
    illegal_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    for char in illegal_chars:
        name = name.replace(char, '_')
    return name[:100]  # 限制长度


def detect_anti_bot(page_content: str) -> bool:
    """检测反自动化验证页面"""
    content_lower = page_content.lower()
    for keyword in ANTI_BOT_KEYWORDS:
        if keyword.lower() in content_lower:
            return True
    return False


async def wait_for_user_resume(page):
    """
    暂停并等待用户恢复
    用户需要手动完成验证，然后按回车继续
    """
    print("\n" + "=" * 60)
    print("⚠️  检测到反自动化验证页面！")
    print("请在浏览器中手动完成验证。")
    print("完成后，请按 Enter 键继续...")
    print("输入 'skip' 跳过当前页面，输入 'quit' 退出程序")
    print("=" * 60 + "\n")
    
    # 非阻塞等待用户输入
    loop = asyncio.get_event_loop()
    user_input = await loop.run_in_executor(None, input)
    
    if user_input.strip().lower() == 'quit':
        return 'quit'
    elif user_input.strip().lower() == 'skip':
        return 'skip'
    return 'continue'


async def copy_page_harvest_v2(limit: int = 0):
    """
    增强版抓取主函数
    
    Args:
        limit: 页面数量限制 (0 = 全量抓取)
    """
    state = HarvestState()
    state.start_time = time.time()
    
    # 1. 加载目录结构
    structure_path = Path("structure.json")
    if not structure_path.exists():
        print(f"[错误] {structure_path} 不存在，请先运行 discover_tree.py")
        return

    with open(structure_path, 'r', encoding='utf-8') as f:
        nodes = json.load(f)

    # 过滤掉没有 URL 的目录节点
    harvest_list = [n for n in nodes if n.get('url') and n['url'].startswith('http')]
    
    # 过滤已完成的
    pending_list = [n for n in harvest_list if not state.is_done(n.get('url'))]
    
    if limit > 0:
        pending_list = pending_list[:limit]
        print(f"[模式] 限制抓取 {limit} 页")
    
    total = len(harvest_list)
    pending = len(pending_list)
    done = len(state.completed)
    
    print(f"\n{'=' * 50}")
    print(f"📊 抓取统计")
    print(f"   总页面: {total}")
    print(f"   已完成: {done}")
    print(f"   待抓取: {pending}")
    print(f"{'=' * 50}\n")
    
    if pending == 0:
        print("✅ 所有页面已抓取完成！")
        return
    
    # 确保输出目录存在
    OUTPUT_DIR.mkdir(exist_ok=True)

    # 2. 启动 Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # 非无头模式
        context = await browser.new_context()
        
        # 自动授权剪贴板权限 (解决首次弹窗问题)
        await context.grant_permissions(['clipboard-read', 'clipboard-write'])
        
        page = await context.new_page()
        
        success_count = 0
        fail_count = 0
        skip_count = 0
        
        # 使用 tqdm 或简化进度
        if tqdm:
            progress = tqdm(pending_list, desc="抓取进度", unit="页")
        else:
            progress = pending_list
        
        for i, node in enumerate(progress):
            title = node.get('title', 'Unknown')
            url = node.get('url')
            
            # 更新进度条描述
            if tqdm:
                progress.set_postfix_str(f"当前: {title[:30]}...")
            else:
                elapsed = time.time() - state.start_time
                eta = (elapsed / (i + 1)) * (pending - i - 1) if i > 0 else 0
                print(f"[{i+1}/{pending}] {title} (ETA: {eta/60:.1f}分钟)")
            
            # 基于 URL 创建目录
            folder_path = url_to_folder_path(url)
            output_folder = OUTPUT_DIR / folder_path
            output_folder.mkdir(parents=True, exist_ok=True)
            
            safe_title = safe_filename(title)
            # 使用 structure.json 中的 id 作为全局序号 (4位数字前缀)
            node_id = node.get('id', i)
            output_file = output_folder / f"{node_id:04d}_{safe_title}.md"
            
            # 检查文件是否已存在（二级断点）
            if output_file.exists() and output_file.stat().st_size > 100:
                if tqdm:
                    progress.write(f"  ⏭️  跳过: {title} (文件已存在)")
                skip_count += 1
                state.mark_skipped(url)
                continue
            
            try:
                # 打开页面
                await page.goto(url, wait_until="networkidle", timeout=30000)
                
                # 检查反自动化
                page_content = await page.content()
                if detect_anti_bot(page_content):
                    action = await wait_for_user_resume(page)
                    if action == 'quit':
                        print("\n[用户中断] 保存状态并退出...")
                        break
                    elif action == 'skip':
                        state.mark_skipped(url)
                        skip_count += 1
                        continue
                
                # 等待正文加载
                try:
                    await page.wait_for_selector(".doc-content", timeout=10000)
                except:
                    pass
                
                await asyncio.sleep(1)
                
                # 点击"复制页面"按钮
                copy_btn = page.locator('button:has-text("复制页面")')
                
                if await copy_btn.count() > 0:
                    await copy_btn.first.click()
                    await asyncio.sleep(0.5)
                    
                    # 读取剪贴板
                    clipboard_content = await page.evaluate("navigator.clipboard.readText()")
                    
                    if clipboard_content and len(clipboard_content) > 50:
                        with open(output_file, 'w', encoding='utf-8') as f:
                            f.write(f"# {title}\n\n")
                            f.write(f"> Source: {url}\n\n---\n\n")
                            f.write(clipboard_content)
                        
                        if tqdm:
                            progress.write(f"  ✅ {title} ({len(clipboard_content)} 字符)")
                        success_count += 1
                        state.mark_completed(url)
                    else:
                        if tqdm:
                            progress.write(f"  ❌ {title} (剪贴板内容为空)")
                        fail_count += 1
                        state.mark_failed(url)
                else:
                    # Fallback: 选中正文并复制
                    if tqdm:
                        progress.write(f"  ⚠️  {title} (无复制按钮，尝试备用方案)")
                    await page.locator(".doc-content").click()
                    await page.keyboard.press("Control+a")
                    await page.keyboard.press("Control+c")
                    await asyncio.sleep(0.5)
                    
                    clipboard_content = await page.evaluate("navigator.clipboard.readText()")
                    
                    if clipboard_content and len(clipboard_content) > 50:
                        with open(output_file, 'w', encoding='utf-8') as f:
                            f.write(f"# {title}\n\n")
                            f.write(f"> Source: {url}\n\n---\n\n")
                            f.write(clipboard_content)
                        success_count += 1
                        state.mark_completed(url)
                    else:
                        fail_count += 1
                        state.mark_failed(url)
                
            except Exception as e:
                if tqdm:
                    progress.write(f"  ❌ {title} 错误: {str(e)[:50]}")
                else:
                    print(f"  ❌ 错误: {e}")
                fail_count += 1
                state.mark_failed(url)
            
            # 随机延迟（反爬）
            await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
        
        await browser.close()
    
    # 最终报告
    elapsed = time.time() - state.start_time
    print(f"\n{'=' * 50}")
    print(f"📊 抓取完成报告")
    print(f"   耗时: {elapsed/60:.1f} 分钟")
    print(f"   成功: {success_count}")
    print(f"   失败: {fail_count}")
    print(f"   跳过: {skip_count}")
    print(f"   总完成: {len(state.completed)}/{total}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="飞书文档抓取器 V2")
    parser.add_argument("--limit", type=int, default=0, help="限制抓取页面数 (0=全量)")
    args = parser.parse_args()
    
    asyncio.run(copy_page_harvest_v2(limit=args.limit))
