"""
批量删除统计管理器

提供线程安全的DNS记录批量删除统计收集功能
"""

import threading
from typing import Dict, List, Optional
from loguru import logger


class BatchDeleteStats:
    """线程安全的批量删除统计管理器"""
    
    def __init__(self):
        """初始化统计管理器"""
        self._lock = threading.Lock()
        self._stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'total_records_deleted': 0,
            'total_records_skipped': 0
        }
        self._domain_results = []
        logger.debug("批量删除统计管理器初始化完成")
    
    def add_result(self, domain_name: str, status: str, 
                   deleted_count: int = 0, skipped_count: int = 0, 
                   error: Optional[str] = None, 
                   delete_info: Optional[Dict] = None) -> None:
        """
        添加单个域名的删除结果
        
        Args:
            domain_name: 域名
            status: 删除状态 ('success', 'failed', 'skipped')
            deleted_count: 删除的记录数量
            skipped_count: 跳过的记录数量
            error: 错误信息（可选）
            delete_info: 删除详细信息（可选）
        """
        with self._lock:
            self._stats['total'] += 1
            self._stats[status] += 1
            self._stats['total_records_deleted'] += deleted_count
            self._stats['total_records_skipped'] += skipped_count
            
            # 存储域名结果
            result = {
                'domain_name': domain_name,
                'status': status,
                'deleted_count': deleted_count,
                'skipped_count': skipped_count,
                'error': error,
                'delete_info': delete_info or {}
            }
            self._domain_results.append(result)
            
            logger.debug(f"添加删除结果: {domain_name} -> {status}")
    
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
        获取所有域名的删除结果
        
        Returns:
            域名结果列表
        """
        with self._lock:
            return self._domain_results.copy()
    
    def get_failed_domains(self) -> List[str]:
        """
        获取删除失败的域名列表
        
        Returns:
            失败域名列表
        """
        with self._lock:
            return [result['domain_name'] for result in self._domain_results 
                   if result['status'] == 'failed']
    
    def get_summary(self) -> str:
        """
        获取统计摘要文本
        
        Returns:
            摘要文本
        """
        with self._lock:
            stats = self._stats
            return (f"总计: {stats['total']} 个域名, "
                   f"成功: {stats['success']}, "
                   f"失败: {stats['failed']}, "
                   f"跳过: {stats['skipped']}, "
                   f"删除记录: {stats['total_records_deleted']} 条")
    
    def reset(self) -> None:
        """重置所有统计信息"""
        with self._lock:
            self._stats = {
                'total': 0,
                'success': 0,
                'failed': 0,
                'skipped': 0,
                'total_records_deleted': 0,
                'total_records_skipped': 0
            }
            self._domain_results = []
            logger.debug("批量删除统计信息已重置") 