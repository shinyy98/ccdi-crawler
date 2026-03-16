#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中纪委爬虫API 快速调用示例

功能：
- 创建爬取任务
- 轮询任务状态
- 获取爬取结果
- 下载JSON/CSV文件

使用方法：
1. 确保API服务已启动: python api.py
2. 运行: python api_quickstart.py
"""

import requests
import time
import json
from datetime import datetime

# API基础地址
API_BASE = "http://localhost:8000"


def create_crawl_task(
    keywords=None,
    max_pages=2,
    urls_dict=None,
    preset_model="kimi_cloud"
):
    """
    创建爬取任务

    参数:
        keywords: 关键词列表，如["工商银行", "工行", "ICBC"]
        max_pages: 最大翻页数（1-10）
        urls_dict: 要爬取的URL字典
        preset_model: 使用的模型（kimi_cloud/qwen3_instruct/qwen3_reasoning）

    返回:
        task_id: 任务ID
    """
    if keywords is None:
        keywords = ["工商银行", "工行", "ICBC", "工银"]

    if urls_dict is None:
        urls_dict = {
            "国家单位执纪审查": "https://www.ccdi.gov.cn/scdcn/zyyj/zjsc/",
            "国家单位党纪政务处分": "https://www.ccdi.gov.cn/scdcn/zyyj/djcf/"
        }

    payload = {
        "urls_dict": urls_dict,
        "risk_keywords": keywords,
        "max_pages": max_pages,
        "headless": True,
        "preset_model": preset_model
    }

    print(f"[创建任务] 关键词: {keywords}, 页数: {max_pages}, 模型: {preset_model}")

    response = requests.post(f"{API_BASE}/crawl", json=payload)
    response.raise_for_status()

    data = response.json()
    task_id = data["task_id"]

    print(f"✓ 任务创建成功: {task_id}")
    print(f"  状态: {data['status']}")
    print(f"  创建时间: {data['created_at']}")

    return task_id


def wait_for_task(task_id, timeout=600, poll_interval=5):
    """
    轮询等待任务完成

    参数:
        task_id: 任务ID
        timeout: 最大等待时间（秒）
        poll_interval: 轮询间隔（秒）

    返回:
        status: 最终状态（completed/failed）
    """
    print(f"\n[等待任务完成] 任务ID: {task_id}")
    print(f"  超时时间: {timeout}秒, 轮询间隔: {poll_interval}秒\n")

    start_time = time.time()

    while time.time() - start_time < timeout:
        response = requests.get(f"{API_BASE}/tasks/{task_id}")
        response.raise_for_status()

        status_data = response.json()
        status = status_data["status"]
        progress = status_data.get("progress", 0)
        message = status_data.get("message", "")

        # 打印进度
        bar_length = 30
        filled = int(bar_length * progress / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        print(f"\r[{bar}] {progress}% | {status} | {message[:30]}", end="", flush=True)

        if status == "completed":
            print(f"\n\n✓ 任务完成！")
            print(f"  结果数量: {status_data.get('result_count', 0)}")
            if status_data.get("completed_at"):
                print(f"  完成时间: {status_data['completed_at']}")
            return status

        elif status == "failed":
            print(f"\n\n✗ 任务失败！")
            print(f"  错误: {status_data.get('message', '未知错误')}")
            return status

        time.sleep(poll_interval)

    print(f"\n\n⚠ 等待超时！")
    return "timeout"


def get_task_results(task_id, preview=3):
    """
    获取任务结果（预览）

    参数:
        task_id: 任务ID
        preview: 预览前几条记录
    """
    print(f"\n[获取结果] 任务ID: {task_id}")

    response = requests.get(f"{API_BASE}/tasks/{task_id}/results")
    response.raise_for_status()

    data = response.json()
    results = data.get("results", [])

    print(f"✓ 共获取 {len(results)} 条记录")
    print(f"  执行时间: {data.get('execution_time', 'N/A')}")

    # 预览前几条
    if results and preview > 0:
        print(f"\n[前{min(preview, len(results))}条记录预览]")
        for i, record in enumerate(results[:preview], 1):
            print(f"\n{i}. [{record.get('类型', 'N/A')}] {record.get('姓名', 'N/A')}")
            print(f"   职务: {record.get('职务', 'N/A')}")
            print(f"   日期: {record.get('日期', 'N/A')}")
            print(f"   省份: {record.get('省份', 'N/A')}")
            print(f"   摘要: {record.get('舆情摘要', 'N/A')[:50]}...")

    return results


def download_results(task_id, save_dir="./downloads"):
    """
    下载JSON和CSV格式的结果文件

    参数:
        task_id: 任务ID
        save_dir: 保存目录
    """
    import os

    print(f"\n[下载结果文件]")

    # 创建保存目录
    os.makedirs(save_dir, exist_ok=True)

    # 下载JSON
    json_url = f"{API_BASE}/tasks/{task_id}/download/json"
    json_response = requests.get(json_url)

    if json_response.status_code == 200:
        json_path = os.path.join(save_dir, f"{task_id}.json")
        with open(json_path, "wb") as f:
            f.write(json_response.content)
        print(f"✓ JSON已保存: {json_path}")
    else:
        print(f"✗ JSON下载失败: {json_response.status_code}")

    # 下载CSV
    csv_url = f"{API_BASE}/tasks/{task_id}/download/csv"
    csv_response = requests.get(csv_url)

    if csv_response.status_code == 200:
        csv_path = os.path.join(save_dir, f"{task_id}.csv")
        with open(csv_path, "wb") as f:
            f.write(csv_response.content)
        print(f"✓ CSV已保存: {csv_path}")
    else:
        print(f"✗ CSV下载失败: {csv_response.status_code}")


def create_schedule_task(
    name="每日9点自动爬取",
    cron="0 9 * * *",
    keywords=None,
    max_pages=2
):
    """
    创建定时任务

    参数:
        name: 任务名称
        cron: Cron表达式，如"0 9 * * *"表示每天9点
        keywords: 关键词列表
        max_pages: 最大翻页数

    返回:
        schedule_id: 定时任务ID
    """
    if keywords is None:
        keywords = ["工商银行", "工行", "ICBC", "工银"]

    config = {
        "name": name,
        "cron": cron,
        "config": {
            "urls_dict": {
                "国家单位执纪审查": "https://www.ccdi.gov.cn/scdcn/zyyj/zjsc/",
                "国家单位党纪政务处分": "https://www.ccdi.gov.cn/scdcn/zyyj/djcf/"
            },
            "risk_keywords": keywords,
            "max_pages": max_pages,
            "headless": True,
            "preset_model": "kimi_cloud"
        },
        "enabled": True
    }

    print(f"\n[创建定时任务]")
    print(f"  名称: {name}")
    print(f"  执行时间: {cron} (每天9点)")
    print(f"  关键词: {keywords}")

    response = requests.post(f"{API_BASE}/schedules", json=config)
    response.raise_for_status()

    data = response.json()
    print(f"✓ 定时任务创建成功: {data['id']}")
    print(f"  下次执行: {data.get('next_run', 'N/A')}")

    return data["id"]


def list_schedules():
    """查看所有定时任务"""
    print("\n[定时任务列表]")

    response = requests.get(f"{API_BASE}/schedules")
    response.raise_for_status()

    schedules = response.json()

    if not schedules:
        print("  暂无定时任务")
        return

    print(f"  共 {len(schedules)} 个定时任务:\n")

    for s in schedules:
        status = "✓ 启用" if s.get("enabled") else "✗ 禁用"
        print(f"  - {s['name']}")
        print(f"    ID: {s['id']}")
        print(f"    执行时间: {s['cron']}")
        print(f"    状态: {status}")
        print(f"    下次执行: {s.get('next_run', 'N/A')}\n")


def main():
    """主函数：演示完整流程"""

    print("=" * 60)
    print("中纪委爬虫API 快速调用示例")
    print("=" * 60)
    print(f"API地址: {API_BASE}")
    print(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    try:
        # 1. 创建爬取任务
        task_id = create_crawl_task(
            keywords=["工商银行", "工行", "ICBC"],
            max_pages=2,
            preset_model="kimi_cloud"
        )

        # 2. 等待任务完成
        status = wait_for_task(task_id, timeout=600, poll_interval=5)

        if status == "completed":
            # 3. 获取结果预览
            results = get_task_results(task_id, preview=3)

            # 4. 下载结果文件
            download_results(task_id, save_dir="./downloads")

            print(f"\n{'='*60}")
            print("✓ 所有操作完成！")
            print(f"{'='*60}")

        else:
            print("\n✗ 任务未成功完成")

    except requests.exceptions.ConnectionError:
        print("\n✗ 连接失败！请确保API服务已启动:")
        print(f"  运行: python api.py")
        print(f"  然后访问: {API_BASE}/health")

    except Exception as e:
        print(f"\n✗ 错误: {e}")


if __name__ == "__main__":
    main()
