"""
域名提供商抽象基类

定义了所有域名提供商必须实现的接口
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class DomainProvider(ABC):
    """域名提供商抽象基类"""
    
    def __init__(self, **config):
        """
        初始化提供商
        
        Args:
            **config: 提供商特定的配置参数
        """
        self.config = config
    
    @abstractmethod
    def get_domains(self) -> List[Dict[str, str]]:
        """
        获取所有域名列表
        
        Returns:
            域名信息列表，每个域名包含至少以下字段：
            - domain_name: 域名
            - registrar: 注册商名称
            - status: 域名状态（可选）
            - expire_date: 过期日期（可选）
        
        Raises:
            ProviderError: 当API调用失败时
        """
        pass
    
    @abstractmethod
    def get_domain_info(self, domain: str) -> Optional[Dict[str, str]]:
        """
        获取特定域名的详细信息
        
        Args:
            domain: 域名
            
        Returns:
            域名详细信息字典，如果域名不存在则返回None
            
        Raises:
            ProviderError: 当API调用失败时
        """
        pass
    
    @abstractmethod
    def validate_credentials(self) -> bool:
        """
        验证API凭据是否有效
        
        Returns:
            True表示凭据有效，False表示无效
            
        Raises:
            ProviderError: 当API调用失败时
        """
        pass
    
    def get_provider_name(self) -> str:
        """
        获取提供商名称
        
        Returns:
            提供商名称
        """
        return self.__class__.__name__.lower().replace('provider', '')


class ProviderError(Exception):
    """域名提供商错误"""
    
    def __init__(self, message: str, provider: str = None, error_code: str = None):
        """
        初始化错误
        
        Args:
            message: 错误消息
            provider: 提供商名称
            error_code: 错误代码
        """
        super().__init__(message)
        self.provider = provider
        self.error_code = error_code
    
    def __str__(self):
        error_parts = [self.args[0]]
        if self.provider:
            error_parts.append(f"Provider: {self.provider}")
        if self.error_code:
            error_parts.append(f"Code: {self.error_code}")
        return " | ".join(error_parts) 