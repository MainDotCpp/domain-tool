"""
Click命令行界面

提供用户友好的命令行接口
"""

import sys
import click
from pathlib import Path
from typing import Optional
from loguru import logger

from .config import Config
from .domain_manager import DomainManager, DomainManagerError
from .utils import setup_logging
from .interactive_menu import InteractiveMenu


@click.group()
@click.option('--config', type=click.Path(), help='配置文件路径')
@click.option('--verbose', '-v', is_flag=True, help='详细输出')
@click.option('--log-level', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']), help='日志级别')
@click.pass_context
def cli(ctx, config, verbose, log_level):
    """域名管理工具 - 自动同步域名到CloudFlare"""
    # 确保context对象存在
    ctx.ensure_object(dict)
    
    # 加载配置
    try:
        app_config = Config(config_file=config)
        
        # 命令行参数覆盖配置文件设置
        if verbose:
            app_config.verbose = True
            if not log_level:
                app_config.log_level = 'DEBUG'
        
        if log_level:
            app_config.log_level = log_level
        
        # 设置日志
        setup_logging(app_config)
        
        # 存储配置到context
        ctx.obj['config'] = app_config
        
        logger.debug("命令行界面初始化完成")
        
    except Exception as e:
        click.echo(f"❌ 初始化失败: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--provider', default='godaddy', type=click.Choice(['godaddy']), help='域名提供商')
@click.pass_context
def import_domains(ctx, provider):
    """从域名提供商导入域名"""
    try:
        config = ctx.obj['config']
        manager = DomainManager(config)
        
        click.echo(f"🔄 正在从 {provider} 导入域名...")
        
        imported_count = manager.import_from_provider(provider)
        
        if imported_count > 0:
            click.echo(f"✅ 成功导入 {imported_count} 个域名")
        else:
            click.echo("ℹ️  没有新的域名需要导入")
            
    except DomainManagerError as e:
        click.echo(f"❌ 导入失败: {str(e)}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ 发生未知错误: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--dry-run', is_flag=True, help='仅预览，不执行实际操作')
@click.option('--force', is_flag=True, help='强制重试失败的域名')
@click.option('--update-ns/--no-update-ns', default=None, help='是否更新名称服务器记录')
@click.option('--confirm-ns/--no-confirm-ns', default=None, help='是否确认NS更新')
@click.option('--threads', '-t', type=int, help='最大并发线程数')
@click.option('--output-format', type=click.Choice(['summary', 'detailed']), default='summary', help='输出格式')
@click.pass_context
def sync(ctx, dry_run, force, update_ns, confirm_ns, threads, output_format):
    """同步域名到CloudFlare（支持多线程）"""
    try:
        config = ctx.obj['config']
        
        # 根据命令行选项覆盖配置
        if update_ns is not None:
            config.auto_update_nameservers = update_ns
        if confirm_ns is not None:
            config.confirm_ns_update = confirm_ns
        if threads is not None:
            config.max_concurrent_threads = threads
        
        manager = DomainManager(config)
        
        mode_text = "预览模式" if dry_run else "执行模式"
        force_text = "（包括失败重试）" if force else ""
        
        click.echo(f"🔄 开始同步域名到CloudFlare - {mode_text} {force_text}")
        click.echo(f"🧵 并发线程数: {config.max_concurrent_threads}")
        
        # 显示NS更新配置
        if config.auto_update_nameservers:
            ns_mode = "自动更新" if not config.confirm_ns_update else "确认后更新"
            click.echo(f"📋 名称服务器更新: {ns_mode}")
        else:
            click.echo("📋 名称服务器更新: 已禁用")
        
        stats = manager.sync_to_cloudflare(dry_run=dry_run, force_retry=force)
        
        # 显示结果
        if output_format == 'detailed':
            # 详细格式输出：domain|add_cloudflare|update_ns|create_dns|set_ssl
            click.echo("\n📋 详细结果:")
            domain_results = stats.get('domain_results', [])
            for result in domain_results:
                domain_name = result['domain_name']
                steps = result['steps']
                add_cf = 1 if steps['add_to_cloudflare'] else 0
                update_ns = 1 if steps['update_nameservers'] else 0
                create_dns = 1 if steps['create_dns_records'] else 0
                set_ssl = 1 if steps['set_ssl_mode'] else 0
                click.echo(f"{domain_name}|{add_cf}|{update_ns}|{create_dns}|{set_ssl}")
        else:
            # 摘要格式输出
            click.echo("\n📊 同步结果:")
            click.echo(f"  总计: {stats['total']} 个域名")
            click.echo(f"  ✅ 成功: {stats['success']} 个")
            if stats['failed'] > 0:
                click.echo(f"  ❌ 失败: {stats['failed']} 个")
            if stats.get('skipped', 0) > 0:
                click.echo(f"  ⏭️  跳过: {stats['skipped']} 个")
        
        if not dry_run and stats['success'] > 0:
            click.echo("\n💡 提示: 请在域名注册商处更新名称服务器为CloudFlare提供的NS记录")
            
    except DomainManagerError as e:
        click.echo(f"❌ 同步失败: {str(e)}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ 发生未知错误: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('domain')
@click.option('--registrar', default='manual', help='注册商名称')
@click.pass_context
def add(ctx, domain, registrar):
    """手动添加域名"""
    try:
        config = ctx.obj['config']
        manager = DomainManager(config)
        
        click.echo(f"🔄 正在添加域名: {domain}")
        
        success = manager.add_manual_domain(domain, registrar)
        
        if success:
            click.echo(f"✅ 域名添加成功: {domain}")
        else:
            click.echo(f"❌ 域名添加失败: {domain}（可能已存在或格式无效）", err=True)
            sys.exit(1)
            
    except Exception as e:
        click.echo(f"❌ 添加域名失败: {str(e)}", err=True)
        sys.exit(1)


@cli.command('list')
@click.option('--status', type=click.Choice(['pending', 'synced', 'failed']), help='按状态过滤')
@click.option('--format', 'output_format', type=click.Choice(['table', 'simple']), default='table', help='输出格式')
@click.pass_context
def list_domains(ctx, status, output_format):
    """列出所有域名"""
    try:
        config = ctx.obj['config']
        manager = DomainManager(config)
        
        domains = manager.list_domains(status_filter=status)
        
        if not domains:
            status_text = f"（状态: {status}）" if status else ""
            click.echo(f"没有找到域名 {status_text}")
            return
        
        # 显示域名列表
        if output_format == 'table':
            _display_domains_table(domains)
        else:
            _display_domains_simple(domains)
            
    except Exception as e:
        click.echo(f"❌ 获取域名列表失败: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def stats(ctx):
    """显示统计信息"""
    try:
        config = ctx.obj['config']
        manager = DomainManager(config)
        
        click.echo("📊 域名管理工具统计信息\n")
        
        statistics = manager.get_statistics()
        
        # 数据库统计
        db_stats = statistics.get('database', {})
        click.echo("💾 数据库统计:")
        click.echo(f"  总域名数: {db_stats.get('total', 0)}")
        click.echo(f"  已同步: {db_stats.get('synced', 0)}")
        click.echo(f"  待同步: {db_stats.get('pending', 0)}")
        click.echo(f"  同步失败: {db_stats.get('failed', 0)}")
        
        # 显示NS统计（如果可用）
        if 'ns_updated' in db_stats and db_stats['ns_updated'] != 'N/A':
            click.echo(f"  NS已更新: {db_stats.get('ns_updated', 0)}")
            click.echo(f"  NS待更新: {db_stats.get('ns_pending', 0)}")
        else:
            click.echo("  NS统计: 数据库需要升级")
        
        # 显示刷新统计
        try:
            refresh_stats = manager.db.get_refresh_stats()
            click.echo("\n🔄 刷新统计:")
            click.echo(f"  已刷新: {refresh_stats.get('refreshed', 0)}")
            click.echo(f"  从未刷新: {refresh_stats.get('never_refreshed', 0)}")
            click.echo(f"  刷新失败: {refresh_stats.get('refresh_failed', 0)}")
        except Exception as e:
            click.echo("\n🔄 刷新统计: 数据库需要升级")
        
        # CloudFlare统计
        cf_stats = statistics.get('cloudflare', {})
        if cf_stats:
            click.echo("\n☁️  CloudFlare统计:")
            if 'error' in cf_stats:
                click.echo(f"  ❌ 获取失败: {cf_stats['error']}")
            else:
                click.echo(f"  总Zone数: {cf_stats.get('total_zones', 0)}")
                click.echo(f"  活跃Zone: {cf_stats.get('active_zones', 0)}")
                click.echo(f"  待激活Zone: {cf_stats.get('pending_zones', 0)}")
        
        # 配置状态
        config_valid = statistics.get('config_valid', False)
        config_status = "✅ 有效" if config_valid else "❌ 无效"
        click.echo(f"\n⚙️  配置状态: {config_status}")
        
    except Exception as e:
        click.echo(f"❌ 获取统计信息失败: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def config_setup(ctx):
    """交互式配置设置"""
    try:
        config = ctx.obj['config']
        
        click.echo("⚙️  开始交互式配置设置...\n")
        
        config.interactive_setup()
        
        # 重新加载配置
        config.load_config()
        
        # 验证配置
        errors = config.validate_config()
        if errors:
            click.echo("\n⚠️  配置验证失败:")
            for error in errors:
                click.echo(f"  - {error}")
        else:
            click.echo("\n✅ 配置设置完成且有效!")
            
    except Exception as e:
        click.echo(f"❌ 配置设置失败: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def validate_credentials(ctx):
    """验证API凭据"""
    try:
        config = ctx.obj['config']
        manager = DomainManager(config)
        
        click.echo("🔐 正在验证API凭据...\n")
        
        results = manager.validate_all_credentials()
        
        for service, valid in results.items():
            status = "✅ 有效" if valid else "❌ 无效"
            service_name = "GoDaddy" if service == "godaddy" else "CloudFlare"
            click.echo(f"{service_name}: {status}")
        
        all_valid = all(results.values())
        if all_valid:
            click.echo("\n🎉 所有凭据验证通过!")
        else:
            click.echo("\n⚠️  部分凭据验证失败，请检查配置")
            
    except Exception as e:
        click.echo(f"❌ 验证凭据失败: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('domain')
@click.option('--target-ip', help='目标IP地址（可选）')
@click.option('--ssl-mode', default='flexible', type=click.Choice(['off', 'flexible', 'full', 'strict']), help='SSL模式')
@click.option('--no-confirm', is_flag=True, help='跳过确认')
@click.pass_context
def migrate(ctx, domain, target_ip, ssl_mode, no_confirm):
    """一键完成域名迁移（添加到CloudFlare + 修改NS + 创建DNS记录 + 设置SSL）"""
    try:
        config = ctx.obj['config']
        
        # 跳过确认
        if no_confirm:
            config.confirm_ns_update = False
        
        manager = DomainManager(config)
        
        # 显示迁移计划
        click.echo(f"🚀 开始一键域名迁移: {domain}")
        click.echo(f"📋 迁移步骤:")
        click.echo(f"  1. 添加域名到CloudFlare")
        click.echo(f"  2. 更新名称服务器记录")
        click.echo(f"  3. 创建DNS记录" + (f" (IP: {target_ip})" if target_ip else " (CNAME)"))
        click.echo(f"  4. 设置SSL模式为: {ssl_mode}")
        
        if not no_confirm:
            if not click.confirm(f"\n是否继续迁移域名 {domain}?"):
                click.echo("迁移已取消")
                return
        
        # 执行迁移
        result = manager.migrate_domain_complete(domain, target_ip, ssl_mode)
        
        # 显示结果
        click.echo(f"\n📊 迁移结果:")
        click.echo(f"  域名: {result['domain']}")
        click.echo(f"  Zone ID: {result['zone_id']}")
        
        # 显示步骤结果
        steps = result['steps']
        click.echo(f"\n📝 步骤执行结果:")
        click.echo(f"  ✅ 添加到CloudFlare: {'成功' if steps['add_to_cloudflare'] else '失败'}")
        click.echo(f"  ✅ 更新名称服务器: {'成功' if steps['update_nameservers'] else '失败'}")
        click.echo(f"  ✅ 创建DNS记录: {'成功' if steps['create_dns_records'] else '失败'}")
        click.echo(f"  ✅ 设置SSL模式: {'成功' if steps['set_ssl_mode'] else '失败'}")
        
        # 显示创建的DNS记录
        if result['dns_records']:
            click.echo(f"\n📋 创建的DNS记录:")
            for record in result['dns_records']:
                click.echo(f"  {record['type']}: {record['name']} -> {record['content']}")
        
        # 显示错误
        if result['errors']:
            click.echo(f"\n❌ 错误信息:")
            for error in result['errors']:
                click.echo(f"  - {error}")
        
        # 最终状态
        if result['success']:
            click.echo(f"\n🎉 域名迁移完成! {domain}")
            click.echo(f"💡 提示: NS记录生效需要一些时间，请耐心等待")
        else:
            click.echo(f"\n⚠️ 域名迁移部分失败: {domain}")
            click.echo(f"请检查上述错误信息并手动完成")
            sys.exit(1)
            
    except DomainManagerError as e:
        click.echo(f"❌ 域名迁移失败: {str(e)}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ 发生未知错误: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('domain')
@click.pass_context
def migration_status(ctx, domain):
    """查看域名迁移状态"""
    try:
        config = ctx.obj['config']
        manager = DomainManager(config)
        
        status = manager.get_migration_status(domain)
        
        if 'error' in status:
            click.echo(f"❌ 获取状态失败: {status['error']}")
            sys.exit(1)
        
        click.echo(f"📊 域名迁移状态: {status['domain']}")
        click.echo(f"  在CloudFlare: {'✅ 是' if status['in_cloudflare'] else '❌ 否'}")
        click.echo(f"  Zone ID: {status['zone_id'] or 'N/A'}")
        click.echo(f"  NS已更新: {'✅ 是' if status['ns_updated'] else '❌ 否'}")
        click.echo(f"  同步状态: {status['sync_status']}")
        click.echo(f"  最后同步: {status['last_sync'] or 'N/A'}")
        
        if status.get('ssl_mode'):
            click.echo(f"  SSL模式: {status['ssl_mode']}")
        
        if status.get('dns_records_count'):
            click.echo(f"  DNS记录数: {status['dns_records_count']}")
        
        if status.get('zone_status'):
            click.echo(f"  Zone状态: {status['zone_status']}")
            
    except Exception as e:
        click.echo(f"❌ 获取状态失败: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('domain', required=False)
@click.option('--all', 'update_all', is_flag=True, help='更新所有域名的NS记录')
@click.option('--provider', default='godaddy', type=click.Choice(['godaddy']), help='域名提供商')
@click.option('--force', is_flag=True, help='强制更新，跳过确认')
@click.pass_context
def update_ns(ctx, domain, update_all, provider, force):
    """更新域名的名称服务器记录"""
    try:
        config = ctx.obj['config']
        
        # 如果指定了force选项，禁用确认
        if force:
            config.confirm_ns_update = False
        
        manager = DomainManager(config)
        
        if update_all:
            # 更新所有域名的NS记录
            click.echo("🔄 开始更新所有域名的NS记录...")
            
            # 获取所有已同步到CloudFlare但NS未更新的域名
            domains = manager.db.get_domains_with_ns_status(ns_updated=False)
            synced_domains = [d for d in domains if d['cloudflare_added'] and d['cloudflare_zone_id']]
            
            if not synced_domains:
                click.echo("没有需要更新NS记录的域名")
                return
            
            success_count = 0
            failed_count = 0
            
            for domain_record in synced_domains:
                domain_name = domain_record['domain_name']
                zone_id = domain_record['cloudflare_zone_id']
                
                try:
                    # 获取CloudFlare名称服务器
                    cf_nameservers = manager.cf_manager.get_nameservers(zone_id)
                    if not cf_nameservers:
                        click.echo(f"❌ 无法获取 {domain_name} 的CloudFlare名称服务器")
                        failed_count += 1
                        continue
                    
                    # 更新NS记录
                    click.echo(f"🔄 更新 {domain_name} 的NS记录...")
                    success = manager.update_domain_nameservers(domain_name, provider, cf_nameservers)
                    
                    if success:
                        click.echo(f"✅ {domain_name} NS记录更新成功")
                        success_count += 1
                    else:
                        click.echo(f"❌ {domain_name} NS记录更新失败")
                        failed_count += 1
                        
                except Exception as e:
                    click.echo(f"❌ 更新 {domain_name} NS记录时发生错误: {str(e)}")
                    failed_count += 1
            
            click.echo(f"\n📊 NS记录更新完成: 成功 {success_count} 个，失败 {failed_count} 个")
            
        elif domain:
            # 更新指定域名的NS记录
            click.echo(f"🔄 更新域名 {domain} 的NS记录...")
            
            # 获取域名信息
            domain_record = manager.db.get_domain_by_name(domain)
            if not domain_record:
                click.echo(f"❌ 域名不存在: {domain}")
                sys.exit(1)
            
            if not domain_record['cloudflare_added'] or not domain_record['cloudflare_zone_id']:
                click.echo(f"❌ 域名 {domain} 未同步到CloudFlare")
                sys.exit(1)
            
            # 获取CloudFlare名称服务器
            cf_nameservers = manager.cf_manager.get_nameservers(domain_record['cloudflare_zone_id'])
            if not cf_nameservers:
                click.echo(f"❌ 无法获取 {domain} 的CloudFlare名称服务器")
                sys.exit(1)
            
            # 更新NS记录
            success = manager.update_domain_nameservers(domain, provider, cf_nameservers)
            
            if success:
                click.echo(f"✅ 域名 {domain} NS记录更新成功")
            else:
                click.echo(f"❌ 域名 {domain} NS记录更新失败")
                sys.exit(1)
        else:
            click.echo("❌ 请指定域名或使用 --all 选项更新所有域名")
            sys.exit(1)
            
    except Exception as e:
        click.echo(f"❌ 更新NS记录失败: {str(e)}", err=True)
        sys.exit(1)


def _display_domains_table(domains):
    """以表格形式显示域名列表"""
    if not domains:
        return
    
    # 表头
    headers = ["ID", "域名", "注册商", "状态", "CloudFlare Zone ID", "NS已更新", "最后同步"]
    
    # 计算列宽
    col_widths = [len(h) for h in headers]
    
    # 准备数据并计算最大宽度
    rows = []
    for domain in domains:
        ns_updated = "✅" if domain.get('ns_updated') else "❌"
        row = [
            str(domain.get('id', '')),
            domain.get('domain_name', ''),
            domain.get('registrar', ''),
            domain.get('sync_status', ''),
            domain.get('cloudflare_zone_id', '') or '-',
            ns_updated,
            domain.get('last_sync_attempt', '') or '-'
        ]
        rows.append(row)
        
        # 更新列宽
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))
    
    # 打印表格
    separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    
    click.echo(separator)
    
    # 打印表头
    header_row = "|" + "|".join(f" {headers[i]:<{col_widths[i]}} " for i in range(len(headers))) + "|"
    click.echo(header_row)
    click.echo(separator)
    
    # 打印数据行
    for row in rows:
        data_row = "|" + "|".join(f" {row[i]:<{col_widths[i]}} " for i in range(len(row))) + "|"
        click.echo(data_row)
    
    click.echo(separator)
    click.echo(f"\n总计: {len(domains)} 个域名")


@cli.command()
@click.option('--mode', type=click.Choice(['basic', 'full']), default='basic', help='刷新模式')
@click.option('--dry-run', is_flag=True, help='仅预览，不执行实际操作')
@click.option('--threads', '-t', type=int, help='最大并发线程数')
@click.pass_context
def refresh(ctx, mode, dry_run, threads):
    """批量刷新域名信息"""
    try:
        config = ctx.obj['config']
        
        # 根据命令行选项覆盖配置
        if threads is not None:
            config.max_concurrent_threads = threads
        
        manager = DomainManager(config)
        
        mode_text = "预览模式" if dry_run else "执行模式"
        click.echo(f"🔄 开始刷新域名信息 - {mode_text}")
        click.echo(f"🔧 刷新模式: {mode} ({'基础信息' if mode == 'basic' else '完整信息'})")
        click.echo(f"🧵 并发线程数: {config.max_concurrent_threads}")
        
        stats = manager.refresh_domains_info(mode=mode, dry_run=dry_run)
        
        # 显示结果统计
        click.echo("\n📊 刷新结果:")
        click.echo(f"  总计: {stats['total']} 个域名")
        click.echo(f"  ✅ 成功: {stats['success']} 个")
        if stats['failed'] > 0:
            click.echo(f"  ❌ 失败: {stats['failed']} 个")
        if stats.get('skipped', 0) > 0:
            click.echo(f"  ⏭️  跳过: {stats['skipped']} 个")
        
        if not dry_run and stats['success'] > 0:
            click.echo("\n💡 提示: 域名信息已刷新，可以使用 'list' 命令查看最新状态")
            
    except DomainManagerError as e:
        click.echo(f"❌ 刷新失败: {str(e)}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ 发生未知错误: {str(e)}", err=True)
        sys.exit(1)


def _display_domains_simple(domains):
    """以简单列表形式显示域名"""
    for domain in domains:
        status = domain.get('sync_status', 'unknown')
        status_icon = {
            'pending': '⏳',
            'synced': '✅',
            'failed': '❌'
        }.get(status, '❓')
        
        click.echo(f"{status_icon} {domain.get('domain_name', '')} ({domain.get('registrar', '')})")
    
    click.echo(f"\n总计: {len(domains)} 个域名")


@cli.command()
@click.argument('domain')
@click.option('--dry-run', is_flag=True, help='仅预览，不执行实际删除')
@click.option('--force', is_flag=True, help='强制删除，跳过确认')
@click.option('--types', help='指定删除的记录类型，用逗号分隔（如: A,CNAME）')
@click.pass_context
def delete_dns(ctx, domain, dry_run, force, types):
    """删除指定域名的所有DNS解析记录"""
    try:
        config = ctx.obj['config']
        manager = DomainManager(config)
        
        # 解析记录类型
        record_types = None
        if types:
            record_types = [t.strip().upper() for t in types.split(',')]
            # 验证记录类型
            valid_types = {'A', 'AAAA', 'CNAME', 'MX', 'TXT', 'SRV', 'NS'}
            invalid_types = [t for t in record_types if t not in valid_types]
            if invalid_types:
                click.echo(f"❌ 无效的记录类型: {', '.join(invalid_types)}")
                sys.exit(1)
        
        # 执行预览以获取要删除的记录信息
        click.echo(f"🔍 检查域名 {domain} 的DNS记录...")
        try:
            preview_result = manager.delete_domain_dns_records(domain, record_types, dry_run=True)
        except DomainManagerError as e:
            click.echo(f"❌ 检查失败: {str(e)}")
            sys.exit(1)
        
        # 显示域名信息
        click.echo(f"\n📋 域名信息:")
        click.echo(f"  域名: {preview_result['domain']}")
        click.echo(f"  Zone ID: {preview_result['zone_id']}")
        click.echo(f"  当前DNS记录总数: {preview_result['total_records']}")
        click.echo(f"  将要删除的记录数: {preview_result['will_delete']}")
        
        # 显示要删除的记录详情
        if preview_result['records_to_delete']:
            click.echo(f"\n📝 将要删除的DNS记录:")
            for record in preview_result['records_to_delete']:
                record_display = f"  {record['type']}: {record['name']} -> {record['content']}"
                if record.get('proxied'):
                    record_display += " (已代理)"
                click.echo(record_display)
        else:
            click.echo(f"\n✅ 没有符合条件的DNS记录需要删除")
            return
        
        # 显示受保护的记录
        protected_records = [r for r in preview_result['current_records'] 
                           if r['type'] in {'NS', 'MX', 'TXT', 'SRV'}]
        if protected_records:
            click.echo(f"\n🛡️  受保护的记录（将保留）:")
            for record in protected_records:
                click.echo(f"  {record['type']}: {record['name']} -> {record['content']}")
        
        if dry_run:
            click.echo(f"\n📋 预览模式完成，没有执行实际删除操作")
            return
        
        # 确认删除操作
        if not force:
            click.echo(f"\n⚠️  警告: 此操作将删除域名 {domain} 的 {preview_result['will_delete']} 条DNS记录!")
            click.echo(f"⚠️  删除后域名可能无法正常解析，请确保您了解后果!")
            
            # 要求用户输入完整域名进行确认
            confirmation = click.prompt(f"\n请输入完整域名 '{domain}' 以确认删除", type=str)
            
            if confirmation != domain:
                click.echo(f"❌ 确认失败，输入的域名不匹配，操作已取消")
                return
            
            if not click.confirm(f"确定要删除域名 {domain} 的DNS记录吗？"):
                click.echo("删除操作已取消")
                return
        
        # 执行删除
        click.echo(f"\n🗑️  正在删除域名 {domain} 的DNS记录...")
        
        try:
            result = manager.delete_domain_dns_records(domain, record_types, dry_run=False)
        except DomainManagerError as e:
            click.echo(f"❌ 删除失败: {str(e)}")
            sys.exit(1)
        
        # 显示删除结果
        click.echo(f"\n📊 删除结果:")
        click.echo(f"  总计找到: {result.get('total_found', 0)} 条记录")
        click.echo(f"  计划删除: {result.get('to_delete', 0)} 条记录")
        click.echo(f"  ✅ 成功删除: {result.get('deleted', 0)} 条记录")
        
        if result.get('failed', 0) > 0:
            click.echo(f"  ❌ 删除失败: {result.get('failed', 0)} 条记录")
        
        if result.get('skipped', 0) > 0:
            click.echo(f"  ⏭️  跳过保护: {result.get('skipped', 0)} 条记录")
        
        if 'error' in result:
            click.echo(f"  ⚠️  错误信息: {result['error']}")
        
        # 最终状态
        if result.get('deleted', 0) > 0:
            click.echo(f"\n🎉 DNS记录删除完成! 域名: {domain}")
            click.echo(f"💡 提示: DNS记录删除后，域名解析可能需要一些时间完全清除")
        else:
            click.echo(f"\n⚠️  没有DNS记录被删除")
            
    except Exception as e:
        click.echo(f"❌ 删除DNS记录失败: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('domains', nargs=-1, required=False)
@click.option('--from-file', type=click.Path(exists=True), help='从文件读取域名列表')
@click.option('--dry-run', is_flag=True, help='仅预览，不执行实际删除')
@click.option('--force', is_flag=True, help='强制删除，跳过确认')
@click.option('--types', help='指定删除的记录类型，用逗号分隔（如: A,CNAME）')
@click.option('--threads', '-t', type=int, help='最大并发线程数')
@click.option('--batch-confirm', is_flag=True, help='批量确认模式，一次确认所有域名')
@click.pass_context
def batch_delete_dns(ctx, domains, from_file, dry_run, force, types, threads, batch_confirm):
    """批量删除多个域名的所有DNS解析记录"""
    try:
        config = ctx.obj['config']
        manager = DomainManager(config)
        
        # 构建域名列表
        domain_list = list(domains) if domains else []
        
        # 从文件读取域名
        if from_file:
            try:
                with open(from_file, 'r', encoding='utf-8') as f:
                    file_domains = [line.strip() for line in f.readlines() if line.strip() and not line.startswith('#')]
                    domain_list.extend(file_domains)
                    click.echo(f"📁 从文件读取了 {len(file_domains)} 个域名")
            except Exception as e:
                click.echo(f"❌ 读取文件失败: {str(e)}")
                sys.exit(1)
        
        # 检查域名列表
        if not domain_list:
            click.echo("❌ 请提供至少一个域名，或使用 --from-file 选项")
            click.echo("\n使用示例:")
            click.echo("  多个域名: batch-delete-dns domain1.com domain2.com domain3.com")
            click.echo("  从文件读取: batch-delete-dns --from-file domains.txt")
            sys.exit(1)
        
        # 去重并验证域名格式
        domain_list = list(set(domain_list))
        click.echo(f"🔍 准备批量删除 {len(domain_list)} 个域名的DNS记录")
        
        # 根据命令行选项覆盖配置
        if threads is not None:
            config.max_concurrent_threads = threads
        
        # 解析记录类型
        record_types = None
        if types:
            record_types = [t.strip().upper() for t in types.split(',')]
            # 验证记录类型
            valid_types = {'A', 'AAAA', 'CNAME', 'MX', 'TXT', 'SRV', 'NS'}
            invalid_types = [t for t in record_types if t not in valid_types]
            if invalid_types:
                click.echo(f"❌ 无效的记录类型: {', '.join(invalid_types)}")
                sys.exit(1)
            click.echo(f"🎯 删除记录类型: {', '.join(record_types)}")
        else:
            click.echo(f"🎯 删除记录类型: A, AAAA, CNAME (默认安全类型)")
        
        click.echo(f"🧵 并发线程数: {config.max_concurrent_threads}")
        
        # 批量确认
        if not force and not batch_confirm:
            click.echo(f"\n⚠️  警告: 此操作将批量删除 {len(domain_list)} 个域名的DNS记录!")
            click.echo(f"⚠️  删除后域名可能无法正常解析，请确保您了解后果!")
            
            click.echo(f"\n📋 域名列表:")
            for i, domain in enumerate(domain_list[:10], 1):
                click.echo(f"  {i}. {domain}")
            if len(domain_list) > 10:
                click.echo(f"  ... 还有 {len(domain_list) - 10} 个域名")
            
            if not click.confirm(f"\n确定要批量删除这 {len(domain_list)} 个域名的DNS记录吗？"):
                click.echo("批量删除操作已取消")
                return
        
        # 执行批量删除
        mode_text = "预览模式" if dry_run else "执行模式"
        click.echo(f"\n🗑️  开始批量删除DNS记录 - {mode_text}")
        
        try:
            result = manager.batch_delete_dns_records(domain_list, record_types, dry_run)
        except DomainManagerError as e:
            click.echo(f"❌ 批量删除失败: {str(e)}")
            sys.exit(1)
        
        # 显示批量删除结果
        click.echo(f"\n📊 批量删除结果:")
        click.echo(f"  总计: {result['total']} 个域名")
        click.echo(f"  ✅ 成功: {result['success']} 个")
        click.echo(f"  ❌ 失败: {result['failed']} 个")
        click.echo(f"  ⏭️  跳过: {result['skipped']} 个")
        click.echo(f"  🗑️  删除记录总数: {result['total_records_deleted']} 条")
        
        # 显示失败的域名
        if result['failed'] > 0:
            failed_domains = [r['domain_name'] for r in result['domain_results'] if r['status'] == 'failed']
            click.echo(f"\n❌ 删除失败的域名:")
            for domain in failed_domains[:5]:
                error_info = next((r['error'] for r in result['domain_results'] 
                                 if r['domain_name'] == domain), '未知错误')
                click.echo(f"  - {domain}: {error_info}")
            if len(failed_domains) > 5:
                click.echo(f"  ... 还有 {len(failed_domains) - 5} 个失败域名")
        
        # 最终状态
        if result['success'] > 0:
            click.echo(f"\n🎉 批量DNS记录删除完成! 成功处理 {result['success']} 个域名")
            if not dry_run:
                click.echo(f"💡 提示: DNS记录删除后，域名解析可能需要一些时间完全清除")
        else:
            click.echo(f"\n⚠️  没有DNS记录被删除")
            
    except Exception as e:
        click.echo(f"❌ 批量删除DNS记录失败: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def menu(ctx):
    """启动交互式菜单界面"""
    try:
        config = ctx.obj['config']
        interactive_menu = InteractiveMenu(config)
        interactive_menu.show_main_menu()
        
    except Exception as e:
        click.echo(f"❌ 启动交互式菜单失败: {str(e)}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli() 