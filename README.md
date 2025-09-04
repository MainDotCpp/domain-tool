# Domain Tool - 域名管理工具

一个用于自动同步域名到CloudFlare的Python命令行工具。

## 功能特性

- 支持从GoDaddy导入域名信息
- 自动同步域名到CloudFlare
- **一键完成域名迁移**：添加到CloudFlare + 修改NS + 创建DNS记录 + 设置SSL
- 自动更新名称服务器记录
- 创建基础DNS记录（A记录、CNAME记录）
- 设置SSL模式（灵活、完整、严格）
- SQLite数据库存储域名状态
- 支持批量操作和单个域名管理
- 完整的日志记录和错误处理
- 可扩展的多注册商支持架构

## 安装要求

- Python 3.8+
- GoDaddy API密钥
- CloudFlare API令牌和账户ID

## 快速开始

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 配置API密钥：
```bash
export GODADDY_API_KEY="your_godaddy_key"
export GODADDY_API_SECRET="your_godaddy_secret" 
export CLOUDFLARE_API_TOKEN="your_cloudflare_token"
export CLOUDFLARE_ACCOUNT_ID="your_cloudflare_account_id"
```

**获取CloudFlare账户ID的方法：**
1. 登录CloudFlare仪表板
2. 在右侧边栏找到"API"部分
3. 复制"Account ID"字段的值

3. 运行工具：
```bash
python main.py --help
```

## 快速开始 - 一键迁移

1. 添加域名到数据库：
```bash
uv run main.py add bondgood.top --registrar godaddy
```

2. 一键完成域名迁移：
```bash
uv run main.py migrate bondgood.top
```

3. 查看迁移状态：
```bash
uv run main.py migration-status bondgood.top
```

## 命令使用

### 导入域名
```bash
python main.py import-domains --provider godaddy
```

### 同步到CloudFlare
```bash
python main.py sync --dry-run  # 预览模式
python main.py sync            # 实际执行
python main.py sync --update-ns  # 同步并自动更新NS记录
python main.py sync --update-ns --no-confirm-ns  # 跳过NS更新确认
```

### 手动添加域名
```bash
python main.py add example.com --registrar godaddy
```

### 列出域名
```bash
python main.py list-domains
python main.py list-domains --status pending
```

### 更新名称服务器记录
```bash
python main.py update-ns example.com           # 更新指定域名的NS记录
python main.py update-ns --all                 # 批量更新所有域名的NS记录
python main.py update-ns --all --force         # 强制更新，跳过确认
```

### 一键完成域名迁移 🚀
```bash
# 完整域名迁移（添加到CloudFlare + 修改NS + 创建DNS记录 + 设置SSL）
python main.py migrate example.com                           # 使用默认配置
python main.py migrate example.com --target-ip 192.168.1.100 # 指定目标IP
python main.py migrate example.com --ssl-mode full           # 设置SSL模式
python main.py migrate example.com --no-confirm              # 跳过确认
```

### 查看域名迁移状态
```bash
python main.py migration-status example.com    # 查看域名迁移状态
```

## 一键域名迁移详解 🎯

`migrate` 命令将自动完成以下步骤：

1. **添加域名到CloudFlare**
   - 创建Zone并获取Zone ID
   - 验证域名所有权

2. **更新名称服务器记录**
   - 获取CloudFlare分配的名称服务器
   - 自动更新GoDaddy域名的NS记录
   - 备份原始NS记录

3. **创建DNS记录**
   - 如果指定了`--target-ip`，创建A记录
   - 如果未指定IP，创建CNAME记录
   - 自动创建www子域名记录

4. **设置SSL模式**
   - 默认设置为"flexible"（灵活模式）
   - 可选择：off（关闭）、flexible（灵活）、full（完整）、strict（严格）

### 使用示例

```bash
# 基本迁移（创建CNAME记录，SSL设置为flexible）
uv run main.py migrate example.com

# 指定IP地址（创建A记录）
uv run main.py migrate example.com --target-ip 192.168.1.100

# 设置SSL为完整模式
uv run main.py migrate example.com --ssl-mode full

# 跳过所有确认
uv run main.py migrate example.com --no-confirm

# 组合使用
uv run main.py migrate example.com --target-ip 192.168.1.100 --ssl-mode strict --no-confirm
```

## 配置文件

工具支持环境变量和配置文件两种配置方式。配置文件示例请参考 `.env.example`。

### 高级配置选项

#### GoDaddy客户端类型

工具支持两种GoDaddy API客户端：

- **新客户端（推荐）**: 使用自建的HTTP客户端，更稳定可靠
- **传统客户端**: 使用godaddypy库，保持向后兼容

```bash
# 使用新客户端（默认）
export GODADDY_CLIENT_TYPE="new"

# 使用传统客户端
export GODADDY_CLIENT_TYPE="legacy"
```

新客户端具有以下优势：
- 更好的错误处理和重试机制
- 完全控制API调用逻辑
- 消除第三方库依赖问题
- 更详细的日志记录

#### 名称服务器自动更新

工具支持自动更新GoDaddy域名的NS记录为CloudFlare的名称服务器，实现完整的域名迁移。

```bash
# 启用自动NS更新
export AUTO_UPDATE_NAMESERVERS=true

# 启用更新前确认
export CONFIRM_NS_UPDATE=true

# 设置NS更新超时时间
export NS_UPDATE_TIMEOUT=30

# 设置NS验证延迟时间
export NS_VERIFICATION_DELAY=5
```

NS更新功能特性：
- **自动更新**: 域名同步后自动更新NS记录
- **原始备份**: 自动备份原始NS记录，支持回滚
- **用户确认**: 支持更新前确认模式
- **批量操作**: 支持批量更新多个域名
- **完整追踪**: 数据库记录NS更新状态和时间

## 开发

项目采用模块化设计，支持扩展更多域名注册商。

## 许可证

MIT License # domain-tool
