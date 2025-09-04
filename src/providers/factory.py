"""
域名提供商工厂

使用工厂模式创建不同的域名提供商实例
"""

from typing import Dict, Type, Optional
from loguru import logger

from .base import DomainProvider, ProviderError
from .godaddy import GoDaddyProvider


class ProviderFactory:
    """域名提供商工厂类"""
    
    # 注册的提供商类
    _providers: Dict[str, Type[DomainProvider]] = {
        'godaddy': GoDaddyProvider,
    }
    
    @classmethod
    def create_provider(cls, provider_name: str, **config) -> DomainProvider:
        """
        创建域名提供商实例
        
        Args:
            provider_name: 提供商名称
            **config: 提供商配置参数
            
        Returns:
            域名提供商实例
            
        Raises:
            ProviderError: 当提供商不存在或创建失败时
        """
        provider_name = provider_name.lower()
        
        if provider_name not in cls._providers:
            available_providers = list(cls._providers.keys())
            raise ProviderError(
                f"不支持的域名提供商: {provider_name}. 支持的提供商: {available_providers}"
            )
        
        provider_class = cls._providers[provider_name]
        
        try:
            logger.debug(f"正在创建 {provider_name} 提供商实例...")
            
            if provider_name == 'godaddy':
                return cls._create_godaddy_provider(config)
            else:
                # 对于其他提供商，使用通用创建方法
                return provider_class(**config)
                
        except Exception as e:
            error_msg = f"创建 {provider_name} 提供商失败: {str(e)}"
            logger.error(error_msg)
            raise ProviderError(error_msg, provider=provider_name)
    
    @classmethod
    def _create_godaddy_provider(cls, config: Dict) -> GoDaddyProvider:
        """
        创建GoDaddy提供商实例
        
        Args:
            config: 配置字典
            
        Returns:
            GoDaddy提供商实例
        """
        api_key = config.get('api_key')
        api_secret = config.get('api_secret')
        client_type = config.get('client_type', 'new')  # 默认使用新客户端
        
        if not api_key:
            raise ProviderError("GoDaddy API Key不能为空", provider="godaddy")
        if not api_secret:
            raise ProviderError("GoDaddy API Secret不能为空", provider="godaddy")
        
        return GoDaddyProvider(api_key=api_key, api_secret=api_secret, client_type=client_type)
    
    @classmethod
    def register_provider(cls, name: str, provider_class: Type[DomainProvider]) -> None:
        """
        注册新的域名提供商
        
        Args:
            name: 提供商名称
            provider_class: 提供商类
        """
        name = name.lower()
        cls._providers[name] = provider_class
        logger.info(f"注册域名提供商: {name}")
    
    @classmethod
    def get_available_providers(cls) -> list[str]:
        """
        获取所有可用的提供商列表
        
        Returns:
            提供商名称列表
        """
        return list(cls._providers.keys())
    
    @classmethod
    def is_provider_supported(cls, provider_name: str) -> bool:
        """
        检查是否支持指定的提供商
        
        Args:
            provider_name: 提供商名称
            
        Returns:
            是否支持
        """
        return provider_name.lower() in cls._providers
    
    @classmethod
    def get_provider_config_requirements(cls, provider_name: str) -> Dict[str, str]:
        """
        获取指定提供商的配置要求
        
        Args:
            provider_name: 提供商名称
            
        Returns:
            配置要求字典
        """
        provider_name = provider_name.lower()
        
        requirements = {
            'godaddy': {
                'api_key': 'GoDaddy API密钥',
                'api_secret': 'GoDaddy API密文'
            }
        }
        
        return requirements.get(provider_name, {}) 