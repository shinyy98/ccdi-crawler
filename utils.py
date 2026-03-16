#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具函数模块
"""

import json
import csv
import os
from typing import List, Dict, Optional
from datetime import datetime


def export_to_json(data: List[Dict], filename: str):
    """导出数据到JSON文件"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"数据已导出到: {filename}")


def export_to_csv(data: List[Dict], filename: str):
    """导出数据到CSV文件"""
    if not data:
        print("没有数据可导出")
        return

    # 获取所有字段名
    fieldnames = list(data[0].keys())

    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    print(f"数据已导出到: {filename}")


def merge_results(files: List[str], output_prefix: str = "merged"):
    """合并多个结果文件"""
    all_data = []

    for file in files:
        if file.endswith('.json'):
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                all_data.extend(data)
        elif file.endswith('.csv'):
            import pandas as pd
            df = pd.read_csv(file, encoding='utf-8')
            all_data.extend(df.to_dict('records'))

    # 去重
    seen_urls = set()
    unique_data = []
    for item in all_data:
        url = item.get('详情URL', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_data.append(item)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_file = f"{output_prefix}_{timestamp}.json"
    csv_file = f"{output_prefix}_{timestamp}.csv"

    export_to_json(unique_data, json_file)
    export_to_csv(unique_data, csv_file)

    print(f"\n合并完成！")
    print(f"  去重前: {len(all_data)} 条")
    print(f"  去重后: {len(unique_data)} 条")


def generate_report(data_file: str, output_file: Optional[str] = None):
    """生成统计报告"""
    import pandas as pd

    # 读取数据
    if data_file.endswith('.json'):
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        df = pd.DataFrame(data)
    else:
        df = pd.read_csv(data_file, encoding='utf-8')

    # 生成报告
    report = []
    report.append("=" * 80)
    report.append("腐败舆情统计报告")
    report.append("=" * 80)
    report.append(f"\n数据来源: {data_file}")
    report.append(f"统计时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"\n总记录数: {len(df)}")

    if '类型' in df.columns:
        report.append("\n【按类型统计】")
        type_counts = df['类型'].value_counts()
        for t, count in type_counts.items():
            report.append(f"  {t}: {count} 条")

    if '省份' in df.columns:
        report.append("\n【按省份统计】")
        province_counts = df['省份'].value_counts().head(10)
        for p, count in province_counts.items():
            report.append(f"  {p}: {count} 条")

    if '日期' in df.columns:
        report.append("\n【按年份统计】")
        df['年份'] = pd.to_datetime(df['日期'], errors='coerce').dt.year
        year_counts = df['年份'].value_counts().sort_index(ascending=False)
        for y, count in year_counts.head(5).items():
            if pd.notna(y):
                report.append(f"  {int(y)}年: {count} 条")

    report.append("\n" + "=" * 80)

    report_text = '\n'.join(report)
    print(report_text)

    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report_text)
        print(f"\n报告已保存到: {output_file}")


def search_in_results(data_file: str, keyword: str):
    """在结果中搜索关键词"""
    import pandas as pd

    # 读取数据
    if data_file.endswith('.json'):
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        df = pd.DataFrame(data)
    else:
        df = pd.read_csv(data_file, encoding='utf-8')

    # 搜索
    mask = False
    for col in df.columns:
        if df[col].dtype == 'object':
            mask = mask | df[col].str.contains(keyword, na=False)

    results = df[mask]

    print(f"\n搜索 '{keyword}' 找到 {len(results)} 条结果:")
    print("=" * 80)

    for idx, row in results.iterrows():
        print(f"\n{idx + 1}. [{row.get('类型', 'N/A')}] {row.get('姓名', 'N/A')}")
        print(f"   职务: {row.get('职务', 'N/A')}")
        print(f"   日期: {row.get('日期', 'N/A')}")
        print(f"   地区: {row.get('地区', 'N/A')} ({row.get('省份', 'N/A')})")
        print(f"   URL: {row.get('详情URL', 'N/A')}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("""
工具脚本使用说明:

1. 合并多个结果文件:
   python utils.py merge file1.json file2.json file3.csv

2. 生成统计报告:
   python utils.py report data.json

3. 在结果中搜索:
   python utils.py search data.json "关键词"
        """)
        sys.exit(0)

    command = sys.argv[1]

    if command == "merge" and len(sys.argv) > 2:
        merge_results(sys.argv[2:])
    elif command == "report" and len(sys.argv) > 2:
        output = sys.argv[3] if len(sys.argv) > 3 else None
        generate_report(sys.argv[2], output)
    elif command == "search" and len(sys.argv) > 3:
        search_in_results(sys.argv[2], sys.argv[3])
    else:
        print("参数错误，请查看使用说明")
