import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Set, Dict, Optional

class HarvestState:
    """
    通用抓取状态管理器
    支持断点续抓、失败记录、文件大小记录
    """
    
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.completed: Set[str] = set()
        self.failed: Set[str] = set()
        self.skipped: Set[str] = set()
        self.file_sizes: Dict[str, int] = {}
        self.start_time: Optional[float] = None
        self.logger = logging.getLogger(__name__)
        
        self.load()
    
    def load(self):
        """加载状态文件"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.completed = set(data.get('completed', []))
                    self.failed = set(data.get('failed', []))
                    self.skipped = set(data.get('skipped', []))
                    self.file_sizes = data.get('file_sizes', {})
                self.logger.info(f"已加载进度: {len(self.completed)} 完成, {len(self.failed)} 失败")
            except Exception as e:
                self.logger.warning(f"无法加载状态文件 {self.state_file}: {e}")
    
    def save(self):
        """保存状态到文件"""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'completed': list(self.completed),
                    'failed': list(self.failed),
                    'skipped': list(self.skipped),
                    'file_sizes': self.file_sizes,
                    'last_updated': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"无法保存状态: {e}")
    
    def is_done(self, url: str) -> bool:
        """检查 URL 是否已处理（完成或跳过）"""
        return url in self.completed or url in self.skipped
    
    def mark_completed(self, url: str, file_size: int = 0):
        self.completed.add(url)
        # 如果之前失败过，现在成功了，从失败列表中移除
        if url in self.failed:
            self.failed.remove(url)
        self.file_sizes[url] = file_size
        self.save()
    
    def mark_failed(self, url: str):
        self.failed.add(url)
        self.save()
    
    def mark_skipped(self, url: str):
        self.skipped.add(url)
        self.save()
