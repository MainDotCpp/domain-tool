"""
自建GoDaddy API客户端

使用直接HTTP请求的方式调用GoDaddy API，避免第三方库的依赖问题
"""

import requests
from typing import List, Dict, Optional, Any
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from .base import ProviderError


class GoDaddyAPIClient:
    """自建GoDaddy API客户端"""
    
    def __init__(self, api_key: str, api_secret: str):
        """
        初始化GoDaddy API客户端
        
        Args:
            api_key: GoDaddy API密钥
            api_secret: GoDaddy API密文
        """
        if not api_key or not api_secret:
            raise ValueError("GoDaddy API凭据不能为空")
        
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api.godaddy.com/v1"
        
        # 创建会话并设置默认头部
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'sso-key {api_key}:{api_secret}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        
        logger.debug("GoDaddy API客户端初始化完成")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        统一的API请求处理
        
        Args:
            method: HTTP方法
            endpoint: API端点
            **kwargs: 额外的请求参数
            
        Returns:
            API响应数据
            
        Raises:
            ProviderError: API调用失败
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            logger.debug(f"发送{method.upper()}请求到: {url}")
            if 'params' in kwargs:
                logger.debug(f"查询参数: {kwargs['params']}")
            response = self.session.request(method, url, **kwargs)
            
            # 检查响应状态码
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                raise ProviderError("GoDaddy API认证失败，请检查API密钥和密文", provider="godaddy")
            elif response.status_code == 403:
                raise ProviderError("GoDaddy API访问被拒绝，请检查API权限", provider="godaddy")
            elif response.status_code == 404:
                raise ProviderError("GoDaddy API端点不存在", provider="godaddy")
            elif response.status_code == 429:
                raise ProviderError("GoDaddy API请求频率过高，请稍后重试", provider="godaddy")
            else:
                error_msg = f"GoDaddy API请求失败，状态码: {response.status_code}"
                if response.text:
                    try:
                        error_data = response.json()
                        if 'message' in error_data:
                            error_msg += f", 错误信息: {error_data['message']}"
                    except:
                        error_msg += f", 响应内容: {response.text}"
                raise ProviderError(error_msg, provider="godaddy")
                
        except requests.exceptions.RequestException as e:
            raise ProviderError(f"GoDaddy API网络请求失败: {str(e)}", provider="godaddy")
    
    def get_domains(self) -> List[Dict[str, Any]]:
        """
        获取GoDaddy账户下的所有域名（支持分页）
        
        Returns:
            域名信息列表
        """
        logger.info("正在从GoDaddy获取域名列表...")
        
        try:
            all_domains = []
            page_size = 1000  # 每页获取100个域名
            offset = 0
            max_retries = 3
            marker = None
            
            while True:
                params = {
                    'limit': page_size,
                    'marker': marker
                }
                
                page_num = offset // page_size + 1
                logger.info(f"正在获取第{page_num}页域名 (offset={offset}, limit={page_size})")
                
                # 尝试获取数据，带重试机制
                for attempt in range(max_retries):
                    try:
                        response_data = self._make_request('GET', '/domains', params=params)
                        break
                    except Exception as e:
                        logger.warning(f"第{attempt + 1}次尝试失败: {str(e)}")
                        if attempt == max_retries - 1:
                            raise
                        import time
                        time.sleep(2 ** attempt)  # 指数退避
                
                if not response_data:
                    logger.info("没有更多数据，结束获取")
                    break
                
                logger.info(f"第{page_num}页获取到 {len(response_data)} 个域名")
                marker = response_data[-1]['domain']
                all_domains.extend(response_data)
                
                # 如果返回的数据少于page_size，说明已经是最后一页
                if len(response_data) < page_size:
                    logger.info("已到达最后一页")
                    break
                
                offset += page_size
                
                # 添加简单的安全检查，避免无限循环
                if offset > 10000:  # 最多获取10000个域名
                    logger.warning("已达到最大域名数量限制(1000)，停止获取")
                    break
            
            logger.info(f"成功获取到 {len(all_domains)} 个域名")
            return all_domains
            
        except Exception as e:
            logger.error(f"获取GoDaddy域名列表失败: {str(e)}")
            # 如果分页失败，尝试使用原始方式获取
            logger.info("尝试使用原始方式获取域名列表...")
            try:
                response_data = self._make_request('GET', '/domains')
                logger.info(f"使用原始方式成功获取到 {len(response_data)} 个域名")
                return response_data
            except Exception as e2:
                logger.error(f"原始方式也失败: {str(e2)}")
                raise
    
    def get_domain(self, domain: str) -> Dict[str, Any]:
        """
        获取特定域名的详细信息
        
        Args:
            domain: 域名
            
        Returns:
            域名详细信息
        """
        logger.debug(f"正在获取域名信息: {domain}")
        
        try:
            response_data = self._make_request('GET', f'/domains/{domain}')
            logger.debug(f"成功获取域名信息: {domain}")
            return response_data
        except Exception as e:
            logger.error(f"获取域名信息失败 [{domain}]: {str(e)}")
            raise
    
    def get_domain_availability(self, domain: str) -> Dict[str, Any]:
        """
        检查域名可用性
        
        Args:
            domain: 域名
            
        Returns:
            域名可用性信息
        """
        logger.debug(f"正在检查域名可用性: {domain}")
        
        try:
            response_data = self._make_request('GET', f'/domains/available?domain={domain}')
            logger.debug(f"成功检查域名可用性: {domain}")
            return response_data
        except Exception as e:
            logger.error(f"检查域名可用性失败 [{domain}]: {str(e)}")
            raise
    
    def test_connection(self) -> bool:
        """
        测试与GoDaddy API的连接
        
        Returns:
            连接是否成功
        """
        try:
            logger.debug("正在测试GoDaddy API连接...")
            self._make_request('GET', '/domains', params={'limit': 1, 'offset': 0})
            logger.info("GoDaddy API连接测试成功")
            return True
        except Exception as e:
            logger.error(f"GoDaddy API连接测试失败: {str(e)}")
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
            response_data = self._make_request('GET', f'/domains/{domain}/records/NS')
            
            # 提取NS记录的数据
            nameservers = [record['data'].rstrip('.') for record in response_data if record['type'] == 'NS']
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
            
            # 构造NS记录数据
            records = []
            for ns in nameservers:
                records.append({
                    "type": "NS",
                    "name": "@",
                    "data": ns.rstrip('.') + '.',
                    "ttl": 600  # 设置为最小TTL值（5分钟）
                })
            
            # 发送PUT请求更新NS记录
            self._make_request('PUT', f'/domains/{domain}/records/NS', json=records)
            logger.info(f"成功更新域名NS记录: {domain}")
            return True
                
        except Exception as e:
            logger.error(f"更新域名NS记录失败 {domain}: {str(e)}")
            return False 
        





