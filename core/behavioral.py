import random
import asyncio
from dataclasses import dataclass
from .config import ScraperConfig

@dataclass
class HumanBehavior:
    """人类行为模拟器 - 增强随机性版本"""
    config: ScraperConfig
    
    # 内部状态
    _consecutive_fast: int = 0  # 连续快速请求计数
    _total_pages: int = 0       # 总处理页数
    _last_long_break: int = 0   # 上次长休息时的页数

    def random_delay(self) -> float:
        """
        生成具有高随机性的延迟
        混合使用多种分布以增加不可预测性
        """
        # 选择延迟策略 (增加不可预测性)
        strategy = random.choices(
            ['gaussian', 'uniform', 'exponential', 'burst'],
            weights=[0.5, 0.25, 0.15, 0.1]
        )[0]
        
        if strategy == 'gaussian':
            # 高斯分布 (最常用)
            delay = random.gauss(self.config.DELAY_BASE, self.config.DELAY_SIGMA)
        elif strategy == 'uniform':
            # 均匀分布
            delay = random.uniform(self.config.DELAY_MIN, self.config.DELAY_MAX)
        elif strategy == 'exponential':
            # 指数分布 (偶尔有较长等待)
            delay = random.expovariate(1 / self.config.DELAY_BASE)
        else:
            # 突发模式：偶尔快速连续请求后长等待
            if self._consecutive_fast < 2:
                delay = random.uniform(1.5, 3.0)
                self._consecutive_fast += 1
            else:
                delay = random.uniform(8.0, 15.0)
                self._consecutive_fast = 0
        
        # 确保在合理范围内
        return max(self.config.DELAY_MIN, min(self.config.DELAY_MAX, delay))

    def should_take_break(self, page_count: int) -> bool:
        """判断是否需要短休息"""
        interval = random.randint(*self.config.BREAK_INTERVAL)
        return page_count > 0 and page_count % interval == 0
    
    def should_take_long_break(self, page_count: int) -> bool:
        """判断是否需要长休息"""
        if page_count - self._last_long_break >= random.randint(*self.config.LONG_BREAK_INTERVAL):
            self._last_long_break = page_count
            return True
        return False
    
    def get_break_duration(self) -> float:
        """获取短休息时长"""
        return random.uniform(*self.config.BREAK_DURATION)
    
    def get_long_break_duration(self) -> float:
        """获取长休息时长"""
        return random.uniform(*self.config.LONG_BREAK_DURATION)

    async def simulate_interaction(self, page):
        """
        模拟页面交互（滚动、鼠标移动）
        增加交互多样性
        """
        # 随机执行 1-3 个动作
        action_count = random.randint(1, 3)
        behaviors = ['scroll', 'mouse', 'wait', 'scroll_smooth']
        
        for _ in range(action_count):
            action = random.choice(behaviors)
            
            if action == 'scroll':
                # 随机滚动
                amount = random.randint(-300, 400)
                await page.evaluate(f"window.scrollBy(0, {amount})")
                await asyncio.sleep(random.uniform(0.1, 0.4))
            elif action == 'scroll_smooth':
                # 平滑滚动
                amount = random.randint(100, 500)
                await page.evaluate(f"window.scrollBy({{top: {amount}, behavior: 'smooth'}})")
                await asyncio.sleep(random.uniform(0.3, 0.8))
            elif action == 'mouse':
                # 随机移动鼠标
                x = random.randint(100, 1000)
                y = random.randint(100, 700)
                try:
                    await page.mouse.move(x, y, steps=random.randint(5, 15))
                except:
                    pass
            else:
                # 短暂发呆
                await asyncio.sleep(random.uniform(0.2, 1.0))
