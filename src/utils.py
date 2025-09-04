"""
工具函数模块

包含重试机制、日志设置等辅助功能
"""

import sys
from functools import wraps
from typing import Callable, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests
from loguru import logger


def retry_with_exponential_backoff(
    max_attempts: int = 3,
    min_wait: float = 1,
    max_wait: float = 10,
    multiplier: float = 2
):
    """
    指数退避重试装饰器
    
    Args:
        max_attempts: 最大重试次数
        min_wait: 最小等待时间（秒）
        max_wait: 最大等待时间（秒）
        multiplier: 等待时间倍数
    """
    def decorator(func: Callable) -> Callable:
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=multiplier, min=min_wait, max=max_wait),
            retry=retry_if_exception_type((
                requests.RequestException,
                requests.ConnectionError,
                requests.Timeout,
                Exception
            )),
            reraise=True
        )
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            return func(*args, **kwargs)
        return wrapper
    return decorator


def setup_logging(config) -> None:
    """
    设置loguru日志配置
    
    Args:
        config: 配置对象
    """
    # 移除默认handler
    logger.remove()
    
    # 控制台输出格式
    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )
    
    # 添加控制台输出
    logger.add(
        sys.stdout,
        level=config.log_level.upper(),
        format=console_format,
        colorize=True
    )
    
    # 添加文件输出（如果配置了）
    if config.log_file:
        file_format = (
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <8} | "
            "{name}:{function}:{line} - "
            "{message}"
        )
        
        logger.add(
            config.log_file,
            level="DEBUG",
            format=file_format,
            rotation="10 MB",
            retention="30 days",
            compression="zip",
            encoding="utf-8"
        )
        
        logger.info(f"日志文件输出已启用: {config.log_file}")
    
    logger.info(f"日志系统初始化完成，级别: {config.log_level}")


def format_domain_name(domain: str) -> str:
    """
    格式化域名，确保格式正确
    
    Args:
        domain: 原始域名
        
    Returns:
        格式化后的域名
    """
    domain = domain.strip().lower()
    
    # 移除协议前缀
    if domain.startswith('http://'):
        domain = domain[7:]
    elif domain.startswith('https://'):
        domain = domain[8:]
    
    # 移除尾部斜杠
    domain = domain.rstrip('/')
    
    return domain


def validate_domain_name(domain: str) -> bool:
    """
    验证域名格式是否正确
    
    Args:
        domain: 域名
        
    Returns:
        是否有效
    """
    import re
    
    # 基本的域名格式验证
    pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
    
    if not domain or len(domain) > 253:
        return False
    
    return bool(re.match(pattern, domain))


def validate_nameservers(nameservers: list) -> bool:
    """
    验证名称服务器列表是否有效
    
    Args:
        nameservers: 名称服务器列表
        
    Returns:
        是否有效
    """
    if not nameservers or len(nameservers) == 0:
        return False
    
    for ns in nameservers:
        if not ns or not isinstance(ns, str):
            return False
        
        # 基本格式检查
        ns = ns.strip().lower()
        if not ns:
            return False
        
        # 检查是否为有效的域名格式
        if not validate_domain_name(ns.rstrip('.')):
            return False
    
    return True


def format_nameservers(nameservers: list) -> str:
    """
    格式化名称服务器列表为字符串
    
    Args:
        nameservers: 名称服务器列表
        
    Returns:
        格式化后的字符串
    """
    if not nameservers:
        return "无"
    
    # 格式化每个NS
    formatted_ns = []
    for ns in nameservers:
        if ns:
            formatted_ns.append(ns.strip().lower().rstrip('.'))
    
    return ', '.join(formatted_ns)


def parse_nameservers(nameservers_str: str) -> list:
    """
    解析名称服务器字符串为列表
    
    Args:
        nameservers_str: 名称服务器字符串（逗号分隔）
        
    Returns:
        名称服务器列表
    """
    if not nameservers_str:
        return []
    
    # 按逗号分割
    ns_list = []
    for ns in nameservers_str.split(','):
        ns = ns.strip()
        if ns:
            ns_list.append(ns)
    
    return ns_list 