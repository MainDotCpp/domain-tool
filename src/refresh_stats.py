"""
刷新统计管理器

提供线程安全的域名刷新统计收集功能
"""

import threading
from typing import Dict, List, Optional
from loguru import logger


class RefreshStats:
    """线程安全的刷新统计管理器"""
    
    def __init__(self):
        """初始化统计管理器"""
        self._lock = threading.Lock()
        self._stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
        self._domain_results = []
        logger.debug("刷新统计管理器初始化完成")
    
    def add_result(self, domain_name: str, status: str, error: Optional[str] = None, 
                   refresh_info: Optional[Dict] = None) -> None:
        """
        添加单个域名的刷新结果
        
        Args:
            domain_name: 域名
            status: 刷新状态 ('success', 'failed', 'skipped')
            error: 错误信息（可选）
            refresh_info: 刷新详细信息（可选）
        """
        with self._lock:
            self._stats['total'] += 1
            
            if status == 'success':
                self._stats['success'] += 1
            elif status == 'failed':
                self._stats['failed'] += 1
            elif status == 'skipped':
                self._stats['skipped'] += 1
            
            # 记录域名结果
            result = {
                'domain_name': domain_name,
                'status': status,
                'error': error,
                'refresh_info': refresh_info or {}
            }
            self._domain_results.append(result)
            
            logger.debug(f"添加刷新结果: {domain_name} -> {status}")
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取当前统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            return self._stats.copy()
    
    def get_domain_results(self) -> List[Dict]:
        """
        获取所有域名的刷新结果
        
        Returns:
            域名结果列表
        """
        with self._lock:
            return self._domain_results.copy()
    
    def reset(self) -> None:
        """重置统计信息"""
        with self._lock:
            self._stats = {
                'total': 0,
                'success': 0,
                'failed': 0,
                'skipped': 0
            }
            self._domain_results = []
            logger.debug("刷新统计信息已重置")
    
    def log_summary(self) -> None:
        """输出统计摘要到日志"""
        stats = self.get_stats()
        logger.info(f"刷新统计: 总计 {stats['total']}, 成功 {stats['success']}, "
                   f"失败 {stats['failed']}, 跳过 {stats['skipped']}") 