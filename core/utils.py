from urllib.parse import urlparse
import re

def url_to_folder_path(url: str) -> str:
    """
    从 URL 推断目录路径
    Example: https://open.feishu.cn/document/client-docs/bot-v3/add -> client-docs/bot-v3
    """
    try:
        parsed = urlparse(url)
        path_parts = parsed.path.strip('/').split('/')
        
        # 移除常见的 'document' 前缀
        if path_parts and path_parts[0] == 'document':
            path_parts = path_parts[1:]
            
        # 移除最后一项（假设是文件名）
        if len(path_parts) > 1:
            return '/'.join(path_parts[:-1])
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
    # 移除首尾空格
    name = name.strip()
    return name[:100]  # 限制长度
