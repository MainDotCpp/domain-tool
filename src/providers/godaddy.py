"""
GoDaddy域名提供商实现

实现了GoDaddy API的域名管理功能
"""

from typing import List, Dict, Optional
from datetime import datetime
from loguru import logger
from .base import DomainProvider, ProviderError
from .godaddy_client import GoDaddyAPIClient

# 保持向后兼容性的导入
try:
    from godaddypy import Client, Account
    GODADDYPY_AVAILABLE = True
except ImportError:
    GODADDYPY_AVAILABLE = False
    logger.warning("godaddypy库不可用，将使用新的自建客户端")


class GoDaddyProvider(DomainProvider):
    """GoDaddy域名提供商实现"""
    
    def __init__(self, api_key: str, api_secret: str, client_type: str = 'new'):
        """
        初始化GoDaddy提供商
        
        Args:
            api_key: GoDaddy API密钥
            api_secret: GoDaddy API密文
            client_type: 客户端类型，'new' 或 'legacy'
        """
        super().__init__(api_key=api_key, api_secret=api_secret)
        
        if not api_key or not api_secret:
            raise ProviderError("GoDaddy API凭据不能为空", provider="godaddy")
        
        self.client_type = client_type
        
        try:
            if client_type == 'new':
                # 使用新的自建客户端
                self.api_client = GoDaddyAPIClient(api_key, api_secret)
                self.client = None  # 保持向后兼容
                logger.debug("GoDaddy新客户端初始化完成")
            else:
                # 使用传统的godaddypy客户端
                if not GODADDYPY_AVAILABLE:
                    raise ProviderError("godaddypy库不可用，请使用新客户端", provider="godaddy")
                
                self.account = Account(api_key=api_key, api_secret=api_secret)
                self.client = Client(self.account)
                self.api_client = None
                logger.debug("GoDaddy传统客户端初始化完成")
        except Exception as e:
            raise ProviderError(f"GoDaddy客户端初始化失败: {str(e)}", provider="godaddy")
    
    def get_domains(self) -> List[Dict[str, str]]:
        """
        获取GoDaddy账户下的所有域名
        
        Returns:
            域名信息列表
        """
        try:
            logger.info("正在从GoDaddy获取域名列表...")
            
            if self.client_type == 'new':
                # 使用新客户端
                domains_data = self.api_client.get_domains()
            else:
                # 使用传统客户端
                domains_data = self.client.get_domains()
            
            domains = []
            for domain_info in domains_data:
                domain = {
                    'domain_name': domain_info.get('domain', ''),
                    'registrar': 'godaddy',
                    'status': domain_info.get('status', ''),
                    'expire_date': self._parse_date(domain_info.get('expires')),
                    'created_date': self._parse_date(domain_info.get('createdAt')),
                    'renewable': domain_info.get('renewable', False),
                    'privacy': domain_info.get('privacy', False)
                }
                domains.append(domain)
            
            logger.info(f"成功获取到 {len(domains)} 个域名")
            return domains
            
        except Exception as e:
            error_msg = f"获取GoDaddy域名列表失败: {str(e)}"
            logger.error(error_msg)
            raise ProviderError(error_msg, provider="godaddy")
    
    def get_domain_info(self, domain: str) -> Optional[Dict[str, str]]:
        """
        获取特定域名的详细信息
        
        Args:
            domain: 域名
            
        Returns:
            域名详细信息
        """
        try:
            logger.debug(f"正在获取域名信息: {domain}")
            
            if self.client_type == 'new':
                # 使用新客户端
                domain_info = self.api_client.get_domain(domain)
            else:
                # 使用传统客户端
                domain_info = self.client.get_domain(domain)
            
            if not domain_info:
                logger.warning(f"域名不存在: {domain}")
                return None
            
            return {
                'domain_name': domain_info.get('domain', domain),
                'registrar': 'godaddy',
                'status': domain_info.get('status', ''),
                'expire_date': self._parse_date(domain_info.get('expires')),
                'created_date': self._parse_date(domain_info.get('createdAt')),
                'renewable': domain_info.get('renewable', False),
                'privacy': domain_info.get('privacy', False),
                'locked': domain_info.get('locked', False),
                'nameservers': domain_info.get('nameServers', [])
            }
            
        except Exception as e:
            error_msg = f"获取域名信息失败 [{domain}]: {str(e)}"
            logger.error(error_msg)
            raise ProviderError(error_msg, provider="godaddy")
    
    def validate_credentials(self) -> bool:
        """
        验证GoDaddy API凭据
        
        Returns:
            凭据是否有效
        """
        try:
            logger.debug("正在验证GoDaddy API凭据...")
            
            if self.client_type == 'new':
                # 使用新客户端
                success = self.api_client.test_connection()
            else:
                # 使用传统客户端
                self.client.get_domains()
                success = True
            
            if success:
                logger.info("GoDaddy API凭据验证成功")
                return True
            else:
                return False
            
        except Exception as e:
            logger.error(f"GoDaddy API凭据验证失败: {str(e)}")
            return False
    
    def get_nameservers(self, domain: str) -> List[str]:
        """
        获取域名当前的名称服务器记录
        
        Args:
            domain: 域名
            
        Returns:
            名称服务器列表
        """
        try:
            logger.debug(f"正在获取域名NS记录: {domain}")
            
            if self.client_type == 'new':
                # 使用新客户端
                nameservers = self.api_client.get_nameservers(domain)
            else:
                # 使用传统客户端 - 需要直接调用API
                # 注意：godaddypy可能不支持NS记录操作，这里使用新客户端作为后备
                logger.warning("传统客户端不支持NS记录操作，使用新客户端")
                if not hasattr(self, 'api_client') or self.api_client is None:
                    self.api_client = GoDaddyAPIClient(self.api_key, self.api_secret)
                nameservers = self.api_client.get_nameservers(domain)
            
            logger.debug(f"成功获取域名NS记录 {domain}: {nameservers}")
            return nameservers
            
        except Exception as e:
            logger.error(f"获取域名NS记录失败 {domain}: {str(e)}")
            return []
    
    def update_nameservers(self, domain: str, nameservers: List[str]) -> bool:
        """
        更新域名的名称服务器记录
        
        Args:
            domain: 域名
            nameservers: 新的名称服务器列表
            
        Returns:
            更新是否成功
        """
        try:
            logger.info(f"正在更新域名NS记录: {domain} -> {nameservers}")
            
            if self.client_type == 'new':
                # 使用新客户端
                success = self.api_client.update_nameservers(domain, nameservers)
            else:
                # 使用传统客户端 - 需要直接调用API
                # 注意：godaddypy可能不支持NS记录操作，这里使用新客户端作为后备
                logger.warning("传统客户端不支持NS记录操作，使用新客户端")
                if not hasattr(self, 'api_client') or self.api_client is None:
                    self.api_client = GoDaddyAPIClient(self.api_key, self.api_secret)
                success = self.api_client.update_nameservers(domain, nameservers)
            
            if success:
                logger.info(f"成功更新域名NS记录: {domain}")
            else:
                logger.error(f"更新域名NS记录失败: {domain}")
                
            return success
            
        except Exception as e:
            logger.error(f"更新域名NS记录失败 {domain}: {str(e)}")
            return False
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[str]:
        """
        解析日期字符串
        
        Args:
            date_str: 日期字符串
            
        Returns:
            格式化后的日期字符串或None
        """
        if not date_str:
            return None
        
        try:
            # GoDaddy API返回的日期格式通常是ISO格式
            if 'T' in date_str:
                # 移除时区信息和时间部分，只保留日期
                date_part = date_str.split('T')[0]
                return date_part
            else:
                return date_str
        except Exception:
            logger.warning(f"无法解析日期: {date_str}")
            return date_str 