import random
import asyncio
from dataclasses import dataclass
from .config import ScraperConfig

@dataclass
class HumanBehavior:
    """人类行为模拟器"""
    config: ScraperConfig

    def random_delay(self) -> float:
        """生成高斯分布的随机延迟"""
        delay = random.gauss(self.config.DELAY_BASE, self.config.DELAY_SIGMA)
        return max(self.config.DELAY_MIN, min(self.config.DELAY_MAX, delay))

    def should_take_break(self, page_count: int) -> bool:
        """判断是否需要休息"""
        interval = random.randint(*self.config.BREAK_INTERVAL)
        return page_count > 0 and page_count % interval == 0
    
    def get_break_duration(self) -> float:
        """获取随机休息时长"""
        return random.uniform(*self.config.BREAK_DURATION)

    async def simulate_interaction(self, page):
        """模拟页面交互（滚动、鼠标移动）"""
        behaviors = ['scroll', 'mouse', 'wait']
        action = random.choice(behaviors)
        
        if action == 'scroll':
            # 随机滚动
            amount = random.randint(-200, 200)
            await page.evaluate(f"window.scrollBy(0, {amount})")
            await asyncio.sleep(0.2)
        elif action == 'mouse':
            # 随机移动鼠标
            x = random.randint(100, 800)
            y = random.randint(100, 600)
            try:
                await page.mouse.move(x, y)
            except:
                pass
        else:
            # 短暂发呆
            await asyncio.sleep(random.uniform(0.1, 0.5))
