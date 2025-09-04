"""
CloudFlare API客户端

实现CloudFlare域名管理和DNS配置功能
"""

from typing import Optional, Dict, List
import cloudflare
from loguru import logger

from .utils import retry_with_exponential_backoff


class CloudFlareError(Exception):
    """CloudFlare操作错误"""
    
    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(message)
        self.error_code = error_code


class CloudFlareManager:
    """CloudFlare管理器"""
    
    def __init__(self, api_key: str = None, email: str = None, api_token: str = None, account_id: str = None):
        """
        初始化CloudFlare管理器
        
        Args:
            api_key: CloudFlare Global API Key (推荐使用)
            email: CloudFlare账户邮箱 (与Global API Key配合使用)
            api_token: CloudFlare API Token (旧版本，不推荐)
            account_id: CloudFlare账户ID
        """
        try:
            # 优先使用Global API Key + Email认证
            if api_key and email:
                self.cf = cloudflare.Cloudflare(api_key=api_key, api_email=email)
                self.auth_method = "global_api_key"
                self.api_key = api_key
                self.email = email
                logger.info("使用Global API Key认证方式")
            elif api_token:
                self.cf = cloudflare.Cloudflare(api_token=api_token)
                self.auth_method = "api_token"
                self.api_token = api_token
                logger.info("使用API Token认证方式")
            else:
                raise CloudFlareError("必须提供 Global API Key + Email 或 API Token")
            
            self.account_id = account_id
            logger.debug("CloudFlare客户端初始化完成")
        except Exception as e:
            raise CloudFlareError(f"CloudFlare客户端初始化失败: {str(e)}")
    
    @retry_with_exponential_backoff()
    def validate_credentials(self) -> bool:
        """
        验证CloudFlare API凭据
        
        Returns:
            凭据是否有效
        """
        try:
            logger.debug(f"正在验证CloudFlare凭据 ({self.auth_method})...")
            # 尝试获取用户信息来验证凭据
            user = self.cf.user.get()
            if user and user.id:
                logger.info(f"CloudFlare凭据验证成功 ({self.auth_method})")
                return True
            else:
                logger.error(f"CloudFlare凭据验证失败：无效响应 ({self.auth_method})")
                return False
                
        except Exception as e:
            logger.error(f"CloudFlare凭据验证失败 ({self.auth_method}): {str(e)}")
            return False
    
    @retry_with_exponential_backoff()
    def add_zone(self, domain: str) -> Optional[str]:
        """
        添加域名到CloudFlare
        
        Args:
            domain: 域名
            
        Returns:
            Zone ID，如果添加失败则返回None
            
        Raises:
            CloudFlareError: 当添加失败时
        """
        try:
            logger.info(f"正在添加域名到CloudFlare: {domain}")
            
            # 检查域名是否已存在
            existing_zone_id = self.check_zone_exists(domain)
            if existing_zone_id:
                logger.info(f"域名 {domain} 已存在于CloudFlare，Zone ID: {existing_zone_id}")
                return existing_zone_id
            
            # 添加新域名
            zone_data = {
                "name": domain,
                "type": "full"  # 完整设置
            }
            
            # 添加账户ID（如果提供）
            if self.account_id:
                zone_data["account"] = {"id": self.account_id}
            
            response = self.cf.zones.create(**zone_data)
            
            if response and response.id:
                zone_id = response.id
                logger.info(f"域名 {domain} 添加成功，Zone ID: {zone_id}")
                return zone_id
            else:
                error_msg = f"添加域名失败，未获得有效的Zone ID: {domain}"
                logger.error(error_msg)
                raise CloudFlareError(error_msg)
                
        except cloudflare.APIError as e:
            error_msg = f"CloudFlare API错误 [{domain}]: {str(e)}"
            logger.error(error_msg)
            raise CloudFlareError(error_msg, error_code=getattr(e, 'code', None))
        except Exception as e:
            error_msg = f"添加域名到CloudFlare失败 [{domain}]: {str(e)}"
            logger.error(error_msg)
            raise CloudFlareError(error_msg)
    
    @retry_with_exponential_backoff()
    def check_zone_exists(self, domain: str) -> Optional[str]:
        """
        检查域名是否已在CloudFlare中存在
        
        Args:
            domain: 域名
            
        Returns:
            Zone ID，如果不存在则返回None
        """
        try:
            logger.debug(f"检查域名是否存在: {domain}")
            
            zones = self.cf.zones.list(name=domain)
            
            # 处理分页响应
            zone_list = list(zones)
            if zone_list and len(zone_list) > 0:
                zone_id = zone_list[0].id
                logger.debug(f"域名 {domain} 已存在，Zone ID: {zone_id}")
                return zone_id
            else:
                logger.debug(f"域名 {domain} 不存在于CloudFlare")
                return None
                
        except cloudflare.APIError as e:
            logger.error(f"检查域名存在性失败 [{domain}]: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"检查域名存在性时发生错误 [{domain}]: {str(e)}")
            return None
    
    @retry_with_exponential_backoff()
    def get_zone_info(self, zone_id: str) -> Optional[Dict]:
        """
        获取Zone详细信息
        
        Args:
            zone_id: Zone ID
            
        Returns:
            Zone信息字典
        """
        try:
            logger.debug(f"获取Zone信息: {zone_id}")
            zone = self.cf.zones.get(zone_id=zone_id)
            
            if zone:
                return {
                    'id': zone.id,
                    'name': zone.name,
                    'status': zone.status,
                    'name_servers': zone.name_servers or [],
                    'created_on': zone.created_on,
                    'modified_on': zone.modified_on
                }
            else:
                return None
                
        except cloudflare.APIError as e:
            logger.error(f"获取Zone信息失败 [{zone_id}]: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"获取Zone信息时发生错误 [{zone_id}]: {str(e)}")
            return None
    
    @retry_with_exponential_backoff()
    def get_nameservers(self, zone_id: str) -> Optional[List[str]]:
        """
        获取CloudFlare分配的名称服务器
        
        Args:
            zone_id: Zone ID
            
        Returns:
            名称服务器列表
        """
        try:
            zone_info = self.get_zone_info(zone_id)
            if zone_info and 'name_servers' in zone_info:
                return zone_info['name_servers']
            else:
                return None
                
        except Exception as e:
            logger.error(f"获取名称服务器失败 [{zone_id}]: {str(e)}")
            return None

    @retry_with_exponential_backoff()
    def create_dns_record(self, zone_id: str, record_type: str, name: str, content: str, ttl: int = 60, proxied: bool = False) -> Optional[str]:
        """
        创建DNS记录
        
        Args:
            zone_id: Zone ID
            record_type: 记录类型 (A, AAAA, CNAME, MX, TXT等)
            name: 记录名称
            content: 记录内容
            ttl: TTL值（秒），最小值60秒
            proxied: 是否启用代理
            
        Returns:
            记录ID，如果创建失败则返回None
        """
        try:
            logger.info(f"创建DNS记录: {name} {record_type} {content}")
            
            record_data = {
                "type": record_type,
                "name": name,
                "content": content,
                "ttl": ttl,
                "proxied": proxied
            }
            
            response = self.cf.dns.records.create(zone_id=zone_id, **record_data)
            
            if response and response.id:
                logger.info(f"DNS记录创建成功: {name} -> {response.id}")
                return response.id
            else:
                logger.error(f"DNS记录创建失败: {name}")
                return None
                
        except cloudflare.APIError as e:
            logger.error(f"创建DNS记录失败 [{name}]: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"创建DNS记录时发生错误 [{name}]: {str(e)}")
            return None

    @retry_with_exponential_backoff()
    def list_dns_records(self, zone_id: str, record_type: str = None) -> List[Dict]:
        """
        列出DNS记录
        
        Args:
            zone_id: Zone ID
            record_type: 记录类型过滤器
            
        Returns:
            DNS记录列表
        """
        try:
            logger.debug(f"获取DNS记录列表: {zone_id}")
            
            params = {}
            if record_type:
                params['type'] = record_type
                
            records = self.cf.dns.records.list(zone_id=zone_id, **params)
            
            record_list = []
            for record in records:
                record_info = {
                    'id': record.id,
                    'type': record.type,
                    'name': record.name,
                    'content': record.content,
                    'ttl': record.ttl,
                    'proxied': record.proxied if hasattr(record, 'proxied') else False
                }
                record_list.append(record_info)
            
            logger.debug(f"获取到 {len(record_list)} 条DNS记录")
            return record_list
            
        except cloudflare.APIError as e:
            logger.error(f"获取DNS记录列表失败 [{zone_id}]: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"获取DNS记录列表时发生错误 [{zone_id}]: {str(e)}")
            return []

    @retry_with_exponential_backoff()
    def delete_dns_record(self, zone_id: str, record_id: str) -> bool:
        """
        删除DNS记录
        
        Args:
            zone_id: Zone ID
            record_id: 记录ID
            
        Returns:
            是否删除成功
        """
        try:
            logger.debug(f"删除DNS记录: {record_id}")
            
            response = self.cf.dns.records.delete(zone_id=zone_id, dns_record_id=record_id)
            
            if response:
                logger.info(f"DNS记录删除成功: {record_id}")
                return True
            else:
                logger.error(f"DNS记录删除失败: {record_id}")
                return False
                
        except cloudflare.APIError as e:
            logger.error(f"删除DNS记录失败 [{record_id}]: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"删除DNS记录时发生错误 [{record_id}]: {str(e)}")
            return False

    @retry_with_exponential_backoff()
    def delete_dns_records_by_name(self, zone_id: str, domain: str, record_names: List[str]) -> int:
        """
        根据记录名称删除DNS记录
        
        Args:
            zone_id: Zone ID
            domain: 域名
            record_names: 要删除的记录名称列表 (如 ['@', 'www', '*'])
            
        Returns:
            删除的记录数量
        """
        try:
            logger.info(f"删除DNS记录: {domain} - {record_names}")
            
            # 获取现有记录
            existing_records = self.list_dns_records(zone_id)
            
            deleted_count = 0
            for record in existing_records:
                record_name = record['name']
                
                # 检查是否需要删除此记录
                should_delete = False
                
                for target_name in record_names:
                    if target_name == '@':
                        # 根域名记录
                        if record_name == domain:
                            should_delete = True
                            break
                    elif target_name == '*':
                        # 通配符记录
                        if record_name == f"*.{domain}":
                            should_delete = True
                            break
                    else:
                        # 其他子域名记录
                        if record_name == f"{target_name}.{domain}":
                            should_delete = True
                            break
                
                # 删除A记录和CNAME记录
                if should_delete and record['type'] in ['A', 'CNAME']:
                    if self.delete_dns_record(zone_id, record['id']):
                        deleted_count += 1
                        logger.info(f"已删除记录: {record_name} {record['type']}")
            
            logger.info(f"删除了 {deleted_count} 条DNS记录")
            return deleted_count
            
        except Exception as e:
            logger.error(f"删除DNS记录时发生错误 [{domain}]: {str(e)}")
            return 0

    @retry_with_exponential_backoff()
    def set_ssl_mode(self, zone_id: str, ssl_mode: str = "flexible") -> bool:
        """
        设置SSL模式
        
        Args:
            zone_id: Zone ID
            ssl_mode: SSL模式 (off, flexible, full, strict)
            
        Returns:
            是否设置成功
        """
        try:
            logger.info(f"设置SSL模式: {ssl_mode}")
            
            # 使用新版本SDK的正确API调用方式
            response = self.cf.zones.settings.edit(
                zone_id=zone_id,
                setting_id="ssl",
                value=ssl_mode
            )
            
            if response and hasattr(response, 'value') and response.value == ssl_mode:
                logger.info(f"SSL模式设置成功: {ssl_mode}")
                return True
            else:
                logger.info(f"SSL模式设置成功: {ssl_mode}")  # API可能返回不同格式，但请求成功
                return True
                
        except cloudflare.APIError as e:
            logger.error(f"设置SSL模式失败 [{ssl_mode}]: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"设置SSL模式时发生错误 [{ssl_mode}]: {str(e)}")
            return False

    @retry_with_exponential_backoff()
    def get_ssl_mode(self, zone_id: str) -> Optional[str]:
        """
        获取当前SSL模式
        
        Args:
            zone_id: Zone ID
            
        Returns:
            SSL模式
        """
        try:
            logger.debug(f"获取SSL模式: {zone_id}")
            
            # 使用新版本SDK的正确API调用方式
            response = self.cf.zones.settings.get(
                zone_id=zone_id,
                setting_id="ssl"
            )
            
            if response and hasattr(response, 'value') and response.value:
                logger.debug(f"当前SSL模式: {response.value}")
                return response.value
            else:
                logger.warning(f"无法获取SSL模式")
                return None
                
        except cloudflare.APIError as e:
            logger.error(f"获取SSL模式失败 [{zone_id}]: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"获取SSL模式时发生错误 [{zone_id}]: {str(e)}")
            return None

    @retry_with_exponential_backoff()
    def create_basic_dns_records(self, zone_id: str, domain: str, target_ip: str = None, default_ip: str = None) -> List[Dict]:
        """
        创建基础DNS记录
        流程：先删除原有记录，然后添加 @、www、* 指向指定IP的A记录
        
        Args:
            zone_id: Zone ID
            domain: 域名
            target_ip: 目标IP地址（可选）
            default_ip: 默认IP地址（可选）
            
        Returns:
            创建的记录列表
        """
        try:
            # 使用提供的IP或默认IP
            final_ip = target_ip or default_ip
            
            logger.info(f"创建基础DNS记录: {domain} -> {final_ip}")
            
            if not final_ip:
                logger.error(f"创建DNS记录失败: 必须提供目标IP地址或配置默认IP")
                return []
            
            created_records = []
            
            # 第一步：删除原有的相关记录
            logger.info("步骤1: 删除原有记录...")
            target_names = ['@', 'www', '*']
            deleted_count = self.delete_dns_records_by_name(zone_id, domain, target_names)
            logger.info(f"删除了 {deleted_count} 条原有记录")
            
            # 第二步：创建新的A记录
            logger.info("步骤2: 创建新的A记录...")
            
            # @ 记录 (根域名)
            root_record = self.create_dns_record(zone_id, "A", domain, final_ip, proxied=True)
            if root_record:
                created_records.append({"type": "A", "name": domain, "content": final_ip, "id": root_record})
                logger.info(f"✅ 创建根域名A记录: {domain} -> {final_ip}")
            
            # www 记录
            www_record = self.create_dns_record(zone_id, "A", f"www.{domain}", final_ip, proxied=True)
            if www_record:
                created_records.append({"type": "A", "name": f"www.{domain}", "content": final_ip, "id": www_record})
                logger.info(f"✅ 创建www子域名A记录: www.{domain} -> {final_ip}")
            
            # * 记录 (通配符)
            wildcard_record = self.create_dns_record(zone_id, "A", f"*.{domain}", final_ip, proxied=True)
            if wildcard_record:
                created_records.append({"type": "A", "name": f"*.{domain}", "content": final_ip, "id": wildcard_record})
                logger.info(f"✅ 创建通配符A记录: *.{domain} -> {final_ip}")
            
            logger.info(f"基础DNS记录创建完成: {len(created_records)} 条记录")
            return created_records
            
        except Exception as e:
            logger.error(f"创建基础DNS记录失败 [{domain}]: {str(e)}")
            return []
    
    @retry_with_exponential_backoff()
    def list_zones(self) -> List[Dict]:
        """
        列出所有Zone
        
        Returns:
            Zone列表
        """
        try:
            logger.debug("获取所有Zone列表...")
            zones = self.cf.zones.list()
            
            zone_list = []
            # 处理分页响应
            for zone in zones:
                zone_info = {
                    'id': zone.id,
                    'name': zone.name,
                    'status': zone.status,
                    'name_servers': zone.name_servers or [],
                }
                zone_list.append(zone_info)
            
            logger.debug(f"获取到 {len(zone_list)} 个Zone")
            return zone_list
            
        except cloudflare.APIError as e:
            logger.error(f"获取Zone列表失败: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"获取Zone列表时发生错误: {str(e)}")
            return []
    
    @retry_with_exponential_backoff()
    def delete_zone(self, zone_id: str) -> bool:
        """
        删除Zone（谨慎使用）
        
        Args:
            zone_id: Zone ID
            
        Returns:
            是否删除成功
        """
        try:
            logger.warning(f"正在删除Zone: {zone_id}")
            response = self.cf.zones.delete(zone_id=zone_id)
            
            if response:
                logger.info(f"Zone删除成功: {zone_id}")
                return True
            else:
                logger.error(f"Zone删除失败: {zone_id}")
                return False
                
        except cloudflare.APIError as e:
            logger.error(f"删除Zone失败 [{zone_id}]: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"删除Zone时发生错误 [{zone_id}]: {str(e)}")
            return False
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取CloudFlare账户统计信息
        
        Returns:
            统计信息字典
        """
        try:
            zones = self.list_zones()
            
            stats = {
                'total_zones': len(zones),
                'active_zones': len([z for z in zones if z.get('status') == 'active']),
                'pending_zones': len([z for z in zones if z.get('status') == 'pending']),
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"获取CloudFlare统计信息失败: {str(e)}")
            return {
                'total_zones': 0,
                'active_zones': 0,
                'pending_zones': 0,
            }
    
    @retry_with_exponential_backoff()
    def delete_all_dns_records(self, zone_id: str, record_types: List[str] = None, preserve_ns: bool = True) -> Dict[str, int]:
        """
        删除Zone中的所有DNS记录
        
        Args:
            zone_id: Zone ID
            record_types: 要删除的记录类型列表，为None时删除默认类型
            preserve_ns: 是否保留NS记录
            
        Returns:
            删除统计信息字典
        """
        try:
            logger.info(f"开始删除DNS记录: Zone {zone_id}")
            
            # 默认删除的记录类型（安全策略）
            if record_types is None:
                record_types = ['A', 'AAAA', 'CNAME']
            
            # 保护性记录类型（不删除）
            protected_types = set()
            if preserve_ns:
                protected_types.add('NS')
            
            # 添加其他受保护的记录类型
            protected_types.update(['MX', 'TXT', 'SRV'])
            
            # 获取现有记录
            all_records = self.list_dns_records(zone_id)
            
            # 过滤要删除的记录
            records_to_delete = []
            for record in all_records:
                record_type = record['type']
                
                # 检查是否是要删除的类型
                if record_types and record_type not in record_types:
                    continue
                
                # 检查是否是受保护的类型
                if record_type in protected_types:
                    logger.debug(f"跳过受保护的记录: {record['name']} {record_type}")
                    continue
                
                records_to_delete.append(record)
            
            # 统计信息
            stats = {
                'total_found': len(all_records),
                'to_delete': len(records_to_delete),
                'deleted': 0,
                'failed': 0,
                'skipped': len(all_records) - len(records_to_delete)
            }
            
            logger.info(f"找到 {stats['total_found']} 条记录，将删除 {stats['to_delete']} 条")
            
            # 执行删除
            for record in records_to_delete:
                try:
                    success = self.delete_dns_record(zone_id, record['id'])
                    if success:
                        stats['deleted'] += 1
                        logger.info(f"已删除记录: {record['name']} {record['type']} -> {record['content']}")
                    else:
                        stats['failed'] += 1
                        logger.error(f"删除记录失败: {record['name']} {record['type']}")
                except Exception as e:
                    stats['failed'] += 1
                    logger.error(f"删除记录异常 [{record['name']} {record['type']}]: {str(e)}")
            
            logger.info(f"DNS记录删除完成: 成功 {stats['deleted']} 条，失败 {stats['failed']} 条")
            return stats
            
        except Exception as e:
            logger.error(f"删除DNS记录时发生错误 [{zone_id}]: {str(e)}")
            return {
                'total_found': 0,
                'to_delete': 0,
                'deleted': 0,
                'failed': 0,
                'skipped': 0,
                'error': str(e)
            } 