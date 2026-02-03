from pathlib import Path
from dataclasses import dataclass

@dataclass
class ScraperConfig:
    """抓取任务配置类"""
    
    # 基础路径
    BASE_DIR: Path = Path(__file__).parent.parent
    OUTPUT_DIR: Path = BASE_DIR / "docs"
    LOG_DIR: Path = BASE_DIR / "logs"
    ARCHIVE_DIR: Path = BASE_DIR / "archive"
    CONFIG_DIR: Path = BASE_DIR / "configs"
    
    # 延时配置 - 增强随机性
    DELAY_MIN: float = 2.0         # 最小延时
    DELAY_MAX: float = 15.0        # 最大延时
    DELAY_BASE: float = 5.0        # 基础延时 (高斯分布均值)
    DELAY_SIGMA: float = 3.0       # 标准差 (增大以提高随机性)
    
    # 休息策略
    BREAK_INTERVAL: tuple = (8, 20)    # 每 N 页休息
    BREAK_DURATION: tuple = (15, 45)   # 休息时长 (秒)
    
    # 长休息 (每 100 页左右)
    LONG_BREAK_INTERVAL: tuple = (80, 120)
    LONG_BREAK_DURATION: tuple = (120, 300)  # 2-5 分钟
    
    MAX_RETRIES: int = 3
    TIMEOUT: int = 45000          # 毫秒 (增加超时)
    
    # 反爬检测
    ANTI_BOT_KEYWORDS: tuple = (
        "captcha", 
        "human verification", 
        "请完成验证"
    )
    
    # 指数退避配置
    BACKOFF_INITIAL: int = 30      # 初始退避秒数
    BACKOFF_MAX: int = 1800        # 最大退避 30 分钟
    BACKOFF_FACTOR: float = 2.0    # 退避倍数
    
    # 心跳间隔
    HEARTBEAT_INTERVAL: int = 30   # 秒

    def __post_init__(self):
        # 确保目录存在
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
