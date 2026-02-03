from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import logging
import asyncio

class BrowserManager:
    """浏览器生命周期管理"""
    
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None
        self.logger = logging.getLogger(__name__)

    async def start(self):
        """启动浏览器并配置反检测"""
        self.logger.info("正在启动浏览器...")
        self.playwright = await async_playwright().start()
        
        # 启动 Chromium
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        
        # 创建上下文
        self.context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        # 核心：自动授权剪贴板（这对我们的抓取至关重要）
        await self.context.grant_permissions(['clipboard-read', 'clipboard-write'])
        
        # 防止 webdriver 检测
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        self.page = await self.context.new_page()
        self.logger.info("浏览器启动成功")
        return self.page

    async def close(self):
        """优雅关闭"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.logger.info("浏览器已关闭")

    async def wait_for_user_resume(self) -> str:
        """简单的命令行交互，用于处理暂停"""
        print("\n" + "=" * 60)
        print("⚠️  需要人工介入！(可能遇到了验证码)")
        print("请在浏览器中完成操作。")
        print("完成后按 Enter 继续，输入 'skip' 跳过，输入 'quit' 退出")
        print("=" * 60 + "\n")
        
        loop = asyncio.get_event_loop()
        user_input = await loop.run_in_executor(None, input)
        
        return user_input.strip().lower()
