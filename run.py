#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中纪委网站腐败舆情爬虫 - 运行脚本
支持命令行参数配置
"""

import argparse
import sys
import os
from datetime import datetime

# 确保可以导入本地模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ccdi_crawler import CCDICrawler
from config import (
    URLS_DICT, RISK_KEYWORDS, MAX_PAGES,
    MOONSHOT_API_KEY, HEADLESS
)


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='中纪委网站腐败舆情爬虫',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  # 使用默认配置爬取工商银行相关信息
  python run.py

  # 爬取建设银行相关信息
  python run.py --keywords "建设银行" "建行" "CCB"

  # 爬取更多页面
  python run.py --max-pages 5

  # 指定输出文件名
  python run.py --output my_result

  # 后台运行（无头模式）
  python run.py --headless

  # 使用特定API Key
  python run.py --api-key "sk-xxxx"
        '''
    )

    parser.add_argument(
        '--keywords', '-k',
        nargs='+',
        default=None,
        help='风险关键词列表（默认使用config.py中的配置）'
    )

    parser.add_argument(
        '--max-pages', '-p',
        type=int,
        default=MAX_PAGES,
        help=f'最大翻页数量（默认: {MAX_PAGES}）'
    )

    parser.add_argument(
        '--headless',
        action='store_true',
        default=HEADLESS,
        help='使用无头浏览器模式'
    )

    parser.add_argument(
        '--api-key',
        type=str,
        default=MOONSHOT_API_KEY,
        help='KIMI API Key'
    )

    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help='输出文件名前缀'
    )

    parser.add_argument(
        '--urls-file',
        type=str,
        default=None,
        help='URL配置文件路径（JSON格式）'
    )

    parser.add_argument(
        '--bank', '-b',
        type=str,
        choices=['icbc', 'ccb', 'abc', 'boc', 'custom'],
        default='icbc',
        help='预设银行类型: icbc(工行), ccb(建行), abc(农行), boc(中行)'
    )

    return parser.parse_args()


def get_bank_keywords(bank_type):
    """获取银行关键词"""
    keywords_map = {
        'icbc': ["工商银行", "工行", "ICBC", "工银"],
        'ccb': ["建设银行", "建行", "CCB", "建银"],
        'abc': ["农业银行", "农行", "ABC"],
        'boc': ["中国银行", "中行", "BOC"],
    }
    return keywords_map.get(bank_type, RISK_KEYWORDS)


def load_urls_from_file(filepath):
    """从JSON文件加载URL配置"""
    import json
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    """主函数"""
    args = parse_args()

    # 确定关键词
    if args.keywords:
        keywords = args.keywords
    else:
        keywords = get_bank_keywords(args.bank)

    # 确定URL配置
    if args.urls_file:
        urls_dict = load_urls_from_file(args.urls_file)
    else:
        urls_dict = URLS_DICT

    # 打印配置信息
    print("=" * 80)
    print("中纪委网站腐败舆情爬虫")
    print("=" * 80)
    print(f"\n运行配置:")
    print(f"  - 银行类型: {args.bank.upper()}")
    print(f"  - 风险关键词: {keywords}")
    print(f"  - 监控类型: {list(urls_dict.keys())}")
    print(f"  - 最大翻页: {args.max_pages}")
    print(f"  - 无头模式: {args.headless}")
    print(f"  - KIMI API: {'已配置' if args.api_key else '未配置'}")
    print("\n" + "=" * 80)

    # 确认提示
    if not args.headless:
        print("\n提示: 浏览器将显示，请勿关闭浏览器窗口")
        print("按 Ctrl+C 可随时中断程序\n")

    try:
        # 创建爬虫实例
        crawler = CCDICrawler(
            urls_dict=urls_dict,
            risk_keywords=keywords,
            max_pages=args.max_pages,
            kimi_api_key=args.api_key,
            headless=args.headless
        )

        # 执行爬取
        results = crawler.crawl()

        # 确定输出文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = args.output or f"{args.bank}_corruption_news"

        json_file = f"{prefix}_{timestamp}.json"
        csv_file = f"{prefix}_{timestamp}.csv"

        # 保存结果
        crawler.save_to_json(json_file)
        crawler.save_to_csv(csv_file)

        # 打印摘要
        crawler.print_summary()

        print(f"\n文件保存位置:")
        print(f"  - JSON: {json_file}")
        print(f"  - CSV: {csv_file}")
        print(f"  - 日志: crawler.log")

        # 返回结果数量（用于脚本调用）
        return len(results)

    except KeyboardInterrupt:
        print("\n\n用户中断程序")
        return 0
    except Exception as e:
        print(f"\n程序运行出错: {e}")
        import traceback
        traceback.print_exc()
        return -1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code if exit_code >= 0 else 1)
