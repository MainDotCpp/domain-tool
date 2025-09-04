"""
数据库管理模块

提供SQLite数据库的所有操作功能
"""

import sqlite3
import os
import json
from datetime import datetime
from typing import List, Dict, Optional
from loguru import logger


class DomainDatabase:
    """域名数据库管理器"""
    
    def __init__(self, db_path: str):
        """
        初始化数据库连接
        
        Args:
            db_path: SQLite数据库文件路径
        """
        self.db_path = db_path
        self.ensure_db_directory()
        self.create_tables()
        
        # 自动执行数据库迁移
        self._migrate_database()
    
    def ensure_db_directory(self):
        """确保数据库目录存在"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
    
    def get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 使用字典形式返回结果
        return conn
    
    def create_tables(self) -> None:
        """创建数据库表结构"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 创建domains表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS domains (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain_name TEXT UNIQUE NOT NULL,
                    registrar TEXT DEFAULT 'godaddy',
                    purchase_date DATE,
                    cloudflare_added BOOLEAN DEFAULT FALSE,
                    cloudflare_zone_id TEXT,
                    last_sync_attempt TIMESTAMP,
                    sync_status TEXT DEFAULT 'pending',
                    error_message TEXT,
                    ns_updated BOOLEAN DEFAULT FALSE,
                    ns_update_date TIMESTAMP,
                    original_nameservers TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sync_status ON domains(sync_status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_cloudflare_added ON domains(cloudflare_added)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_domain_name ON domains(domain_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ns_updated ON domains(ns_updated)')
            
            conn.commit()
            logger.info("数据库表结构创建完成")
    
    def add_domain(self, domain_name: str, registrar: str = 'godaddy', purchase_date: Optional[str] = None) -> int:
        """
        添加域名到数据库
        
        Args:
            domain_name: 域名
            registrar: 注册商
            purchase_date: 购买日期
            
        Returns:
            插入记录的ID
            
        Raises:
            sqlite3.IntegrityError: 如果域名已存在
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO domains (domain_name, registrar, purchase_date)
                VALUES (?, ?, ?)
            ''', (domain_name, registrar, purchase_date))
            
            domain_id = cursor.lastrowid
            conn.commit()
            
            logger.info(f"添加域名到数据库: {domain_name} (ID: {domain_id})")
            return domain_id
    
    def get_pending_domains(self) -> List[Dict]:
        """
        获取待同步到CloudFlare的域名
        
        Returns:
            待同步域名列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM domains 
                WHERE cloudflare_added = FALSE AND sync_status != 'failed'
                ORDER BY created_at ASC
            ''')
            
            domains = [dict(row) for row in cursor.fetchall()]
            logger.debug(f"获取到 {len(domains)} 个待同步域名")
            return domains
    
    def update_sync_status(self, domain_id: int, status: str, zone_id: Optional[str] = None, error: Optional[str] = None) -> None:
        """
        更新域名同步状态
        
        Args:
            domain_id: 域名ID
            status: 同步状态 (pending, synced, failed)
            zone_id: CloudFlare区域ID
            error: 错误信息
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cloudflare_added = status == 'synced'
            current_time = datetime.now().isoformat()
            
            cursor.execute('''
                UPDATE domains 
                SET sync_status = ?, 
                    cloudflare_added = ?,
                    cloudflare_zone_id = ?,
                    error_message = ?,
                    last_sync_attempt = ?,
                    updated_at = ?
                WHERE id = ?
            ''', (status, cloudflare_added, zone_id, error, current_time, current_time, domain_id))
            
            conn.commit()
            logger.info(f"更新域名同步状态: ID {domain_id} -> {status}")
    
    def get_domain_by_name(self, domain_name: str) -> Optional[Dict]:
        """
        根据域名获取记录
        
        Args:
            domain_name: 域名
            
        Returns:
            域名记录或None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM domains WHERE domain_name = ?', (domain_name,))
            row = cursor.fetchone()
            
            return dict(row) if row else None
    
    def list_all_domains(self, status_filter: Optional[str] = None) -> List[Dict]:
        """
        列出所有域名
        
        Args:
            status_filter: 状态过滤器
            
        Returns:
            域名列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if status_filter:
                cursor.execute('SELECT * FROM domains WHERE sync_status = ? ORDER BY created_at DESC', (status_filter,))
            else:
                cursor.execute('SELECT * FROM domains ORDER BY created_at DESC')
            
            domains = [dict(row) for row in cursor.fetchall()]
            logger.debug(f"列出 {len(domains)} 个域名记录")
            return domains
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取数据库统计信息
        
        Returns:
            统计信息字典
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 总域名数
            cursor.execute('SELECT COUNT(*) as total FROM domains')
            total = cursor.fetchone()['total']
            
            # 已同步数
            cursor.execute('SELECT COUNT(*) as synced FROM domains WHERE cloudflare_added = TRUE')
            synced = cursor.fetchone()['synced']
            
            # 待同步数
            cursor.execute('SELECT COUNT(*) as pending FROM domains WHERE sync_status = "pending"')
            pending = cursor.fetchone()['pending']
            
            # 失败数
            cursor.execute('SELECT COUNT(*) as failed FROM domains WHERE sync_status = "failed"')
            failed = cursor.fetchone()['failed']
            
            return {
                'total': total,
                'synced': synced,
                'pending': pending,
                'failed': failed
            }
    
    def domain_exists(self, domain_name: str) -> bool:
        """
        检查域名是否已存在
        
        Args:
            domain_name: 域名
            
        Returns:
            True如果存在，False如果不存在
        """
        return self.get_domain_by_name(domain_name) is not None
    
    def update_nameserver_status(self, domain_id: int, ns_updated: bool, original_nameservers: Optional[List[str]] = None) -> None:
        """
        更新域名的NS记录状态
        
        Args:
            domain_id: 域名ID
            ns_updated: NS是否已更新
            original_nameservers: 原始NS记录列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            current_time = datetime.now().isoformat()
            original_ns_json = json.dumps(original_nameservers) if original_nameservers else None
            
            cursor.execute('''
                UPDATE domains 
                SET ns_updated = ?, 
                    ns_update_date = ?,
                    original_nameservers = ?,
                    updated_at = ?
                WHERE id = ?
            ''', (ns_updated, current_time, original_ns_json, current_time, domain_id))
            
            conn.commit()
            logger.info(f"更新域名NS状态: ID {domain_id} -> NS已更新: {ns_updated}")
    
    def get_domains_with_ns_status(self, ns_updated: bool) -> List[Dict]:
        """
        获取指定NS状态的域名
        
        Args:
            ns_updated: NS更新状态
            
        Returns:
            域名列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM domains 
                WHERE ns_updated = ?
                ORDER BY created_at DESC
            ''', (ns_updated,))
            
            domains = [dict(row) for row in cursor.fetchall()]
            logger.debug(f"获取到 {len(domains)} 个NS状态为 {ns_updated} 的域名")
            return domains
    
    def get_domain_original_nameservers(self, domain_id: int) -> Optional[List[str]]:
        """
        获取域名的原始NS记录
        
        Args:
            domain_id: 域名ID
            
        Returns:
            原始NS记录列表或None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT original_nameservers FROM domains WHERE id = ?', (domain_id,))
            row = cursor.fetchone()
            
            if row and row['original_nameservers']:
                try:
                    return json.loads(row['original_nameservers'])
                except json.JSONDecodeError:
                    logger.warning(f"无法解析域名 {domain_id} 的原始NS记录")
                    return None
            return None
    
    def _migrate_database(self) -> None:
        """
        自动执行数据库迁移
        """
        try:
            # 使用现有的连接方法
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 检查表结构
                cursor.execute("PRAGMA table_info(domains)")
                columns = [column[1] for column in cursor.fetchall()]
                
                migration_needed = False
                
                # 检查并添加 ns_updated 列
                if 'ns_updated' not in columns:
                    logger.info("数据库迁移：添加 ns_updated 列...")
                    cursor.execute("ALTER TABLE domains ADD COLUMN ns_updated BOOLEAN DEFAULT FALSE")
                    migration_needed = True
                
                # 检查并添加 ns_update_date 列
                if 'ns_update_date' not in columns:
                    logger.info("数据库迁移：添加 ns_update_date 列...")
                    cursor.execute("ALTER TABLE domains ADD COLUMN ns_update_date TIMESTAMP")
                    migration_needed = True
                
                # 检查并添加 original_nameservers 列
                if 'original_nameservers' not in columns:
                    logger.info("数据库迁移：添加 original_nameservers 列...")
                    cursor.execute("ALTER TABLE domains ADD COLUMN original_nameservers TEXT")
                    migration_needed = True
                
                # 检查并添加刷新功能相关字段
                if 'expire_date' not in columns:
                    logger.info("数据库迁移：添加 expire_date 列...")
                    cursor.execute("ALTER TABLE domains ADD COLUMN expire_date DATE")
                    migration_needed = True
                
                if 'domain_status' not in columns:
                    logger.info("数据库迁移：添加 domain_status 列...")
                    cursor.execute("ALTER TABLE domains ADD COLUMN domain_status TEXT")
                    migration_needed = True
                
                if 'locked' not in columns:
                    logger.info("数据库迁移：添加 locked 列...")
                    cursor.execute("ALTER TABLE domains ADD COLUMN locked BOOLEAN DEFAULT FALSE")
                    migration_needed = True
                
                if 'privacy' not in columns:
                    logger.info("数据库迁移：添加 privacy 列...")
                    cursor.execute("ALTER TABLE domains ADD COLUMN privacy BOOLEAN DEFAULT FALSE")
                    migration_needed = True
                
                if 'cf_zone_status' not in columns:
                    logger.info("数据库迁移：添加 cf_zone_status 列...")
                    cursor.execute("ALTER TABLE domains ADD COLUMN cf_zone_status TEXT")
                    migration_needed = True
                
                if 'cf_ssl_mode' not in columns:
                    logger.info("数据库迁移：添加 cf_ssl_mode 列...")
                    cursor.execute("ALTER TABLE domains ADD COLUMN cf_ssl_mode TEXT")
                    migration_needed = True
                
                if 'dns_records_count' not in columns:
                    logger.info("数据库迁移：添加 dns_records_count 列...")
                    cursor.execute("ALTER TABLE domains ADD COLUMN dns_records_count INTEGER DEFAULT 0")
                    migration_needed = True
                
                if 'last_refresh_time' not in columns:
                    logger.info("数据库迁移：添加 last_refresh_time 列...")
                    cursor.execute("ALTER TABLE domains ADD COLUMN last_refresh_time TIMESTAMP")
                    migration_needed = True
                
                if 'refresh_status' not in columns:
                    logger.info("数据库迁移：添加 refresh_status 列...")
                    cursor.execute("ALTER TABLE domains ADD COLUMN refresh_status TEXT DEFAULT 'never'")
                    migration_needed = True
                
                # 创建新的索引
                if migration_needed:
                    try:
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ns_updated ON domains(ns_updated)")
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_refresh_status ON domains(refresh_status)")
                        cursor.execute("CREATE INDEX IF NOT EXISTS idx_last_refresh_time ON domains(last_refresh_time)")
                        logger.info("数据库迁移：创建索引...")
                    except sqlite3.Error as e:
                        logger.debug(f"创建索引失败（可能已存在）: {e}")
                
                # 提交更改
                conn.commit()
                
                if migration_needed:
                    logger.info("数据库迁移完成")
                else:
                    logger.debug("数据库已是最新版本，无需迁移")
                    
        except Exception as e:
            logger.error(f"数据库迁移失败: {e}")
            raise
    
    def update_domain_refresh_info(self, domain_id: int, **refresh_data) -> None:
        """
        更新域名的刷新信息
        
        Args:
            domain_id: 域名ID
            **refresh_data: 刷新数据字典，可包含以下键值：
                - expire_date: 过期日期
                - domain_status: 域名状态
                - locked: 是否锁定
                - privacy: 是否启用隐私保护
                - cf_zone_status: CloudFlare Zone状态
                - cf_ssl_mode: CloudFlare SSL模式
                - dns_records_count: DNS记录数量
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            current_time = datetime.now().isoformat()
            
            # 构建动态更新SQL
            set_clauses = []
            values = []
            
            for key, value in refresh_data.items():
                if key in ['expire_date', 'domain_status', 'locked', 'privacy', 
                          'cf_zone_status', 'cf_ssl_mode', 'dns_records_count']:
                    set_clauses.append(f"{key} = ?")
                    values.append(value)
            
            # 总是更新刷新时间和更新时间
            set_clauses.extend(['last_refresh_time = ?', 'updated_at = ?'])
            values.extend([current_time, current_time, domain_id])
            
            if set_clauses:
                sql = f"UPDATE domains SET {', '.join(set_clauses)} WHERE id = ?"
                cursor.execute(sql, values)
                conn.commit()
                logger.debug(f"更新域名刷新信息: ID {domain_id}")
    
    def get_domains_for_refresh(self) -> List[Dict]:
        """
        获取所有域名用于刷新操作
        
        Returns:
            域名列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM domains ORDER BY created_at ASC')
            domains = [dict(row) for row in cursor.fetchall()]
            logger.debug(f"获取到 {len(domains)} 个域名用于刷新")
            return domains
    
    def update_refresh_status(self, domain_id: int, status: str, error: Optional[str] = None) -> None:
        """
        更新域名刷新状态
        
        Args:
            domain_id: 域名ID
            status: 刷新状态 ('success', 'failed', 'skipped')
            error: 错误信息（可选）
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            current_time = datetime.now().isoformat()
            
            cursor.execute('''
                UPDATE domains 
                SET refresh_status = ?,
                    error_message = ?,
                    last_refresh_time = ?,
                    updated_at = ?
                WHERE id = ?
            ''', (status, error, current_time, current_time, domain_id))
            
            conn.commit()
            logger.debug(f"更新域名刷新状态: ID {domain_id} -> {status}")
    
    def get_refresh_stats(self) -> Dict[str, int]:
        """
        获取刷新相关统计信息
        
        Returns:
            刷新统计信息字典
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 总域名数
            cursor.execute('SELECT COUNT(*) as total FROM domains')
            total = cursor.fetchone()['total']
            
            # 已刷新数
            cursor.execute('SELECT COUNT(*) as refreshed FROM domains WHERE refresh_status = "success"')
            refreshed = cursor.fetchone()['refreshed']
            
            # 从未刷新数
            cursor.execute('SELECT COUNT(*) as never_refreshed FROM domains WHERE refresh_status = "never"')
            never_refreshed = cursor.fetchone()['never_refreshed']
            
            # 刷新失败数
            cursor.execute('SELECT COUNT(*) as refresh_failed FROM domains WHERE refresh_status = "failed"')
            refresh_failed = cursor.fetchone()['refresh_failed']
            
            return {
                'total': total,
                'refreshed': refreshed,
                'never_refreshed': never_refreshed,
                'refresh_failed': refresh_failed
            } 