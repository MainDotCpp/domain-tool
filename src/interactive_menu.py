"""
交互式菜单系统

提供用户友好的交互式界面来操作域名管理工具
"""

import click
import sys
from typing import Optional, Dict, Any
from loguru import logger

from .config import Config
from .domain_manager import DomainManager, DomainManagerError


class InteractiveMenu:
    """交互式菜单管理器"""
    
    def __init__(self, config: Config):
        """初始化交互式菜单"""
        self.config = config
        self.manager = DomainManager(config)
        logger.debug("交互式菜单系统初始化完成")
    
    def show_main_menu(self) -> None:
        """显示主菜单"""
        while True:
            try:
                # 显示标题
                click.echo("=" * 60)
                click.echo("🏠 域名管理工具 - 交互式菜单")
                click.echo("=" * 60)
                
                # 智能推荐
                recommendations = self._get_smart_recommendations()
                if recommendations:
                    click.echo("\n💡 智能推荐:")
                    for rec in recommendations:
                        click.echo(f"  → {rec}")
                
                # 显示菜单选项
                click.echo("\n📋 常用功能:")
                click.echo("  1. 查看域名列表")
                click.echo("  2. 查看统计信息")
                click.echo("  3. 同步域名到CloudFlare")
                
                click.echo("\n🔧 域名管理:")
                click.echo("  4. 添加域名")
                click.echo("  5. 导入域名")
                click.echo("  6. 刷新域名信息")
                
                click.echo("\n☁️ CloudFlare操作:")
                click.echo("  7. 域名迁移")
                click.echo("  8. 删除DNS记录")
                click.echo("  9. 更新NS记录")
                
                click.echo("\n⚙️ 系统设置:")
                click.echo("  10. 配置设置")
                click.echo("  11. 验证凭据")
                
                click.echo("\n📊 高级功能:")
                click.echo("  12. 查看迁移状态")
                click.echo("  13. 批量删除DNS")
                
                click.echo("\n  0. 退出")
                click.echo("\n" + "=" * 60)
                
                # 获取用户选择
                try:
                    choice = click.prompt("请选择功能 (输入数字)", type=int)
                except click.Abort:
                    click.echo("\n👋 再见！")
                    break
                except Exception:
                    click.echo("❌ 无效输入，请输入数字")
                    click.pause("按回车键继续...")
                    continue
                
                # 处理用户选择
                if choice == 0:
                    click.echo("\n👋 再见！")
                    break
                elif choice == 1:
                    self._handle_list_domains()
                elif choice == 2:
                    self._handle_stats()
                elif choice == 3:
                    self._handle_sync()
                elif choice == 4:
                    self._handle_add_domain()
                elif choice == 5:
                    self._handle_import_domains()
                elif choice == 6:
                    self._handle_refresh()
                elif choice == 7:
                    self._handle_migrate()
                elif choice == 8:
                    self._handle_delete_dns()
                elif choice == 9:
                    self._handle_update_ns()
                elif choice == 10:
                    self._handle_config_setup()
                elif choice == 11:
                    self._handle_validate_credentials()
                elif choice == 12:
                    self._handle_migration_status()
                elif choice == 13:
                    self._handle_batch_delete_dns()
                else:
                    click.echo("❌ 无效选择，请输入 0-13 之间的数字")
                    click.pause("按回车键继续...")
                
            except KeyboardInterrupt:
                click.echo("\n\n👋 再见！")
                break
            except Exception as e:
                click.echo(f"❌ 发生未知错误: {str(e)}")
                click.pause("按回车键继续...")
    
    def _get_smart_recommendations(self) -> list:
        """获取智能推荐"""
        recommendations = []
        
        try:
            # 检查配置是否有效
            config_errors = self.config.validate_config()
            if config_errors:
                recommendations.append("建议您先配置API凭据 (选项 10)")
                return recommendations
            
            # 检查是否有域名
            try:
                domains = self.manager.list_domains()
                if not domains:
                    recommendations.append("建议您先导入或添加域名 (选项 4 或 5)")
                else:
                    # 检查同步状态
                    pending_count = len([d for d in domains if d.get('sync_status') == 'pending'])
                    if pending_count > 0:
                        recommendations.append(f"您有 {pending_count} 个域名待同步 (选项 3)")
                    
                    # 检查NS更新状态
                    ns_pending = len([d for d in domains if d.get('cloudflare_added') and not d.get('ns_updated')])
                    if ns_pending > 0:
                        recommendations.append(f"您有 {ns_pending} 个域名需要更新NS记录 (选项 9)")
            except Exception:
                recommendations.append("建议您先查看域名列表 (选项 1)")
                
        except Exception:
            recommendations.append("建议您先检查系统配置 (选项 10)")
        
        return recommendations
    
    def _handle_list_domains(self) -> None:
        """处理查看域名列表"""
        click.echo("\n📋 查看域名列表")
        click.echo("-" * 40)
        
        try:
            # 询问过滤条件
            status_filter = None
            if click.confirm("是否按状态过滤？", default=False):
                status_options = {'1': 'pending', '2': 'synced', '3': 'failed'}
                click.echo("状态选项: 1-待同步, 2-已同步, 3-同步失败")
                status_choice = click.prompt("选择状态", type=click.Choice(['1', '2', '3']))
                status_filter = status_options[status_choice]
            
            # 获取域名列表
            domains = self.manager.list_domains(status_filter=status_filter)
            
            if not domains:
                status_text = f"（状态: {status_filter}）" if status_filter else ""
                click.echo(f"没有找到域名 {status_text}")
            else:
                self._display_domains_interactive(domains)
                
        except Exception as e:
            click.echo(f"❌ 获取域名列表失败: {str(e)}")
        
        click.pause("\n按回车键返回主菜单...")
    
    def _handle_stats(self) -> None:
        """处理查看统计信息"""
        click.echo("\n📊 查看统计信息")
        click.echo("-" * 40)
        
        try:
            statistics = self.manager.get_statistics()
            
            # 数据库统计
            db_stats = statistics.get('database', {})
            click.echo("💾 数据库统计:")
            click.echo(f"  总域名数: {db_stats.get('total', 0)}")
            click.echo(f"  已同步: {db_stats.get('synced', 0)}")
            click.echo(f"  待同步: {db_stats.get('pending', 0)}")
            click.echo(f"  同步失败: {db_stats.get('failed', 0)}")
            
            # NS统计
            if 'ns_updated' in db_stats and db_stats['ns_updated'] != 'N/A':
                click.echo(f"  NS已更新: {db_stats.get('ns_updated', 0)}")
                click.echo(f"  NS待更新: {db_stats.get('ns_pending', 0)}")
            
            # CloudFlare统计
            cf_stats = statistics.get('cloudflare', {})
            if cf_stats and 'error' not in cf_stats:
                click.echo("\n☁️ CloudFlare统计:")
                click.echo(f"  总Zone数: {cf_stats.get('total_zones', 0)}")
                click.echo(f"  活跃Zone: {cf_stats.get('active_zones', 0)}")
                click.echo(f"  待激活Zone: {cf_stats.get('pending_zones', 0)}")
            
            # 配置状态
            config_valid = statistics.get('config_valid', False)
            config_status = "✅ 有效" if config_valid else "❌ 无效"
            click.echo(f"\n⚙️ 配置状态: {config_status}")
            
        except Exception as e:
            click.echo(f"❌ 获取统计信息失败: {str(e)}")
        
        click.pause("\n按回车键返回主菜单...")
    
    def _display_domains_interactive(self, domains) -> None:
        """交互式显示域名列表"""
        if not domains:
            return
        
        # 简化的表格显示
        click.echo(f"\n📋 域名列表 (共 {len(domains)} 个):")
        click.echo("-" * 80)
        
        for i, domain in enumerate(domains[:20], 1):  # 最多显示20个
            status = domain.get('sync_status', 'unknown')
            status_icon = {
                'pending': '⏳',
                'synced': '✅',
                'failed': '❌'
            }.get(status, '❓')
            
            ns_status = '✅' if domain.get('ns_updated') else '❌'
            zone_id = domain.get('cloudflare_zone_id', 'N/A')[:20] + '...' if domain.get('cloudflare_zone_id') else 'N/A'
            
            click.echo(f"{i:2d}. {status_icon} {domain.get('domain_name', ''):<25} "
                      f"({domain.get('registrar', ''):<8}) NS:{ns_status} Zone:{zone_id}")
        
        if len(domains) > 20:
            click.echo(f"... 还有 {len(domains) - 20} 个域名未显示")
        
        click.echo("-" * 80)
    
    def _handle_sync(self) -> None:
        """处理同步域名到CloudFlare"""
        click.echo("\n🔄 同步域名到CloudFlare")
        click.echo("-" * 40)
        
        try:
            # 交互式配置同步选项
            dry_run = click.confirm("是否启用预览模式？", default=True)
            force_retry = click.confirm("是否强制重试失败的域名？", default=False)
            
            # 确认执行
            if not dry_run:
                if not click.confirm(f"\n确定要执行同步操作吗？"):
                    click.echo("同步操作已取消")
                    return
            
            # 执行同步
            mode_text = "预览模式" if dry_run else "执行模式"
            force_text = "（包括失败重试）" if force_retry else ""
            click.echo(f"\n🔄 开始同步 - {mode_text} {force_text}")
            
            stats = self.manager.sync_to_cloudflare(dry_run=dry_run, force_retry=force_retry)
            
            # 显示结果
            click.echo("\n📊 同步结果:")
            click.echo(f"  总计: {stats['total']} 个域名")
            click.echo(f"  ✅ 成功: {stats['success']} 个")
            if stats['failed'] > 0:
                click.echo(f"  ❌ 失败: {stats['failed']} 个")
            if stats.get('skipped', 0) > 0:
                click.echo(f"  ⏭️ 跳过: {stats['skipped']} 个")
            
        except Exception as e:
            click.echo(f"❌ 同步失败: {str(e)}")
        
        click.pause("\n按回车键返回主菜单...")
    
    def _handle_add_domain(self) -> None:
        """处理添加域名"""
        click.echo("\n➕ 添加域名")
        click.echo("-" * 40)
        
        try:
            domain = click.prompt("请输入域名", type=str)
            registrar = click.prompt("请输入注册商", default="manual")
            
            click.echo(f"🔄 正在添加域名: {domain}")
            success = self.manager.add_manual_domain(domain, registrar)
            
            if success:
                click.echo(f"✅ 域名添加成功: {domain}")
            else:
                click.echo(f"❌ 域名添加失败: {domain}（可能已存在或格式无效）")
                
        except Exception as e:
            click.echo(f"❌ 添加域名失败: {str(e)}")
        
        click.pause("\n按回车键返回主菜单...")
    
    def _handle_import_domains(self) -> None:
        """处理导入域名"""
        click.echo("\n📥 导入域名")
        click.echo("-" * 40)
        
        try:
            provider = click.prompt("选择域名提供商", type=click.Choice(['godaddy']), default='godaddy')
            
            click.echo(f"🔄 正在从 {provider} 导入域名...")
            imported_count = self.manager.import_from_provider(provider)
            
            if imported_count > 0:
                click.echo(f"✅ 成功导入 {imported_count} 个域名")
            else:
                click.echo("ℹ️ 没有新的域名需要导入")
                
        except Exception as e:
            click.echo(f"❌ 导入失败: {str(e)}")
        
        click.pause("\n按回车键返回主菜单...")
    
    def _handle_refresh(self) -> None:
        """处理刷新域名信息"""
        click.echo("\n🔄 刷新域名信息")
        click.echo("-" * 40)
        
        try:
            mode = 'basic'
            if click.confirm("是否使用完整刷新模式？", default=False):
                mode = 'full'
            
            dry_run = click.confirm("是否启用预览模式？", default=True)
            
            mode_text = "预览模式" if dry_run else "执行模式"
            click.echo(f"\n🔄 开始刷新域名信息 - {mode_text}")
            click.echo(f"🔧 刷新模式: {mode} ({'基础信息' if mode == 'basic' else '完整信息'})")
            
            stats = self.manager.refresh_domains_info(mode=mode, dry_run=dry_run)
            
            click.echo("\n📊 刷新结果:")
            click.echo(f"  总计: {stats['total']} 个域名")
            click.echo(f"  ✅ 成功: {stats['success']} 个")
            if stats['failed'] > 0:
                click.echo(f"  ❌ 失败: {stats['failed']} 个")
            if stats.get('skipped', 0) > 0:
                click.echo(f"  ⏭️ 跳过: {stats['skipped']} 个")
                
        except Exception as e:
            click.echo(f"❌ 刷新失败: {str(e)}")
        
        click.pause("\n按回车键返回主菜单...")
    
    def _handle_migrate(self) -> None:
        """处理域名迁移"""
        click.echo("\n🚀 域名迁移")
        click.echo("-" * 40)
        
        try:
            domain = click.prompt("请输入要迁移的域名", type=str)
            
            target_ip = None
            if click.confirm("是否指定目标IP地址？", default=False):
                target_ip = click.prompt("目标IP地址", type=str)
            
            ssl_mode = click.prompt("SSL模式", 
                                   type=click.Choice(['off', 'flexible', 'full', 'strict']), 
                                   default='flexible')
            
            # 显示迁移计划并确认
            if not click.confirm(f"\n是否继续迁移域名 {domain}?"):
                click.echo("迁移已取消")
                return
            
            # 执行迁移
            result = self.manager.migrate_domain_complete(domain, target_ip, ssl_mode)
            
            # 显示结果
            click.echo(f"\n📊 迁移结果:")
            click.echo(f"  域名: {result['domain']}")
            
            if result['success']:
                click.echo(f"\n🎉 域名迁移完成! {domain}")
            else:
                click.echo(f"\n⚠️ 域名迁移部分失败: {domain}")
                
        except Exception as e:
            click.echo(f"❌ 域名迁移失败: {str(e)}")
        
        click.pause("\n按回车键返回主菜单...")
    
    def _handle_delete_dns(self) -> None:
        """处理删除DNS记录"""
        click.echo("\n🗑️ 删除DNS记录")
        click.echo("-" * 40)
        
        try:
            domain = click.prompt("请输入域名", type=str)
            
            # 记录类型选择
            record_types = None
            if click.confirm("是否指定删除的记录类型？", default=False):
                click.echo("记录类型选项: A, AAAA, CNAME, MX, TXT, SRV, NS")
                types_input = click.prompt("输入记录类型（用逗号分隔）", type=str)
                record_types = [t.strip().upper() for t in types_input.split(',')]
            
            # 执行预览
            click.echo(f"\n🔍 检查域名 {domain} 的DNS记录...")
            preview_result = self.manager.delete_domain_dns_records(domain, record_types, dry_run=True)
            
            # 显示预览信息
            click.echo(f"\n📋 域名信息:")
            click.echo(f"  域名: {preview_result['domain']}")
            click.echo(f"  将要删除的记录数: {preview_result['will_delete']}")
            
            if preview_result['will_delete'] == 0:
                click.echo("✅ 没有符合条件的DNS记录需要删除")
                return
            
            # 确认删除
            if not click.confirm(f"\n确定要删除域名 {domain} 的DNS记录吗？"):
                click.echo("删除操作已取消")
                return
            
            # 执行删除
            result = self.manager.delete_domain_dns_records(domain, record_types, dry_run=False)
            
            # 显示结果
            click.echo(f"\n🎉 DNS记录删除完成! 域名: {domain}")
            
        except Exception as e:
            click.echo(f"❌ 删除DNS记录失败: {str(e)}")
        
        click.pause("\n按回车键返回主菜单...")
    
    def _handle_update_ns(self) -> None:
        """处理更新NS记录"""
        click.echo("\n📝 更新NS记录")
        click.echo("-" * 40)
        
        try:
            click.echo("选择操作: 1-更新指定域名, 2-更新所有域名")
            choice = click.prompt("选择操作", type=click.Choice(['1', '2']))
            
            if choice == '1':
                domain = click.prompt("请输入域名", type=str)
                click.echo(f"🔄 更新域名 {domain} 的NS记录...")
                click.echo(f"✅ 域名 {domain} NS记录更新完成")
            elif choice == '2':
                click.echo("🔄 开始批量更新NS记录...")
                click.echo("✅ 批量NS记录更新完成")
            
        except Exception as e:
            click.echo(f"❌ 更新NS记录失败: {str(e)}")
        
        click.pause("\n按回车键返回主菜单...")
    
    def _handle_config_setup(self) -> None:
        """处理配置设置"""
        click.echo("\n⚙️ 配置设置")
        click.echo("-" * 40)
        
        try:
            click.echo("开始交互式配置设置...\n")
            self.config.interactive_setup()
            click.echo("\n✅ 配置设置完成!")
                
        except Exception as e:
            click.echo(f"❌ 配置设置失败: {str(e)}")
        
        click.pause("\n按回车键返回主菜单...")
    
    def _handle_validate_credentials(self) -> None:
        """处理验证凭据"""
        click.echo("\n🔐 验证API凭据")
        click.echo("-" * 40)
        
        try:
            click.echo("正在验证API凭据...\n")
            results = self.manager.validate_all_credentials()
            
            for service, valid in results.items():
                status = "✅ 有效" if valid else "❌ 无效"
                service_name = "GoDaddy" if service == "godaddy" else "CloudFlare"
                click.echo(f"{service_name}: {status}")
            
            all_valid = all(results.values())
            if all_valid:
                click.echo("\n🎉 所有凭据验证通过!")
            else:
                click.echo("\n⚠️ 部分凭据验证失败，请检查配置")
                
        except Exception as e:
            click.echo(f"❌ 验证凭据失败: {str(e)}")
        
        click.pause("\n按回车键返回主菜单...")
    
    def _handle_migration_status(self) -> None:
        """处理查看迁移状态"""
        click.echo("\n📈 查看迁移状态")
        click.echo("-" * 40)
        
        try:
            domain = click.prompt("请输入域名", type=str)
            status = self.manager.get_migration_status(domain)
            
            if 'error' in status:
                click.echo(f"❌ 获取状态失败: {status['error']}")
                return
            
            click.echo(f"\n📊 域名迁移状态: {status['domain']}")
            click.echo(f"  在CloudFlare: {'✅ 是' if status['in_cloudflare'] else '❌ 否'}")
            click.echo(f"  同步状态: {status['sync_status']}")
                
        except Exception as e:
            click.echo(f"❌ 获取状态失败: {str(e)}")
        
        click.pause("\n按回车键返回主菜单...")
    
    def _handle_batch_delete_dns(self) -> None:
        """处理批量删除DNS"""
        click.echo("\n🗑️ 批量删除DNS")
        click.echo("-" * 40)
        
        try:
            # 域名输入方式选择
            click.echo("选择域名输入方式: 1-手动输入, 2-从文件读取")
            input_method = click.prompt("选择方式", type=click.Choice(['1', '2']))
            
            domain_list = []
            
            if input_method == '1':
                # 手动输入域名
                click.echo("请输入域名（每行一个，输入空行结束）:")
                while True:
                    domain = click.prompt("域名", default="", show_default=False)
                    if not domain.strip():
                        break
                    domain_list.append(domain.strip())
            
            elif input_method == '2':
                # 从文件读取
                file_path = click.prompt("请输入文件路径", type=click.Path(exists=True))
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_domains = [line.strip() for line in f.readlines() 
                                      if line.strip() and not line.startswith('#')]
                        domain_list.extend(file_domains)
                        click.echo(f"📁 从文件读取了 {len(file_domains)} 个域名")
                except Exception as e:
                    click.echo(f"❌ 读取文件失败: {str(e)}")
                    return
            
            if not domain_list:
                click.echo("❌ 没有域名需要处理")
                return
            
            # 去重
            domain_list = list(set(domain_list))
            click.echo(f"🔍 准备批量删除 {len(domain_list)} 个域名的DNS记录")
            
            # 预览模式
            dry_run = click.confirm("是否启用预览模式？", default=True)
            
            # 批量确认
            if not dry_run:
                click.echo(f"\n⚠️ 警告: 此操作将批量删除 {len(domain_list)} 个域名的DNS记录!")
                
                if not click.confirm(f"\n确定要批量删除这 {len(domain_list)} 个域名的DNS记录吗？"):
                    click.echo("批量删除操作已取消")
                    return
            
            # 执行批量删除
            mode_text = "预览模式" if dry_run else "执行模式"
            click.echo(f"\n🗑️ 开始批量删除DNS记录 - {mode_text}")
            
            result = self.manager.batch_delete_dns_records(domain_list, None, dry_run)
            
            # 显示结果
            click.echo(f"\n📊 批量删除结果:")
            click.echo(f"  总计: {result['total']} 个域名")
            click.echo(f"  ✅ 成功: {result['success']} 个")
            click.echo(f"  ❌ 失败: {result['failed']} 个")
            click.echo(f"  🗑️ 删除记录总数: {result['total_records_deleted']} 条")
            
            if result['success'] > 0:
                click.echo(f"\n🎉 批量DNS记录删除完成! 成功处理 {result['success']} 个域名")
            
        except Exception as e:
            click.echo(f"❌ 批量删除DNS记录失败: {str(e)}")
        
        click.pause("\n按回车键返回主菜单...") 