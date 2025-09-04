#!/usr/bin/env python3
"""
Domain Tool - 主程序入口

用法：
    python main.py --help
"""

import sys
from pathlib import Path

# 添加src目录到Python路径
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

if __name__ == "__main__":
    from src.cli import cli
    cli() 