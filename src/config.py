"""
配置管理模块

实现环境变量 + 配置文件混合配置方案
配置优先级：命令行参数 > 环境变量 > 配置文件 > 默认值
"""

import os
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from loguru import logger


class Config:
    """配置管理器"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_file: 配置文件路径，如果为None则使用默认路径
        """
        self.config_file = config_file or str(Path() / 'config.json')
        self.config_dir = Path(self.config_file).parent
        
        # 加载.env文件
        load_dotenv()
        
        # 初始化配置属性
        self._init_config_properties()
        
        # 加载配置
        self.load_config()
    
    def _init_config_properties(self):
        """初始化配置属性"""
        # GoDaddy配置
        self.godaddy_api_key: Optional[str] = None
        self.godaddy_api_secret: Optional[str] = None
        
        # CloudFlare配置
        self.cloudflare_api_key: Optional[str] = None
        self.cloudflare_email: Optional[str] = None
        self.cloudflare_api_token: Optional[str] = None  # 向后兼容
        self.cloudflare_account_id: Optional[str] = None
        
        # 数据库配置
        self.database_path: str = "./domains.db"
        
        # 日志配置
        self.log_level: str = "INFO"
        self.log_file: Optional[str] = None
        
        # 重试配置
        self.max_retries: int = 3
        self.retry_delay: int = 2
        
        # 多线程配置
        self.max_concurrent_threads: int = 5  # 最大并发线程数
        self.thread_pool_timeout: int = 300  # 线程池超时时间（秒）
        
        # GoDaddy客户端类型配置
        self.godaddy_client_type: str = 'new'  # 'new' 或 'legacy'
        
        # 名称服务器更新配置
        self.auto_update_nameservers: bool = True  # 是否自动更新NS记录
        self.confirm_ns_update: bool = False  # 是否在更新NS前确认（默认关闭）
        self.ns_update_timeout: int = 30  # NS更新超时时间（秒）
        self.ns_verification_delay: int = 5  # NS验证延迟时间（秒）
        
        # DNS记录配置
        self.default_target_ip: Optional[str] = None  # 默认目标IP地址
        
        # 刷新配置
        self.refresh_batch_size: int = 50  # 每批处理的域名数量
        self.refresh_timeout: int = 30  # 单个域名刷新超时时间（秒）
        self.enable_full_refresh: bool = True  # 是否启用完整刷新模式
        
        # 其他配置
        self.dry_run: bool = False
        self.verbose: bool = False
    
    def load_config(self) -> None:
        """加载配置，按优先级顺序：环境变量 > 配置文件 > 默认值"""
        # 先从配置文件加载
        file_config = self._load_from_file()
        
        # GoDaddy配置
        self.godaddy_api_key = (
            os.getenv('GODADDY_API_KEY') or 
            file_config.get('godaddy_api_key')
        )
        self.godaddy_api_secret = (
            os.getenv('GODADDY_API_SECRET') or 
            file_config.get('godaddy_api_secret')
        )
        
        # CloudFlare配置
        self.cloudflare_api_key = (
            os.getenv('CLOUDFLARE_API_KEY') or 
            file_config.get('cloudflare_api_key')
        )
        self.cloudflare_email = (
            os.getenv('CLOUDFLARE_EMAIL') or 
            file_config.get('cloudflare_email')
        )
        self.cloudflare_api_token = (
            os.getenv('CLOUDFLARE_API_TOKEN') or 
            file_config.get('cloudflare_api_token')
        )
        self.cloudflare_account_id = (
            os.getenv('CLOUDFLARE_ACCOUNT_ID') or 
            file_config.get('cloudflare_account_id')
        )
        
        # 数据库配置
        self.database_path = (
            os.getenv('DATABASE_PATH') or 
            file_config.get('database_path') or 
            self.database_path
        )
        
        # 日志配置
        self.log_level = (
            os.getenv('LOG_LEVEL') or 
            file_config.get('log_level') or 
            self.log_level
        )
        self.log_file = (
            os.getenv('LOG_FILE') or 
            file_config.get('log_file')
        )
        
        # 重试配置
        try:
            self.max_retries = int(
                os.getenv('MAX_RETRIES') or 
                file_config.get('max_retries') or 
                self.max_retries
            )
        except ValueError:
            logger.warning("无效的MAX_RETRIES值，使用默认值")
        
        try:
            self.retry_delay = int(
                os.getenv('RETRY_DELAY') or 
                file_config.get('retry_delay') or 
                self.retry_delay
            )
        except ValueError:
            logger.warning("无效的RETRY_DELAY值，使用默认值")
        
        # 多线程配置
        try:
            self.max_concurrent_threads = int(
                os.getenv('MAX_CONCURRENT_THREADS') or 
                file_config.get('max_concurrent_threads') or 
                self.max_concurrent_threads
            )
        except ValueError:
            logger.warning("无效的MAX_CONCURRENT_THREADS值，使用默认值")
            
        try:
            self.thread_pool_timeout = int(
                os.getenv('THREAD_POOL_TIMEOUT') or 
                file_config.get('thread_pool_timeout') or 
                self.thread_pool_timeout
            )
        except ValueError:
            logger.warning("无效的THREAD_POOL_TIMEOUT值，使用默认值")
        
        # GoDaddy客户端类型配置
        self.godaddy_client_type = (
            os.getenv('GODADDY_CLIENT_TYPE') or 
            file_config.get('godaddy_client_type') or 
            self.godaddy_client_type
        )
        
        # 名称服务器更新配置
        self.auto_update_nameservers = (
            os.getenv('AUTO_UPDATE_NAMESERVERS', '').lower() == 'true' if os.getenv('AUTO_UPDATE_NAMESERVERS') else
            file_config.get('auto_update_nameservers', self.auto_update_nameservers)
        )
        
        self.confirm_ns_update = (
            os.getenv('CONFIRM_NS_UPDATE', '').lower() == 'true' if os.getenv('CONFIRM_NS_UPDATE') else
            file_config.get('confirm_ns_update', self.confirm_ns_update)
        )
        
        try:
            self.ns_update_timeout = int(
                os.getenv('NS_UPDATE_TIMEOUT') or 
                file_config.get('ns_update_timeout') or 
                self.ns_update_timeout
            )
        except ValueError:
            logger.warning("无效的NS_UPDATE_TIMEOUT值，使用默认值")
            
        try:
            self.ns_verification_delay = int(
                os.getenv('NS_VERIFICATION_DELAY') or 
                file_config.get('ns_verification_delay') or 
                self.ns_verification_delay
            )
        except ValueError:
            logger.warning("无效的NS_VERIFICATION_DELAY值，使用默认值")
        
        # DNS记录配置
        self.default_target_ip = (
            os.getenv('DEFAULT_TARGET_IP') or 
            file_config.get('default_target_ip') or 
            self.default_target_ip
        )
        
        # 刷新配置
        try:
            self.refresh_batch_size = int(
                os.getenv('REFRESH_BATCH_SIZE') or 
                file_config.get('refresh_batch_size') or 
                self.refresh_batch_size
            )
        except ValueError:
            logger.warning("无效的REFRESH_BATCH_SIZE值，使用默认值")
            
        try:
            self.refresh_timeout = int(
                os.getenv('REFRESH_TIMEOUT') or 
                file_config.get('refresh_timeout') or 
                self.refresh_timeout
            )
        except ValueError:
            logger.warning("无效的REFRESH_TIMEOUT值，使用默认值")
            
        self.enable_full_refresh = (
            os.getenv('ENABLE_FULL_REFRESH', '').lower() == 'true' if os.getenv('ENABLE_FULL_REFRESH') else
            file_config.get('enable_full_refresh', self.enable_full_refresh)
        )
        
        logger.debug("配置加载完成")
    
    def _load_from_file(self) -> Dict[str, Any]:
        """从配置文件加载配置"""
        if not os.path.exists(self.config_file):
            logger.debug(f"配置文件不存在: {self.config_file}")
            return {}
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.debug(f"从配置文件加载配置: {self.config_file}")
                return config
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"加载配置文件失败: {e}")
            return {}
    
    def save_config(self) -> None:
        """保存配置到文件"""
        # 确保配置目录存在
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        config_data = {
            'godaddy_api_key': self.godaddy_api_key,
            'godaddy_api_secret': self.godaddy_api_secret,
            'cloudflare_api_key': self.cloudflare_api_key,
            'cloudflare_email': self.cloudflare_email,
            'cloudflare_api_token': self.cloudflare_api_token,
            'cloudflare_account_id': self.cloudflare_account_id,
            'database_path': self.database_path,
            'log_level': self.log_level,
            'log_file': self.log_file,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'godaddy_client_type': self.godaddy_client_type,
            'auto_update_nameservers': self.auto_update_nameservers,
            'confirm_ns_update': self.confirm_ns_update,
            'ns_update_timeout': self.ns_update_timeout,
            'ns_verification_delay': self.ns_verification_delay,
            'default_target_ip': self.default_target_ip,
            'max_concurrent_threads': self.max_concurrent_threads,
            'thread_pool_timeout': self.thread_pool_timeout,
            'refresh_batch_size': self.refresh_batch_size,
            'refresh_timeout': self.refresh_timeout,
            'enable_full_refresh': self.enable_full_refresh
        }
        
        # 移除None值
        config_data = {k: v for k, v in config_data.items() if v is not None}
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
                logger.info(f"配置已保存到: {self.config_file}")
        except IOError as e:
            logger.error(f"保存配置文件失败: {e}")
    
    def validate_config(self) -> List[str]:
        """
        验证配置的完整性
        
        Returns:
            错误信息列表，如果为空则表示配置有效
        """
        errors = []
        
        # 检查必需的配置
        if not self.godaddy_api_key:
            errors.append("缺少GoDaddy API Key配置")
        
        if not self.godaddy_api_secret:
            errors.append("缺少GoDaddy API Secret配置")
        
        # 检查CloudFlare认证配置
        if not (self.cloudflare_api_key and self.cloudflare_email) and not self.cloudflare_api_token:
            errors.append("缺少CloudFlare认证配置 (需要API Key+Email 或 API Token)")
        
        if self.cloudflare_api_key and not self.cloudflare_email:
            errors.append("使用CloudFlare API Key时必须配置Email")
        
        if self.cloudflare_email and not self.cloudflare_api_key:
            errors.append("使用CloudFlare Email时必须配置API Key")
        
        if not self.cloudflare_account_id:
            errors.append("缺少CloudFlare Account ID配置")
        
        # 检查数据库路径
        if not self.database_path:
            errors.append("缺少数据库路径配置")
        
        # 检查日志级别
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.log_level.upper() not in valid_log_levels:
            errors.append(f"无效的日志级别: {self.log_level}")
        
        # 检查重试配置
        if self.max_retries < 0:
            errors.append("max_retries不能为负数")
        
        if self.retry_delay < 0:
            errors.append("retry_delay不能为负数")
        
        # 检查多线程配置
        if self.max_concurrent_threads < 1:
            errors.append("max_concurrent_threads必须大于0")
            
        if self.thread_pool_timeout < 0:
            errors.append("thread_pool_timeout不能为负数")
        
        # 检查GoDaddy客户端类型
        valid_client_types = ['new', 'legacy']
        if self.godaddy_client_type not in valid_client_types:
            errors.append(f"无效的GoDaddy客户端类型: {self.godaddy_client_type}")
        
        # 检查NS更新配置
        if self.ns_update_timeout < 0:
            errors.append("ns_update_timeout不能为负数")
        
        if self.ns_verification_delay < 0:
            errors.append("ns_verification_delay不能为负数")
        
        return errors
    
    def is_valid(self) -> bool:
        """检查配置是否有效"""
        return len(self.validate_config()) == 0
    
    def get_config_summary(self) -> Dict[str, Any]:
        """获取配置摘要（隐藏敏感信息）"""
        return {
            'godaddy_api_key': '***' if self.godaddy_api_key else None,
            'godaddy_api_secret': '***' if self.godaddy_api_secret else None,
            'cloudflare_api_key': '***' if self.cloudflare_api_key else None,
            'cloudflare_email': '***' if self.cloudflare_email else None,
            'cloudflare_api_token': '***' if self.cloudflare_api_token else None,
            'cloudflare_account_id': '***' if self.cloudflare_account_id else None,
            'database_path': self.database_path,
            'log_level': self.log_level,
            'log_file': self.log_file,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'godaddy_client_type': self.godaddy_client_type,
            'auto_update_nameservers': self.auto_update_nameservers,
            'confirm_ns_update': self.confirm_ns_update,
            'ns_update_timeout': self.ns_update_timeout,
            'ns_verification_delay': self.ns_verification_delay,
            'default_target_ip': self.default_target_ip,
            'max_concurrent_threads': self.max_concurrent_threads,
            'thread_pool_timeout': self.thread_pool_timeout,
            'config_file': self.config_file
        }
    
    def update_from_dict(self, config_dict: Dict[str, Any]) -> None:
        """从字典更新配置"""
        for key, value in config_dict.items():
            if hasattr(self, key):
                setattr(self, key, value)
                logger.debug(f"更新配置: {key} = {value}")
    
    def interactive_setup(self) -> None:
        """交互式配置设置"""
        print("=== Domain Tool 配置设置 ===\n")
        
        # GoDaddy配置
        print("1. GoDaddy API配置")
        self.godaddy_api_key = input(f"GoDaddy API Key [{self.godaddy_api_key or ''}]: ").strip() or self.godaddy_api_key
        self.godaddy_api_secret = input(f"GoDaddy API Secret [{self.godaddy_api_secret or ''}]: ").strip() or self.godaddy_api_secret
        
        # CloudFlare配置
        print("\n2. CloudFlare API配置")
        print("选择认证方式:")
        print("1. Global API Key + Email (推荐)")
        print("2. API Token (旧版本)")
        auth_choice = input("请选择认证方式 [1]: ").strip() or "1"
        
        if auth_choice == "1":
            self.cloudflare_api_key = input(f"CloudFlare API Key [{self.cloudflare_api_key or ''}]: ").strip() or self.cloudflare_api_key
            self.cloudflare_email = input(f"CloudFlare Email [{self.cloudflare_email or ''}]: ").strip() or self.cloudflare_email
        else:
            self.cloudflare_api_token = input(f"CloudFlare API Token [{self.cloudflare_api_token or ''}]: ").strip() or self.cloudflare_api_token
        
        self.cloudflare_account_id = input(f"CloudFlare Account ID [{self.cloudflare_account_id or ''}]: ").strip() or self.cloudflare_account_id
        
        # 数据库配置
        print("\n3. 数据库配置")
        self.database_path = input(f"数据库路径 [{self.database_path}]: ").strip() or self.database_path
        
        # 日志配置
        print("\n4. 日志配置")
        self.log_level = input(f"日志级别 [{self.log_level}]: ").strip() or self.log_level
        self.log_file = input(f"日志文件路径 (可选) [{self.log_file or ''}]: ").strip() or self.log_file
        
        # DNS记录配置
        print("\n5. DNS记录配置")
        self.default_target_ip = input(f"默认目标IP地址 (可选) [{self.default_target_ip or ''}]: ").strip() or self.default_target_ip
        
        # 多线程配置
        print("\n6. 多线程配置")
        self.max_concurrent_threads = int(input(f"最大并发线程数 [{self.max_concurrent_threads}]: ").strip() or self.max_concurrent_threads)
        self.thread_pool_timeout = int(input(f"线程池超时时间 (秒) [{self.thread_pool_timeout}]: ").strip() or self.thread_pool_timeout)
        
        # 保存配置
        print("\n正在保存配置...")
        self.save_config()
        
        # 验证配置
        errors = self.validate_config()
        if errors:
            print("\n⚠️  配置验证失败:")
            for error in errors:
                print(f"  - {error}")
        else:
            print("\n✅ 配置设置完成!")


def get_default_config() -> Config:
    """获取默认配置实例"""
    return Config() 