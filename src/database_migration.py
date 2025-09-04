"""
数据库迁移脚本

用于更新现有数据库结构，添加新的NS相关字段
"""

import sqlite3
import os
from loguru import logger


def migrate_database(db_path: str) -> bool:
    """
    迁移数据库，添加新的NS相关字段
    
    Args:
        db_path: 数据库路径
        
    Returns:
        迁移是否成功
    """
    try:
        # 检查数据库是否存在
        if not os.path.exists(db_path):
            logger.info(f"数据库不存在，无需迁移: {db_path}")
            return True
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查是否需要迁移
        cursor.execute("PRAGMA table_info(domains)")
        columns = [column[1] for column in cursor.fetchall()]
        
        migration_needed = False
        
        # 检查并添加 ns_updated 列
        if 'ns_updated' not in columns:
            logger.info("添加 ns_updated 列...")
            cursor.execute("ALTER TABLE domains ADD COLUMN ns_updated BOOLEAN DEFAULT FALSE")
            migration_needed = True
        
        # 检查并添加 ns_update_date 列
        if 'ns_update_date' not in columns:
            logger.info("添加 ns_update_date 列...")
            cursor.execute("ALTER TABLE domains ADD COLUMN ns_update_date TIMESTAMP")
            migration_needed = True
        
        # 检查并添加 original_nameservers 列
        if 'original_nameservers' not in columns:
            logger.info("添加 original_nameservers 列...")
            cursor.execute("ALTER TABLE domains ADD COLUMN original_nameservers TEXT")
            migration_needed = True
        
        # 创建新的索引
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ns_updated ON domains(ns_updated)")
            if migration_needed:
                logger.info("创建 ns_updated 索引...")
        except sqlite3.Error as e:
            logger.debug(f"创建索引失败（可能已存在）: {e}")
        
        # 提交更改
        conn.commit()
        
        if migration_needed:
            logger.info("数据库迁移完成")
        else:
            logger.info("数据库已是最新版本，无需迁移")
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        logger.error(f"数据库迁移失败: {e}")
        return False
    except Exception as e:
        logger.error(f"迁移过程中发生错误: {e}")
        return False


def check_migration_needed(db_path: str) -> bool:
    """
    检查数据库是否需要迁移
    
    Args:
        db_path: 数据库路径
        
    Returns:
        是否需要迁移
    """
    try:
        if not os.path.exists(db_path):
            return False
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查表结构
        cursor.execute("PRAGMA table_info(domains)")
        columns = [column[1] for column in cursor.fetchall()]
        
        conn.close()
        
        # 检查是否缺少NS相关字段
        required_columns = ['ns_updated', 'ns_update_date', 'original_nameservers']
        missing_columns = [col for col in required_columns if col not in columns]
        
        return len(missing_columns) > 0
        
    except Exception as e:
        logger.error(f"检查迁移状态失败: {e}")
        return False


if __name__ == "__main__":
    # 用于测试的主函数
    import sys
    
    if len(sys.argv) != 2:
        print("使用方法: python database_migration.py <数据库路径>")
        sys.exit(1)
    
    db_path = sys.argv[1]
    
    if check_migration_needed(db_path):
        print(f"数据库需要迁移: {db_path}")
        if migrate_database(db_path):
            print("迁移成功")
        else:
            print("迁移失败")
            sys.exit(1)
    else:
        print("数据库已是最新版本") 