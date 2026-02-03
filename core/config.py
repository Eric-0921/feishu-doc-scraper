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
    
    # 抓取行为配置
    DELAY_BASE: float = 2.5       # 基础延迟 (秒)
    DELAY_SIGMA: float = 1.0      # 标准差
    DELAY_MIN: float = 1.0
    DELAY_MAX: float = 6.0
    
    BREAK_INTERVAL: tuple = (5, 15)   # 每 N 页休息
    BREAK_DURATION: tuple = (5, 15)   # 休息时长 (秒)
    
    MAX_RETRIES: int = 3
    TIMEOUT: int = 30000          # 毫秒
    
    # 反爬检测
    ANTI_BOT_KEYWORDS: tuple = (
        "captcha", 
        "challenge", 
        "human verification", 
        "请完成验证"
    )

    def __post_init__(self):
        # 确保目录存在
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
