"""
核心域名管理器

整合数据库、域名提供商和CloudFlare功能的核心业务逻辑
"""

from typing import Dict, List, Optional, Tuple
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger

from .config import Config
from .database import DomainDatabase
from .cloudflare_client import CloudFlareManager, CloudFlareError
from .providers.factory import ProviderFactory, ProviderError
from .utils import format_domain_name, validate_domain_name
from .refresh_stats import RefreshStats
from .batch_delete_stats import BatchDeleteStats


class DomainManagerError(Exception):
    """域名管理器错误"""
    pass


class ThreadSafeStats:
    """线程安全的统计收集器"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
        self._domain_results = []  # 存储每个域名的详细结果
    
    def increment(self, stat_name: str, value: int = 1):
        """增加统计计数"""
        with self._lock:
            self._stats[stat_name] += value
    
    def add_domain_result(self, result: Dict):
        """添加域名处理结果"""
        with self._lock:
            self._domain_results.append(result)
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        with self._lock:
            return self._stats.copy()
    
    def get_domain_results(self) -> List[Dict]:
        """获取所有域名的详细结果"""
        with self._lock:
            return self._domain_results.copy()


class DomainManager:
    """核心域名管理器"""
    
    def __init__(self, config: Config):
        """
        初始化域名管理器
        
        Args:
            config: 配置对象
        """
        self.config = config
        
        # 初始化数据库
        self.db = DomainDatabase(config.database_path)
        logger.debug(f"数据库初始化完成: {config.database_path}")
        
        # 初始化CloudFlare管理器
        if config.cloudflare_api_key and config.cloudflare_email:
            self.cf_manager = CloudFlareManager(
                api_key=config.cloudflare_api_key,
                email=config.cloudflare_email,
                account_id=config.cloudflare_account_id
            )
            logger.debug("CloudFlare管理器初始化完成 (使用Global API Key)")
        elif config.cloudflare_api_token:
            self.cf_manager = CloudFlareManager(
                api_token=config.cloudflare_api_token,
                account_id=config.cloudflare_account_id
            )
            logger.debug("CloudFlare管理器初始化完成 (使用API Token)")
        else:
            self.cf_manager = None
            logger.warning("CloudFlare API Key+Email 或 API Token 未配置，相关功能将不可用")
    
    def import_from_provider(self, provider_name: str) -> int:
        """
        从域名提供商导入域名
        
        Args:
            provider_name: 提供商名称
            
        Returns:
            导入的域名数量
            
        Raises:
            DomainManagerError: 导入失败时
        """
        try:
            logger.info(f"开始从 {provider_name} 导入域名...")
            
            # 创建提供商实例
            provider = self._create_provider(provider_name)
            
            # 验证提供商凭据
            if not provider.validate_credentials():
                raise DomainManagerError(f"{provider_name} API凭据验证失败")
            
            # 获取域名列表
            domains = provider.get_domains()
            logger.info(f"从 {provider_name} 获取到 {len(domains)} 个域名")
            
            # 导入域名到数据库
            imported_count = 0
            skipped_count = 0
            
            for domain_info in domains:
                domain_name = domain_info.get('domain_name', '')
                if not domain_name:
                    logger.warning(f"跳过无效域名: {domain_info}")
                    continue
                
                # 格式化域名
                domain_name = format_domain_name(domain_name)
                
                # 验证域名格式
                if not validate_domain_name(domain_name):
                    logger.warning(f"跳过无效域名格式: {domain_name}")
                    continue
                
                # 检查域名是否已存在
                if self.db.domain_exists(domain_name):
                    logger.debug(f"域名已存在，跳过: {domain_name}")
                    skipped_count += 1
                    continue
                
                # 添加域名到数据库
                try:
                    self.db.add_domain(
                        domain_name=domain_name,
                        registrar=provider_name,
                        purchase_date=domain_info.get('created_date')
                    )
                    imported_count += 1
                    logger.debug(f"导入域名: {domain_name}")
                    
                except sqlite3.IntegrityError:
                    logger.warning(f"域名已存在（并发创建）: {domain_name}")
                    skipped_count += 1
                except Exception as e:
                    logger.error(f"导入域名失败 [{domain_name}]: {str(e)}")
            
            logger.info(f"域名导入完成: 新增 {imported_count} 个，跳过 {skipped_count} 个")
            return imported_count
            
        except ProviderError as e:
            error_msg = f"提供商错误: {str(e)}"
            logger.error(error_msg)
            raise DomainManagerError(error_msg)
        except Exception as e:
            error_msg = f"导入域名失败: {str(e)}"
            logger.error(error_msg)
            raise DomainManagerError(error_msg)
    
    def sync_to_cloudflare(self, dry_run: bool = False, force_retry: bool = False) -> Dict[str, int]:
        """
        同步域名到CloudFlare（多线程版本）
        
        Args:
            dry_run: 是否为预览模式
            force_retry: 是否强制重试失败的域名
            
        Returns:
            统计信息字典
            
        Raises:
            DomainManagerError: 同步失败时
        """
        if not self.cf_manager:
            raise DomainManagerError("CloudFlare API Token未配置")
        
        try:
            logger.info(f"开始同步域名到CloudFlare {'(预览模式)' if dry_run else ''}")
            
            # 验证CloudFlare凭据
            if not self.cf_manager.validate_credentials():
                raise DomainManagerError("CloudFlare API凭据验证失败")
            
            # 获取待同步的域名
            if force_retry:
                # 包括失败的域名
                pending_domains = self.db.list_all_domains()
                pending_domains = [d for d in pending_domains if not d['cloudflare_added']]
            else:
                pending_domains = self.db.get_pending_domains()
            
            if not pending_domains:
                logger.info("没有待同步的域名")
                return {
                    'total': 0,
                    'success': 0,
                    'failed': 0,
                    'skipped': 0,
                    'domain_results': []
                }
            
            logger.info(f"找到 {len(pending_domains)} 个待同步域名")
            
            # 使用多线程处理
            max_workers = min(len(pending_domains), self.config.max_concurrent_threads)
            logger.info(f"使用 {max_workers} 个线程进行并发处理")
            
            # 线程安全的统计收集器
            stats = ThreadSafeStats()
            stats.increment('total', len(pending_domains))
            
            if dry_run:
                logger.info("[预览模式] 将要同步的域名:")
                for domain_record in pending_domains:
                    logger.info(f"  - {domain_record['domain_name']}")
                    # 为预览模式创建虚拟结果
                    preview_result = {
                        'domain_name': domain_record['domain_name'],
                        'status': 'preview',
                        'steps': {
                            'add_to_cloudflare': True,
                            'update_nameservers': True,
                            'create_dns_records': True,
                            'set_ssl_mode': True
                        }
                    }
                    stats.add_domain_result(preview_result)
                stats.increment('success', len(pending_domains))
                return {
                    **stats.get_stats(),
                    'domain_results': stats.get_domain_results()
                }
            
            # 使用线程池执行同步
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                futures = {
                    executor.submit(self._sync_single_domain, domain_record): domain_record
                    for domain_record in pending_domains
                }
                
                # 收集结果
                for future in as_completed(futures, timeout=self.config.thread_pool_timeout):
                    domain_record = futures[future]
                    domain_name = domain_record['domain_name']
                    
                    try:
                        result = future.result()
                        stats.add_domain_result(result)
                        
                        if result['status'] == 'success':
                            stats.increment('success')
                            logger.info(f"✅ 域名同步成功: {domain_name}")
                        else:
                            stats.increment('failed')
                            logger.error(f"❌ 域名同步失败: {domain_name}")
                    except Exception as e:
                        stats.increment('failed')
                        # 为异常情况创建结果记录
                        error_result = {
                            'domain_name': domain_name,
                            'status': 'failed',
                            'error': str(e),
                            'steps': {
                                'add_to_cloudflare': False,
                                'update_nameservers': False,
                                'create_dns_records': False,
                                'set_ssl_mode': False
                            }
                        }
                        stats.add_domain_result(error_result)
                        logger.error(f"❌ 域名同步异常 [{domain_name}]: {str(e)}")
            
            final_stats = stats.get_stats()
            logger.info(f"同步完成: 成功 {final_stats['success']} 个，失败 {final_stats['failed']} 个")
            
            # 返回包含详细结果的统计信息
            return {
                **final_stats,
                'domain_results': stats.get_domain_results()
            }
            
        except Exception as e:
            error_msg = f"同步到CloudFlare失败: {str(e)}"
            logger.error(error_msg)
            raise DomainManagerError(error_msg)
    
    def _sync_single_domain(self, domain_record: Dict) -> Dict[str, any]:
        """
        同步单个域名到CloudFlare
        
        Args:
            domain_record: 域名记录
            
        Returns:
            包含域名和各个步骤状态的字典
        """
        domain_name = domain_record['domain_name']
        domain_id = domain_record['id']
        
        # 初始化步骤状态
        steps = {
            'add_to_cloudflare': False,
            'update_nameservers': False,
            'create_dns_records': False,
            'set_ssl_mode': False
        }
        
        try:
            logger.info(f"🔄 正在处理域名: {domain_name}")
            
            # 步骤1: 添加域名到CloudFlare（如果已存在会返回现有Zone ID）
            zone_id = self.cf_manager.add_zone(domain_name)
            
            if not zone_id:
                # 同步失败
                self.db.update_sync_status(
                    domain_id=domain_id,
                    status='failed',
                    error='未获得有效的Zone ID'
                )
                logger.error(f"❌ 域名添加失败: {domain_name}")
                return {
                    'domain_name': domain_name,
                    'status': 'failed',
                    'error': '未获得有效的Zone ID',
                    'steps': steps
                }
            
            # 步骤1成功
            steps['add_to_cloudflare'] = True
            
            # 更新数据库状态
            self.db.update_sync_status(
                domain_id=domain_id,
                status='synced',
                zone_id=zone_id
            )
            logger.info(f"✅ 域名添加成功: {domain_name} -> {zone_id}")
            
            # 步骤2: 获取CloudFlare名称服务器并更新NS记录
            ns_success = False
            try:
                nameservers = self.cf_manager.get_nameservers(zone_id)
                if nameservers:
                    logger.info(f"🔗 CloudFlare名称服务器 [{domain_name}]: {', '.join(nameservers)}")
                    
                    # 检查是否需要更新GoDaddy NS记录
                    if self.config.auto_update_nameservers:
                        try:
                            ns_updated = self.update_domain_nameservers(domain_name, 'godaddy', nameservers)
                            if ns_updated:
                                self.db.update_nameserver_status(domain_id, True)
                                logger.info(f"✅ 已更新域名NS记录: {domain_name}")
                                ns_success = True
                            else:
                                logger.warning(f"⚠️ NS记录更新失败: {domain_name}")
                        except Exception as e:
                            logger.error(f"❌ 更新NS记录时发生错误 [{domain_name}]: {str(e)}")
                    else:
                        # 如果配置为不自动更新NS，则认为此步骤跳过（成功）
                        ns_success = True
                        logger.info(f"⏭️ 跳过NS记录更新: {domain_name}")
                else:
                    logger.warning(f"⚠️ 无法获取CloudFlare名称服务器: {domain_name}")
            except Exception as e:
                logger.error(f"❌ 获取名称服务器时发生错误 [{domain_name}]: {str(e)}")
            
            steps['update_nameservers'] = ns_success
            
            # 步骤3: 创建DNS记录
            dns_success = False
            try:
                dns_records = self.cf_manager.create_basic_dns_records(zone_id, domain_name, None, self.config.default_target_ip)
                if dns_records:
                    logger.info(f"✅ DNS记录创建成功: {len(dns_records)} 条记录")
                    dns_success = True
                else:
                    logger.warning(f"⚠️ DNS记录创建失败: {domain_name}")
            except Exception as e:
                logger.error(f"❌ 创建DNS记录时发生错误 [{domain_name}]: {str(e)}")
            
            steps['create_dns_records'] = dns_success
            
            # 步骤4: 设置SSL模式
            ssl_success = False
            try:
                ssl_set = self.cf_manager.set_ssl_mode(zone_id, "flexible")
                if ssl_set:
                    logger.info(f"✅ SSL模式设置成功: flexible")
                    ssl_success = True
                else:
                    logger.warning(f"⚠️ SSL模式设置失败（不影响其他功能）")
            except Exception as e:
                logger.warning(f"⚠️ 设置SSL模式失败: {str(e)}（不影响其他功能）")
            
            steps['set_ssl_mode'] = ssl_success
            
            logger.info(f"🎉 域名同步完成: {domain_name}")
            return {
                'domain_name': domain_name,
                'status': 'success',
                'steps': steps
            }
            
        except CloudFlareError as e:
            # CloudFlare API错误
            error_msg = str(e)
            self.db.update_sync_status(
                domain_id=domain_id,
                status='failed',
                error=error_msg
            )
            logger.error(f"❌ CloudFlare错误 [{domain_name}]: {error_msg}")
            return {
                'domain_name': domain_name,
                'status': 'failed',
                'error': error_msg,
                'steps': steps
            }
        
        except Exception as e:
            # 其他错误
            error_msg = str(e)
            self.db.update_sync_status(
                domain_id=domain_id,
                status='failed',
                error=error_msg
            )
            logger.error(f"❌ 同步域名时发生错误 [{domain_name}]: {error_msg}")
            return {
                'domain_name': domain_name,
                'status': 'failed',
                'error': error_msg,
                'steps': steps
            }
    
    def add_manual_domain(self, domain: str, registrar: str = 'manual') -> bool:
        """
        手动添加域名
        
        Args:
            domain: 域名
            registrar: 注册商名称
            
        Returns:
            是否添加成功
        """
        try:
            # 格式化域名
            domain = format_domain_name(domain)
            
            # 验证域名格式
            if not validate_domain_name(domain):
                logger.error(f"无效的域名格式: {domain}")
                return False
            
            # 检查域名是否已存在
            if self.db.domain_exists(domain):
                logger.warning(f"域名已存在: {domain}")
                return True
            
            # 添加域名到数据库
            domain_id = self.db.add_domain(
                domain_name=domain,
                registrar=registrar
            )
            
            logger.info(f"手动添加域名成功: {domain} (ID: {domain_id})")
            return True
            
        except Exception as e:
            logger.error(f"手动添加域名失败 [{domain}]: {str(e)}")
            return False
    
    def list_domains(self, status_filter: Optional[str] = None) -> List[Dict]:
        """
        列出域名
        
        Args:
            status_filter: 状态过滤器
            
        Returns:
            域名列表
        """
        try:
            domains = self.db.list_all_domains(status_filter)
            logger.debug(f"获取域名列表: {len(domains)} 个域名")
            return domains
        except Exception as e:
            logger.error(f"获取域名列表失败: {str(e)}")
            return []
    
    def get_statistics(self) -> Dict[str, any]:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        try:
            # 数据库统计
            db_stats = self.db.get_stats()
            
            # 添加NS统计（如果数据库支持）
            try:
                ns_updated_domains = self.db.get_domains_with_ns_status(ns_updated=True)
                ns_not_updated_domains = self.db.get_domains_with_ns_status(ns_updated=False)
                synced_not_updated = [d for d in ns_not_updated_domains if d['cloudflare_added']]
                
                db_stats['ns_updated'] = len(ns_updated_domains)
                db_stats['ns_pending'] = len(synced_not_updated)
            except Exception as e:
                logger.debug(f"获取NS统计失败，数据库可能需要升级: {str(e)}")
                db_stats['ns_updated'] = 'N/A'
                db_stats['ns_pending'] = 'N/A'
            
            # CloudFlare统计
            cf_stats = {}
            if self.cf_manager:
                try:
                    cf_stats = self.cf_manager.get_stats()
                except Exception as e:
                    logger.error(f"获取CloudFlare统计信息失败: {str(e)}")
                    cf_stats = {'error': str(e)}
            
            return {
                'database': db_stats,
                'cloudflare': cf_stats,
                'config_valid': self.config.is_valid()
            }
            
        except Exception as e:
            logger.error(f"获取统计信息失败: {str(e)}")
            return {
                'database': {},
                'cloudflare': {},
                'config_valid': False,
                'error': str(e)
            }
    
    def update_domain_nameservers(self, domain: str, provider: str, nameservers: List[str]) -> bool:
        """
        更新域名的名称服务器记录
        
        Args:
            domain: 域名
            provider: 提供商名称
            nameservers: 新的名称服务器列表
            
        Returns:
            更新是否成功
        """
        try:
            # 创建提供商实例
            provider_instance = self._create_provider(provider)
            
            # 获取原始NS记录（用于备份）
            try:
                original_ns = provider_instance.get_nameservers(domain)
                logger.info(f"域名 {domain} 的原始NS记录: {original_ns}")
            except Exception as e:
                logger.warning(f"获取原始NS记录失败 [{domain}]: {str(e)}")
                original_ns = []
            
            # 直接更新NS记录，无需确认
            logger.info(f"正在更新域名 {domain} 的NS记录为: {', '.join(nameservers)}")
            success = provider_instance.update_nameservers(domain, nameservers)
            
            if success:
                # 保存原始NS记录到数据库
                domain_record = self.db.get_domain_by_name(domain)
                if domain_record:
                    self.db.update_nameserver_status(domain_record['id'], True, original_ns)
                
                logger.info(f"✅ 成功更新域名 {domain} 的NS记录")
                return True
            else:
                logger.error(f"❌ 更新域名 {domain} 的NS记录失败")
                return False
                
        except Exception as e:
            logger.error(f"更新域名NS记录时发生错误 [{domain}]: {str(e)}")
            return False
    
    def _create_provider(self, provider_name: str):
        """
        创建域名提供商实例
        
        Args:
            provider_name: 提供商名称
            
        Returns:
            提供商实例
        """
        if provider_name.lower() == 'godaddy':
            return ProviderFactory.create_provider(
                provider_name='godaddy',
                api_key=self.config.godaddy_api_key,
                api_secret=self.config.godaddy_api_secret,
                client_type=self.config.godaddy_client_type
            )
        else:
            raise DomainManagerError(f"不支持的提供商: {provider_name}")

    def migrate_domain_complete(self, domain: str, target_ip: str = None, ssl_mode: str = "flexible") -> Dict[str, any]:
        """
        完整域名迁移（一键完成）
        
        Args:
            domain: 域名
            target_ip: 目标IP地址（可选）
            ssl_mode: SSL模式 (off, flexible, full, strict)
            
        Returns:
            迁移结果字典
        """
        if not self.cf_manager:
            raise DomainManagerError("CloudFlare API Token未配置")
        
        try:
            logger.info(f"开始完整域名迁移: {domain}")
            
            # 验证CloudFlare凭据
            if not self.cf_manager.validate_credentials():
                raise DomainManagerError("CloudFlare API凭据验证失败")
            
            result = {
                'domain': domain,
                'success': False,
                'steps': {
                    'add_to_cloudflare': False,
                    'update_nameservers': False,
                    'create_dns_records': False,
                    'set_ssl_mode': False
                },
                'zone_id': None,
                'dns_records': [],
                'errors': []
            }
            
            # 步骤1: 添加域名到CloudFlare
            logger.info(f"步骤1: 添加域名到CloudFlare")
            try:
                zone_id = self.cf_manager.add_zone(domain)
                if zone_id:
                    result['zone_id'] = zone_id
                    result['steps']['add_to_cloudflare'] = True
                    logger.info(f"✅ 域名添加成功: {domain} -> {zone_id}")
                else:
                    result['errors'].append("添加域名到CloudFlare失败")
                    return result
            except Exception as e:
                result['errors'].append(f"添加域名到CloudFlare失败: {str(e)}")
                return result
            
            # 步骤2: 更新名称服务器
            logger.info(f"步骤2: 更新名称服务器")
            try:
                # 获取CloudFlare名称服务器
                nameservers = self.cf_manager.get_nameservers(zone_id)
                if nameservers:
                    logger.info(f"CloudFlare名称服务器: {', '.join(nameservers)}")
                    
                    # 更新GoDaddy NS记录
                    ns_updated = self.update_domain_nameservers(domain, 'godaddy', nameservers)
                    if ns_updated:
                        result['steps']['update_nameservers'] = True
                        logger.info(f"✅ NS记录更新成功: {domain}")
                    else:
                        result['errors'].append("NS记录更新失败")
                else:
                    result['errors'].append("无法获取CloudFlare名称服务器")
            except Exception as e:
                result['errors'].append(f"更新名称服务器失败: {str(e)}")
            
            # 步骤3: 创建DNS记录
            logger.info(f"步骤3: 创建DNS记录")
            try:
                dns_records = self.cf_manager.create_basic_dns_records(zone_id, domain, target_ip, self.config.default_target_ip)
                if dns_records:
                    result['dns_records'] = dns_records
                    result['steps']['create_dns_records'] = True
                    logger.info(f"✅ DNS记录创建成功: {len(dns_records)} 条记录")
                else:
                    result['errors'].append("DNS记录创建失败")
            except Exception as e:
                result['errors'].append(f"创建DNS记录失败: {str(e)}")
            
            # 步骤4: 设置SSL模式
            logger.info(f"步骤4: 设置SSL模式为 {ssl_mode}")
            try:
                ssl_set = self.cf_manager.set_ssl_mode(zone_id, ssl_mode)
                if ssl_set:
                    result['steps']['set_ssl_mode'] = True
                    logger.info(f"✅ SSL模式设置成功: {ssl_mode}")
                else:
                    result['steps']['set_ssl_mode'] = False
                    logger.warning(f"⚠️ SSL模式设置失败: {ssl_mode}（不影响其他功能）")
            except Exception as e:
                result['steps']['set_ssl_mode'] = False
                logger.warning(f"⚠️ 设置SSL模式失败: {str(e)}（不影响其他功能）")
            
            # 更新数据库状态
            domain_record = self.db.get_domain_by_name(domain)
            if domain_record:
                self.db.update_sync_status(
                    domain_id=domain_record['id'],
                    status='synced',
                    zone_id=zone_id
                )
                if result['steps']['update_nameservers']:
                    self.db.update_nameserver_status(domain_record['id'], True)
            
            # 判断整体成功
            critical_steps = ['add_to_cloudflare', 'update_nameservers']
            result['success'] = all(result['steps'][step] for step in critical_steps)
            
            if result['success']:
                logger.info(f"🎉 域名迁移完成: {domain}")
            else:
                logger.warning(f"⚠️ 域名迁移部分失败: {domain}")
            
            return result
            
        except Exception as e:
            error_msg = f"域名迁移失败: {str(e)}"
            logger.error(error_msg)
            raise DomainManagerError(error_msg)

    def get_migration_status(self, domain: str) -> Dict[str, any]:
        """
        获取域名迁移状态
        
        Args:
            domain: 域名
            
        Returns:
            迁移状态信息
        """
        try:
            domain_record = self.db.get_domain_by_name(domain)
            if not domain_record:
                return {'error': '域名不存在'}
            
            status = {
                'domain': domain,
                'in_cloudflare': domain_record['cloudflare_added'],
                'zone_id': domain_record['cloudflare_zone_id'],
                'ns_updated': domain_record.get('ns_updated', False),
                'sync_status': domain_record['sync_status'],
                'last_sync': domain_record['last_sync_attempt']
            }
            
            # 如果域名已在CloudFlare，获取更多信息
            if domain_record['cloudflare_added'] and domain_record['cloudflare_zone_id']:
                zone_id = domain_record['cloudflare_zone_id']
                
                # 获取SSL模式
                try:
                    ssl_mode = self.cf_manager.get_ssl_mode(zone_id)
                    status["ssl_mode"] = ssl_mode
                except Exception as e:
                    logger.debug(f"获取SSL模式失败: {str(e)}")
                    status["ssl_mode"] = "unknown"  # 设置为unknown而不是None
                except Exception as e:
                    logger.debug(f"获取SSL模式失败: {str(e)}")
                    status['ssl_mode'] = 'unknown'  # 设置为unknown而不是None
                
                # 获取DNS记录数量
                dns_records = self.cf_manager.list_dns_records(zone_id)
                status['dns_records_count'] = len(dns_records)
                
                # 获取Zone状态
                zone_info = self.cf_manager.get_zone_info(zone_id)
                if zone_info:
                    status['zone_status'] = zone_info.get('status')
            
            return status
            
        except Exception as e:
            logger.error(f"获取迁移状态失败 [{domain}]: {str(e)}")
            return {'error': str(e)}
    
    def validate_all_credentials(self) -> Dict[str, bool]:
        """
        验证所有API凭据
        
        Returns:
            验证结果字典
        """
        results = {}
        
        # 验证GoDaddy凭据
        try:
            if self.config.godaddy_api_key and self.config.godaddy_api_secret:
                provider = self._create_provider('godaddy')
                results['godaddy'] = provider.validate_credentials()
            else:
                results['godaddy'] = False
        except Exception as e:
            logger.error(f"验证GoDaddy凭据失败: {str(e)}")
            results['godaddy'] = False
        
        # 验证CloudFlare凭据
        try:
            if self.cf_manager:
                results['cloudflare'] = self.cf_manager.validate_credentials()
            else:
                results['cloudflare'] = False
        except Exception as e:
            logger.error(f"验证CloudFlare凭据失败: {str(e)}")
            results['cloudflare'] = False
        
        return results
    
    def refresh_domains_info(self, mode: str = 'basic', dry_run: bool = False) -> Dict[str, int]:
        """
        批量刷新域名信息（多线程版本）
        
        Args:
            mode: 刷新模式 ('basic', 'full')
            dry_run: 是否为预览模式
            
        Returns:
            统计信息字典
            
        Raises:
            DomainManagerError: 刷新失败时
        """
        try:
            logger.info(f"开始刷新域名信息 {'(预览模式)' if dry_run else ''} - 模式: {mode}")
            
            # 获取所有域名
            domains = self.db.get_domains_for_refresh()
            
            if not domains:
                logger.info("没有域名需要刷新")
                return {
                    'total': 0,
                    'success': 0,
                    'failed': 0,
                    'skipped': 0
                }
            
            logger.info(f"找到 {len(domains)} 个域名需要刷新")
            
            # 使用多线程处理
            max_workers = min(len(domains), self.config.max_concurrent_threads)
            logger.info(f"使用 {max_workers} 个线程进行并发处理")
            
            # 初始化统计管理器
            stats = RefreshStats()
            
            if dry_run:
                # 预览模式：只显示将要执行的操作
                for domain in domains:
                    stats.add_result(domain['domain_name'], 'skipped', error="预览模式")
                    logger.info(f"预览刷新: {domain['domain_name']} (模式: {mode})")
            else:
                # 实际执行刷新
                with ThreadPoolExecutor(max_workers=max_workers, 
                                      thread_name_prefix="refresh-worker") as executor:
                    
                    # 提交所有任务
                    future_to_domain = {
                        executor.submit(self._refresh_single_domain, domain, mode): domain
                        for domain in domains
                    }
                    
                    # 收集结果
                    for future in as_completed(future_to_domain):
                        domain = future_to_domain[future]
                        try:
                            result = future.result(timeout=self.config.thread_pool_timeout)
                            stats.add_result(
                                result['domain_name'],
                                result['status'],
                                result.get('error'),
                                result.get('refresh_info')
                            )
                        except Exception as e:
                            error_msg = f"刷新任务异常: {str(e)}"
                            stats.add_result(domain['domain_name'], 'failed', error_msg)
                            logger.error(f"刷新任务异常 [{domain['domain_name']}]: {error_msg}")
            
            final_stats = stats.get_stats()
            logger.info(f"刷新完成: 成功 {final_stats['success']} 个，失败 {final_stats['failed']} 个")
            
            return final_stats
            
        except Exception as e:
            error_msg = f"批量刷新域名信息失败: {str(e)}"
            logger.error(error_msg)
            raise DomainManagerError(error_msg)
    
    def _refresh_single_domain(self, domain_record: Dict, mode: str) -> Dict[str, any]:
        """
        刷新单个域名信息
        
        Args:
            domain_record: 域名记录
            mode: 刷新模式 ('basic', 'full')
            
        Returns:
            刷新结果字典
        """
        domain_name = domain_record['domain_name']
        domain_id = domain_record['id']
        
        try:
            logger.info(f"🔄 正在刷新域名: {domain_name} (模式: {mode})")
            
            if mode == 'basic':
                return self._refresh_basic_info(domain_record)
            elif mode == 'full':
                return self._refresh_full_info(domain_record)
            else:
                raise ValueError(f"不支持的刷新模式: {mode}")
                
        except Exception as e:
            error_msg = str(e)
            self.db.update_refresh_status(domain_id, 'failed', error_msg)
            logger.error(f"❌ 刷新域名失败 [{domain_name}]: {error_msg}")
            return {
                'domain_name': domain_name,
                'status': 'failed',
                'error': error_msg
            }
    
    def _refresh_basic_info(self, domain_record: Dict) -> Dict[str, any]:
        """
        基础模式刷新：验证CloudFlare Zone状态和NS同步状态，检查和更新zone_id
        
        Args:
            domain_record: 域名记录
            
        Returns:
            刷新结果字典
        """
        domain_name = domain_record['domain_name']
        domain_id = domain_record['id']
        
        refresh_info = {}
        zone_id_updated = False
        
        try:
            if not self.cf_manager:
                logger.warning(f"CloudFlare管理器未初始化，跳过CloudFlare相关检查: {domain_name}")
                self.db.update_refresh_status(domain_id, 'success')
                return {
                    'domain_name': domain_name,
                    'status': 'success',
                    'refresh_info': refresh_info
                }
            
            current_zone_id = domain_record.get('cloudflare_zone_id')
            
            # 情况1: 数据库中有zone_id，验证其有效性
            if current_zone_id:
                logger.debug(f"检查现有Zone ID: {domain_name} -> {current_zone_id}")
                zone_info = self.cf_manager.get_zone_info(current_zone_id)
                
                if zone_info:
                    # Zone ID有效，更新状态信息
                    refresh_info['cf_zone_status'] = zone_info.get('status')
                    logger.debug(f"Zone状态: {domain_name} -> {zone_info.get('status')}")
                else:
                    # Zone ID无效，需要重新查找
                    logger.warning(f"Zone ID无效，尝试重新查找: {domain_name}")
                    current_zone_id = None  # 重置，触发重新查找
            
            # 情况2: 数据库中没有zone_id或zone_id无效，尝试查找
            if not current_zone_id:
                logger.info(f"查找域名的Zone ID: {domain_name}")
                found_zone_id = self.cf_manager.check_zone_exists(domain_name)
                
                if found_zone_id:
                    # 找到了zone_id，更新数据库
                    logger.info(f"找到Zone ID: {domain_name} -> {found_zone_id}")
                    self.db.update_sync_status(
                        domain_id=domain_id,
                        status='synced',
                        zone_id=found_zone_id
                    )
                    zone_id_updated = True
                    
                    # 获取Zone状态信息
                    zone_info = self.cf_manager.get_zone_info(found_zone_id)
                    if zone_info:
                        refresh_info['cf_zone_status'] = zone_info.get('status')
                        logger.debug(f"更新Zone状态: {domain_name} -> {zone_info.get('status')}")
                else:
                    # 在CloudFlare中未找到该域名
                    logger.info(f"域名未在CloudFlare中找到: {domain_name}")
                    if domain_record.get('cloudflare_added'):
                        # 如果数据库标记为已添加但找不到，更新状态
                        self.db.update_sync_status(
                            domain_id=domain_id,
                            status='failed',
                            zone_id=None,
                            error='域名未在CloudFlare中找到'
                        )
                        zone_id_updated = True
                    refresh_info['cf_zone_status'] = 'not_found'
            
            # 更新刷新信息到数据库
            if refresh_info:
                self.db.update_domain_refresh_info(domain_id, **refresh_info)
            
            # 更新刷新状态
            self.db.update_refresh_status(domain_id, 'success')
            
            success_msg = f"✅ 基础刷新成功: {domain_name}"
            if zone_id_updated:
                success_msg += " (Zone ID已更新)"
            logger.info(success_msg)
            
            return {
                'domain_name': domain_name,
                'status': 'success',
                'refresh_info': refresh_info,
                'zone_id_updated': zone_id_updated
            }
            
        except Exception as e:
            error_msg = str(e)
            self.db.update_refresh_status(domain_id, 'failed', error_msg)
            logger.error(f"❌ 基础刷新失败 [{domain_name}]: {error_msg}")
            return {
                'domain_name': domain_name,
                'status': 'failed',
                'error': error_msg
            }
    
    def _refresh_full_info(self, domain_record: Dict) -> Dict[str, any]:
        """
        完整模式刷新：获取详细的域名和CloudFlare信息
        
        Args:
            domain_record: 域名记录
            
        Returns:
            刷新结果字典
        """
        domain_name = domain_record['domain_name']
        domain_id = domain_record['id']
        registrar = domain_record.get('registrar', 'godaddy')
        
        refresh_info = {}
        
        try:
            # 先执行基础刷新
            basic_result = self._refresh_basic_info(domain_record)
            if basic_result['status'] == 'success':
                refresh_info.update(basic_result.get('refresh_info', {}))
            
            # 从域名注册商获取详细信息
            try:
                provider = self._create_provider(registrar)
                domain_info = provider.get_domain_info(domain_name)
                
                if domain_info:
                    # 更新域名详细信息
                    refresh_info.update({
                        'expire_date': domain_info.get('expire_date'),
                        'domain_status': domain_info.get('status'),
                        'locked': domain_info.get('locked', False),
                        'privacy': domain_info.get('privacy', False)
                    })
                    logger.debug(f"获取域名详细信息: {domain_name}")
                else:
                    logger.warning(f"无法获取域名详细信息: {domain_name}")
                    
            except Exception as e:
                logger.warning(f"获取域名注册商信息失败 [{domain_name}]: {str(e)}")
            
            # 从CloudFlare获取详细信息
            if domain_record.get('cloudflare_zone_id') and self.cf_manager:
                zone_id = domain_record['cloudflare_zone_id']
                
                try:
                    # 获取SSL模式
                    ssl_mode = self.cf_manager.get_ssl_mode(zone_id)
                    if ssl_mode:
                        refresh_info['cf_ssl_mode'] = ssl_mode
                    
                    # 获取DNS记录数量
                    dns_records = self.cf_manager.list_dns_records(zone_id)
                    refresh_info['dns_records_count'] = len(dns_records)
                    
                    logger.debug(f"获取CloudFlare详细信息: {domain_name}")
                    
                except Exception as e:
                    logger.warning(f"获取CloudFlare详细信息失败 [{domain_name}]: {str(e)}")
            
            # 更新刷新信息到数据库
            if refresh_info:
                self.db.update_domain_refresh_info(domain_id, **refresh_info)
            
            # 更新刷新状态
            self.db.update_refresh_status(domain_id, 'success')
            
            logger.info(f"✅ 完整刷新成功: {domain_name}")
            return {
                'domain_name': domain_name,
                'status': 'success',
                'refresh_info': refresh_info
            }
            
        except Exception as e:
            error_msg = str(e)
            self.db.update_refresh_status(domain_id, 'failed', error_msg)
            logger.error(f"❌ 完整刷新失败 [{domain_name}]: {error_msg}")
            return {
                'domain_name': domain_name,
                'status': 'failed',
                'error': error_msg
            }
    
    def delete_domain_dns_records(self, domain: str, record_types: List[str] = None, dry_run: bool = False) -> Dict[str, any]:
        """
        删除指定域名的所有DNS记录
        
        Args:
            domain: 域名
            record_types: 要删除的记录类型列表，为None时删除默认安全类型
            dry_run: 是否为预览模式
            
        Returns:
            删除结果字典
            
        Raises:
            DomainManagerError: 删除失败时
        """
        try:
            logger.info(f"开始删除域名DNS记录: {domain} {'(预览模式)' if dry_run else ''}")
            
            # 验证域名是否存在
            domain_record = self.db.get_domain_by_name(domain)
            if not domain_record:
                raise DomainManagerError(f"域名不存在: {domain}")
            
            # 检查域名是否已同步到CloudFlare
            if not domain_record.get('cloudflare_added') or not domain_record.get('cloudflare_zone_id'):
                raise DomainManagerError(f"域名 {domain} 未同步到CloudFlare")
            
            zone_id = domain_record['cloudflare_zone_id']
            
            # 检查CloudFlare管理器是否可用
            if not self.cf_manager:
                raise DomainManagerError("CloudFlare管理器未初始化")
            
            # 验证Zone是否仍然存在
            zone_info = self.cf_manager.get_zone_info(zone_id)
            if not zone_info:
                raise DomainManagerError(f"Zone不存在或已被删除: {zone_id}")
            
            # 获取当前DNS记录用于预览
            current_records = self.cf_manager.list_dns_records(zone_id)
            
            # 过滤要删除的记录（用于预览）
            default_types = ['A', 'AAAA', 'CNAME'] if record_types is None else record_types
            protected_types = {'NS', 'MX', 'TXT', 'SRV'}
            
            records_to_delete = []
            for record in current_records:
                record_type = record['type']
                if record_type in default_types and record_type not in protected_types:
                    records_to_delete.append(record)
            
            result = {
                'domain': domain,
                'zone_id': zone_id,
                'current_records': current_records,
                'records_to_delete': records_to_delete,
                'total_records': len(current_records),
                'will_delete': len(records_to_delete),
                'dry_run': dry_run
            }
            
            if dry_run:
                # 预览模式，不执行实际删除
                logger.info(f"预览删除DNS记录: {domain} - 将删除 {len(records_to_delete)} 条记录")
                result['status'] = 'preview'
                return result
            
            # 执行实际删除
            logger.info(f"执行删除DNS记录: {domain}")
            delete_stats = self.cf_manager.delete_all_dns_records(
                zone_id=zone_id,
                record_types=record_types,
                preserve_ns=True  # 始终保留NS记录以确保安全
            )
            
            # 合并删除统计信息
            result.update(delete_stats)
            result['status'] = 'completed'
            
            # 记录操作到数据库（可选）
            if delete_stats.get('deleted', 0) > 0:
                # 这里可以添加操作日志记录
                logger.info(f"成功删除域名DNS记录: {domain} - {delete_stats['deleted']} 条记录")
            
            return result
            
        except CloudFlareError as e:
            error_msg = f"CloudFlare API错误: {str(e)}"
            logger.error(f"删除DNS记录失败 [{domain}]: {error_msg}")
            raise DomainManagerError(error_msg)
        except Exception as e:
            error_msg = f"删除DNS记录失败: {str(e)}"
            logger.error(f"删除DNS记录异常 [{domain}]: {error_msg}")
            raise DomainManagerError(error_msg)

    def batch_delete_dns_records(self, domains: List[str], record_types: List[str] = None, 
                                dry_run: bool = False) -> Dict[str, any]:
        """
        批量删除多个域名的DNS记录（多线程版本）
        
        Args:
            domains: 域名列表
            record_types: 要删除的记录类型列表，为None时删除默认安全类型
            dry_run: 是否为预览模式
            
        Returns:
            批量删除结果字典
            
        Raises:
            DomainManagerError: 删除失败时
        """
        try:
            logger.info(f"开始批量删除DNS记录 {'(预览模式)' if dry_run else ''} - {len(domains)} 个域名")
            
            if not domains:
                logger.info("没有域名需要删除DNS记录")
                return {
                    'total': 0,
                    'success': 0,
                    'failed': 0,
                    'skipped': 0,
                    'total_records_deleted': 0,
                    'domain_results': []
                }
            
            # 初始化统计管理器
            stats = BatchDeleteStats()
            
            # 使用多线程并发删除
            max_threads = min(self.config.max_concurrent_threads, len(domains))
            logger.info(f"使用 {max_threads} 个线程进行批量删除")
            
            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                # 提交所有删除任务
                future_to_domain = {
                    executor.submit(self._delete_single_domain_dns, domain, record_types, dry_run, stats): domain
                    for domain in domains
                }
                
                # 等待所有任务完成
                for future in as_completed(future_to_domain, timeout=self.config.thread_pool_timeout):
                    domain_name = future_to_domain[future]
                    try:
                        result = future.result()
                        logger.debug(f"域名 {domain_name} 删除完成: {result['status']}")
                    except Exception as e:
                        logger.error(f"域名 {domain_name} 删除异常: {str(e)}")
                        stats.add_result(
                            domain_name=domain_name,
                            status='failed',
                            error=f"删除异常: {str(e)}"
                        )
            
            # 获取最终统计
            final_stats = stats.get_stats()
            domain_results = stats.get_domain_results()
            
            logger.info(f"批量删除完成: {stats.get_summary()}")
            
            return {
                'total': final_stats['total'],
                'success': final_stats['success'],
                'failed': final_stats['failed'],
                'skipped': final_stats['skipped'],
                'total_records_deleted': final_stats['total_records_deleted'],
                'total_records_skipped': final_stats['total_records_skipped'],
                'domain_results': domain_results
            }
            
        except Exception as e:
            error_msg = f"批量删除DNS记录失败: {str(e)}"
            logger.error(error_msg)
            raise DomainManagerError(error_msg)
    
    def _delete_single_domain_dns(self, domain: str, record_types: List[str], 
                                 dry_run: bool, stats: BatchDeleteStats) -> Dict[str, any]:
        """
        删除单个域名的DNS记录（线程安全版本）
        
        Args:
            domain: 域名
            record_types: 记录类型列表
            dry_run: 是否为预览模式
            stats: 统计管理器
            
        Returns:
            删除结果字典
        """
        try:
            logger.debug(f"开始删除单个域名DNS记录: {domain}")
            
            # 调用现有的单域名删除方法
            result = self.delete_domain_dns_records(domain, record_types, dry_run)
            
            # 确定状态
            if result.get('error'):
                status = 'failed'
                stats.add_result(
                    domain_name=domain,
                    status=status,
                    deleted_count=result.get('deleted', 0),
                    skipped_count=result.get('skipped', 0),
                    error=result.get('error'),
                    delete_info=result
                )
            elif result.get('deleted', 0) > 0:
                status = 'success'
                stats.add_result(
                    domain_name=domain,
                    status=status,
                    deleted_count=result.get('deleted', 0),
                    skipped_count=result.get('skipped', 0),
                    delete_info=result
                )
            else:
                status = 'skipped'
                stats.add_result(
                    domain_name=domain,
                    status=status,
                    deleted_count=0,
                    skipped_count=result.get('total_found', 0),
                    delete_info=result
                )
            
            logger.debug(f"域名 {domain} DNS删除完成: {status}")
            
            return {
                'domain_name': domain,
                'status': status,
                'result': result
            }
            
        except Exception as e:
            error_msg = f"删除域名 {domain} DNS记录失败: {str(e)}"
            logger.error(error_msg)
            
            stats.add_result(
                domain_name=domain,
                status='failed',
                error=error_msg
            )
            
            return {
                'domain_name': domain,
                'status': 'failed',
                'error': error_msg
            }