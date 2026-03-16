#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
爬虫配置文件
修改此文件中的参数来自定义爬取行为
"""

import os

# ============================================
# 爬取配置
# ============================================

# 要爬取的中纪委网站URL字典
# 格式: {"类型名称": "URL地址"}
URLS_DICT = {
    "中管干部执纪审查": "https://www.ccdi.gov.cn/scdcn/zggb/zjsc/",
    "中管干部党纪政务处分": "https://www.ccdi.gov.cn/scdcn/zggb/djcf/",
    "国家单位执纪审查": "https://www.ccdi.gov.cn/scdcn/zyyj/zjsc/",
    "国家单位党纪政务处分": "https://www.ccdi.gov.cn/scdcn/zyyj/djcf/"
}

# 风险关键词列表
# 当文章标题或内容包含这些关键词时会被记录
# 工商银行示例：
RISK_KEYWORDS_ICBC = ["工商银行", "工行", "ICBC", "工银"]

# 其他银行示例：
RISK_KEYWORDS_CCB = ["建设银行", "建行", "CCB", "建银"]
RISK_KEYWORDS_ABC = ["农业银行", "农行", "ABC"]
RISK_KEYWORDS_BOC = ["中国银行", "中行", "BOC"]

# 默认使用工商银行关键词
RISK_KEYWORDS = RISK_KEYWORDS_ICBC

# 最大翻页数量（默认为1，设为更大的数字可以获取更多历史数据）
MAX_PAGES = 3

# 是否使用无头浏览器（不显示浏览器窗口）
# True: 后台运行，不显示浏览器
# False: 显示浏览器窗口，便于调试观察
HEADLESS = False

# ============================================
# 大模型 API 配置
# ============================================

# 预设模型配置
# 用户可以通过 API 请求中的 model_config 参数选择或自定义模型
PRESET_MODELS = {
    "kimi_cloud": {
        "name": "KIMI 云端 (Moonshot)",
        "base_url": "https://api.moonshot.cn/v1",
        "api_key": os.getenv("MOONSHOT_API_KEY", ""),
        "model": "kimi-k2.5",
        "temperature": 1,
        "description": "KIMI云端大模型 - 需要外网访问"
    },
    "qwen3_instruct": {
        "name": "Qwen3 Instruct (本地)",
        "base_url": "http://10.29.40.143:9655/v1",
        "api_key": "ailab_1234567890",
        "model": "FundGPT-large",
        "temperature": 0.7,
        "description": "Qwen3-235B-A22B-Instruct (非推理模型)"
    },
    "qwen3_reasoning": {
        "name": "Qwen3 Reasoning (本地)",
        "base_url": "http://10.29.40.141:9654/v1",
        "api_key": "ailab_1234567890",
        "model": "FundGPT-R",
        "temperature": 0.7,
        "description": "Qwen3-235B-A22B (推理模型)"
    }
}

# 默认使用的模型
DEFAULT_MODEL = "kimi_cloud"

# 向后兼容 - 旧的 KIMI 配置
MOONSHOT_API_KEY = os.getenv("MOONSHOT_API_KEY", "")
KIMI_BASE_URL = "https://api.moonshot.cn/v1"
KIMI_MODEL = "kimi-k2.5"
KIMI_TEMPERATURE = 1

# ============================================
# 输出配置
# ============================================

# 输出文件格式
OUTPUT_FORMAT_JSON = True
OUTPUT_FORMAT_CSV = True

# 输出文件前缀
OUTPUT_PREFIX = "corruption_news"
