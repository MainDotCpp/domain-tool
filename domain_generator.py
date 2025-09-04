import random
import string
import argparse

# 经济金融投资科技相关单词库
ADJECTIVES = [
    'smart', 'digital', 'global', 'secure', 'rapid', 'stable', 'prime', 'elite', 'alpha', 'beta',
    'premium', 'pro', 'expert', 'advanced', 'efficient', 'optimal', 'strategic', 'dynamic', 'agile', 'robust',
    'innovative', 'disruptive', 'scalable', 'flexible', 'liquid', 'solid', 'growth', 'value', 'yield', 'profit',
    'future', 'next', 'ultra', 'mega', 'micro', 'macro', 'quantum', 'neural', 'auto', 'instant'
]

NOUNS = [
    'capital', 'fund', 'asset', 'equity', 'bond', 'stock', 'share', 'portfolio', 'wealth', 'finance',
    'invest', 'trade', 'market', 'exchange', 'bank', 'credit', 'loan', 'cash', 'coin', 'token',
    'blockchain', 'crypto', 'bitcoin', 'defi', 'fintech', 'paytech', 'regtech', 'insurtech', 'wealthtech', 'neobank',
    'algorithm', 'data', 'analytics', 'ml', 'ai', 'robot', 'automation', 'platform', 'system', 'network'
]

TECH_WORDS = [
    'tech', 'fintech', 'regtech', 'insurtech', 'paytech', 'wealthtech', 'proptech', 'lendtech', 'roboadviser', 'neobank',
    'blockchain', 'crypto', 'defi', 'cefi', 'dao', 'nft', 'web3', 'metaverse', 'ai', 'ml',
    'analytics', 'algorithm', 'quant', 'trading', 'invest', 'capital', 'fund', 'asset', 'portfolio', 'wealth'
]

def generate_domain(style='word'):
    """生成随机域名
    style: 'word' - 单词组合, 'random' - 随机字符, 'tech' - 科技风格
    """
    tlds = ['.fun','.site','.life','.online','.site','.sotre','.ink','.space','.cloud','.buzz','.monster','.work','.live']

    if style == 'word':
        # 形容词 + 名词组合
        adj = random.choice(ADJECTIVES)
        noun = random.choice(NOUNS)
        domain_name = adj + noun
    elif style == 'tech':
        # 科技风格：名词 + 科技词汇
        word1 = random.choice(NOUNS + ADJECTIVES)
        word2 = random.choice(TECH_WORDS)
        domain_name = word1 + word2
    elif style == 'hybrid':
        # 混合风格：单词 + 数字
        word = random.choice(ADJECTIVES + NOUNS)
        number = random.randint(1, 999)
        domain_name = word + str(number)
    else:  # random
        # 原始随机字符方式
        chars = string.ascii_lowercase + string.digits
        domain_name = ''.join(random.choice(chars) for _ in range(6))

    tld = random.choice(tlds)
    return domain_name + tld

def mutate_domain(domain):
    """随机修改域名主体中的一个字母
    只修改域名主体部分，保持TLD不变
    """
    # 分离域名主体和TLD
    if '.' in domain:
        domain_parts = domain.rsplit('.', 1)
        domain_body = domain_parts[0]
        tld = '.' + domain_parts[1]
    else:
        # 如果没有TLD，整个域名作为主体
        domain_body = domain
        tld = ''
    
    # 如果域名主体为空或只有一个字符，无法变异
    if len(domain_body) <= 1:
        return domain
    
    # 随机选择一个字母位置进行变异
    position = random.randint(0, len(domain_body) - 1)
    
    # 生成新的随机小写字母
    new_char = random.choice(string.ascii_lowercase)
    
    # 变异域名主体
    mutated_body = domain_body[:position] + new_char + domain_body[position + 1:]
    
    # 重新组合域名
    return mutated_body + tld

def generate_domains(count, style='word'):
    """生成指定数量的域名"""
    domains = []
    for _ in range(count):
        domain = generate_domain(style)
        # 对生成的域名进行变异
        mutated_domain = mutate_domain(domain)
        domains.append(mutated_domain)
    return domains

def main():
    parser = argparse.ArgumentParser(description='随机生成域名')
    parser.add_argument('-n', '--number', type=int, default=10,
                       help='生成域名的数量 (默认: 10)')
    parser.add_argument('-s', '--style', choices=['word', 'tech', 'hybrid', 'random'],
                       default='word', help='域名风格 (默认: word)')
    parser.add_argument('-o', '--output', type=str, default='domains.txt',
                       help='输出文件名 (默认: domains.txt)')

    args = parser.parse_args()

    style_names = {
        'word': '单词组合',
        'tech': '科技风格',
        'hybrid': '混合风格',
        'random': '随机字符'
    }

    domains = generate_domains(args.number, args.style)

    # 写入文件
    with open(args.output, 'w', encoding='utf-8') as f:
        for domain in domains:
            f.write(domain + '\n')

    print(f"已生成 {args.number} 个{style_names[args.style]}域名到文件: {args.output}")

if __name__ == "__main__":
    main()
