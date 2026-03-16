#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中纪委网站腐败舆情爬虫
用于爬取中纪委网站上指定系统（如工商银行）的腐败舆情信息
"""

import os
import re
import json
import csv
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from tqdm import tqdm
import pandas as pd
from DrissionPage import ChromiumPage, ChromiumOptions
from openai import OpenAI

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crawler.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class CorruptionNews:
    """腐败舆情数据类"""
    日期: str = ""
    类型: str = ""
    姓名: str = ""
    职务: str = ""
    地区: str = ""
    省份: str = ""
    舆情摘要: str = ""
    舆情全文: str = ""
    详情URL: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


class LLMAnalyzer:
    """大模型分析器 - 支持多种模型配置"""

    def __init__(self, model_config: Optional[Dict] = None):
        """
        初始化分析器
        :param model_config: 模型配置字典，包含 base_url, api_key, model, temperature
        """
        if model_config is None:
            # 使用默认KIMI配置
            model_config = {
                "base_url": "https://api.moonshot.cn/v1",
                "api_key": os.getenv("MOONSHOT_API_KEY", ""),
                "model": "kimi-k2.5",
                "temperature": 1
            }

        self.base_url = model_config.get("base_url", "https://api.moonshot.cn/v1")
        self.api_key = model_config.get("api_key", "")
        self.model = model_config.get("model", "kimi-k2.5")
        self.temperature = model_config.get("temperature", 1)

        if not self.api_key or self.api_key == "sk-xxxx":
            logger.warning("API Key 未设置，将使用简单规则提取信息")
            self.client = None
        else:
            logger.info(f"使用模型: {self.model}, base_url: {self.base_url}")
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )

    def analyze_content(self, title: str, content: str, news_type: str) -> Dict:
        """使用KIMI分析内容，提取关键信息"""
        if not self.client:
            return self._simple_extract(title, content, news_type)

        prompt = f"""请分析以下中纪委网站发布的腐败舆情信息，提取关键字段：

舆情类型：{news_type}
标题：{title}
正文内容：
{content[:3000]}  # 限制长度避免超出token限制

请提取以下信息并以JSON格式返回：
{{
    "姓名": "当事人姓名，多个用顿号分隔",
    "职务": "当事人的职务，如'工商银行XX省分行副行长'",
    "地区": "案件发生地区，案件发生时当事人的任职地区（不是检察机关地区）",
    "省份": "根据地区推断的省份，如地区是大连市，则省份为辽宁省",
    "舆情摘要": "200字以内的舆情摘要，包含核心事实"
}}

注意：
1. 只返回JSON格式，不要其他文字说明
2. 如果信息不确定，请填写"未知"
3. 特别行政区如香港、澳门的省份地区信息也请如实填写，不要误填为广东省
4. 对于高级专家、资深专家等职务也要准确提取"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的信息提取助手，擅长从政务文本中提取结构化信息。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=1,  # KIMI要求temperature为1
                max_tokens=1000
            )

            result_text = response.choices[0].message.content.strip()

            # 提取JSON部分 - 处理多种格式
            result = self._extract_json_from_text(result_text)
            if result:
                return result
            else:
                logger.warning(f"KIMI返回结果无法解析为JSON: {result_text[:200]}")
                return self._simple_extract(title, content, news_type)

        except Exception as e:
            logger.error(f"KIMI API调用失败: {e}")
            return self._simple_extract(title, content, news_type)

    def _extract_json_from_text(self, text: str) -> Optional[Dict]:
        """从文本中提取JSON对象，处理各种格式"""
        if not text or not text.strip():
            return None

        # 移除markdown代码块标记
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = text.strip()

        # 尝试直接解析整个文本
        try:
            return json.loads(text)
        except:
            pass

        # 尝试提取JSON对象 - 处理截断的情况
        # 首先尝试补全可能截断的JSON
        if text.rfind('{') > text.rfind('}'):
            # JSON可能被截断，尝试补全
            text = text + '"}'
            try:
                return json.loads(text)
            except:
                pass

        # 匹配最外层的大括号对
        brace_count = 0
        start = -1
        for i, char in enumerate(text):
            if char == '{':
                if brace_count == 0:
                    start = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and start != -1:
                    try:
                        return json.loads(text[start:i+1])
                    except:
                        pass

        # 尝试从部分JSON中提取字段（处理截断的情况）
        partial_result = self._extract_from_partial_json(text)
        if partial_result:
            return partial_result

        # 尝试正则表达式匹配
        patterns = [
            r'"姓名"\s*:\s*"([^"]*)"',
            r'"职务"\s*:\s*"([^"]*)"',
            r'"地区"\s*:\s*"([^"]*)"',
            r'"省份"\s*:\s*"([^"]*)"',
            r'"舆情摘要"\s*:\s*"([^"]*)"',
        ]
        result = {}
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                key = pattern.split('"')[1]
                result[key] = match.group(1)

        return result if result else None

    def _extract_from_partial_json(self, text: str) -> Optional[Dict]:
        """从部分/截断的JSON中提取可用字段"""
        result = {}

        # 提取各个字段
        fields = {
            '姓名': r'"姓名"\s*:\s*"([^"，。、；\n]{2,20})"',
            '职务': r'"职务"\s*:\s*"([^"]{5,100}?)"',
            '地区': r'"地区"\s*:\s*"([^"]{2,20})"',
            '省份': r'"省份"\s*:\s*"([^"]{2,20})"',
            '舆情摘要': r'"舆情摘要"\s*:\s*"([^"]{10,300}?)"',
        }

        for field, pattern in fields.items():
            match = re.search(pattern, text)
            if match:
                result[field] = match.group(1)

        return result if result else None

    def _simple_extract(self, title: str, content: str, news_type: str) -> Dict:
        """简单规则提取（当KIMI API不可用时使用）"""
        result = {
            "姓名": "未知",
            "职务": "未知",
            "地区": "未知",
            "省份": "未知",
            "舆情摘要": title
        }

        # 尝试从标题提取姓名（通常是"因涉嫌...被调查"前面的名字）
        name_patterns = [
            r'([^，。、；\s]{2,4}?)涉嫌',
            r'([^，。、；\s]{2,4}?)接受',
            r'([^，。、；\s]{2,4}?)严重违纪',
        ]
        for pattern in name_patterns:
            match = re.search(pattern, title)
            if match:
                result["姓名"] = match.group(1)
                break

        # 尝试提取地区（从检察机构信息）
        region_patterns = [
            r'经(.+?)(?:市|县|区|省)人民检察院',
            r'由(.+?)(?:市|县|区|省)纪委',
            r'(.+?)(?:市|县|区|省)纪委监委',
        ]
        for pattern in region_patterns:
            match = re.search(pattern, content)
            if match:
                region = match.group(1)
                if '省' not in region and len(region) <= 4:
                    result["地区"] = region + "市"
                else:
                    result["地区"] = region
                break

        # 省份映射
        province_map = {
            '北京': '北京市', '上海': '上海市', '天津': '天津市', '重庆': '重庆市',
            '青岛': '山东省', '大连': '辽宁省', '宁波': '浙江省', '厦门': '福建省', '深圳': '广东省',
            '哈尔滨': '黑龙江省', '长春': '吉林省', '沈阳': '辽宁省', '石家庄': '河北省',
            '太原': '山西省', '济南': '山东省', '郑州': '河南省', '西安': '陕西省',
            '兰州': '甘肃省', '西宁': '青海省', '银川': '宁夏回族自治区', '乌鲁木齐': '新疆维吾尔自治区',
            '呼和浩特': '内蒙古自治区', '拉萨': '西藏自治区', '南宁': '广西壮族自治区',
            '昆明': '云南省', '贵阳': '贵州省', '成都': '四川省', '武汉': '湖北省',
            '长沙': '湖南省', '南昌': '江西省', '合肥': '安徽省', '南京': '江苏省',
            '杭州': '浙江省', '福州': '福建省', '广州': '广东省', '海口': '海南省',
        }

        for city, province in province_map.items():
            if city in content or city in result["地区"]:
                result["省份"] = province
                break

        # 职务提取
        position_patterns = [
            r'(中国工商银行[^，。]+?)[党委]',
            r'(工商银行[^，。]+?)[党委]',
            r'([^，。]*?支行[^，。]*?行长)',
            r'([^，。]*?分行[^，。]*?行长)',
        ]
        for pattern in position_patterns:
            match = re.search(pattern, content)
            if match:
                result["职务"] = match.group(1)
                break

        return result


class CCDICrawler:
    """中纪委网站爬虫"""

    # 默认URL配置
    DEFAULT_URLS_DICT = {
        "中管干部执纪审查": "https://www.ccdi.gov.cn/scdcn/zggb/zjsc/",
        "中管干部党纪政务处分": "https://www.ccdi.gov.cn/scdcn/zggb/djcf/",
        "国家单位执纪审查": "https://www.ccdi.gov.cn/scdcn/zyyj/zjsc/",
        "国家单位党纪政务处分": "https://www.ccdi.gov.cn/scdcn/zyyj/djcf/"
    }

    # 默认风险关键词（工商银行相关）
    DEFAULT_RISK_KEYWORDS = ["工商银行", "工行", "ICBC", "工银"]

    def __init__(
        self,
        urls_dict: Optional[Dict[str, str]] = None,
        risk_keywords: Optional[List[str]] = None,
        max_pages: int = 1,
        kimi_api_key: Optional[str] = None,
        headless: bool = True,
        model_config: Optional[Dict] = None
    ):
        self.urls_dict = urls_dict or self.DEFAULT_URLS_DICT
        self.risk_keywords = risk_keywords or self.DEFAULT_RISK_KEYWORDS
        self.max_pages = max_pages
        self.headless = headless
        # 支持新的LLMAnalyzer，传入模型配置
        self.analyzer = LLMAnalyzer(model_config)
        self.page = None
        self.results: List[CorruptionNews] = []

    def _init_browser(self):
        """初始化浏览器"""
        logger.info("正在初始化浏览器...")

        try:
            co = ChromiumOptions()

            if self.headless:
                co.headless(True)

            # 设置浏览器选项以绕过检测
            co.set_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            co.set_argument('--disable-blink-features', 'AutomationControlled')
            co.set_argument('--disable-web-security')
            co.set_argument('--disable-features', 'IsolateOrigins,site-per-process')
            co.set_argument('--no-sandbox')
            co.set_argument('--disable-dev-shm-usage')

            # 设置页面加载超时
            co.set_timeouts(page_load=30, script=30)

            self.page = ChromiumPage(addr_or_opts=co)

            if not self.headless:
                try:
                    self.page.set.window.max()
                except:
                    pass

            # 执行脚本隐藏webdriver属性
            try:
                self.page.run_js("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)
            except:
                pass

            logger.info("浏览器初始化完成")

        except Exception as e:
            logger.error(f"浏览器初始化失败: {e}")
            raise

    def _close_browser(self):
        """关闭浏览器"""
        if self.page:
            self.page.quit()
            logger.info("浏览器已关闭")

    def _contains_keywords(self, text: str) -> bool:
        """检查文本是否包含风险关键词"""
        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in self.risk_keywords)

    def _extract_date(self, text: str) -> str:
        """从文本中提取日期"""
        # 匹配 YYYY-MM-DD 或 YYYY年MM月DD日 格式
        patterns = [
            r'(\d{4}-\d{2}-\d{2})',
            r'(\d{4}年\d{1,2}月\d{1,2}日)',
            r'(\d{4}/\d{2}/\d{2})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                date_str = match.group(1)
                # 统一转换为 YYYY-MM-DD 格式
                date_str = date_str.replace('年', '-').replace('月', '-').replace('日', '').replace('/', '-')
                try:
                    parts = date_str.split('-')
                    if len(parts) == 3:
                        year, month, day = parts
                        return f"{year}-{int(month):02d}-{int(day):02d}"
                except:
                    pass
        return datetime.now().strftime("%Y-%m-%d")

    def _safe_get(self, url: str, retries: int = 3) -> bool:
        """安全获取页面，带重试机制"""
        for i in range(retries):
            try:
                self.page.get(url)
                time.sleep(2)
                return True
            except Exception as e:
                logger.warning(f"页面加载失败 ({i+1}/{retries}): {e}")
                time.sleep(3)
        return False

    def _get_article_links(self, list_url: str, news_type: str) -> List[Dict]:
        """获取文章列表中的所有链接"""
        articles = []

        try:
            self.page.get(list_url)
            time.sleep(2)  # 等待页面加载

            for page_num in range(1, self.max_pages + 1):
                logger.info(f"正在获取 [{news_type}] 第 {page_num} 页...")

                # 获取当前页的文章列表
                html = self.page.html
                soup = BeautifulSoup(html, 'lxml')

                # 查找文章列表 - 中纪委网站常见的列表结构
                article_links = []

                # 尝试多种可能的选择器
                selectors = [
                    '.list-item a', '.news-item a', 'ul.list li a',
                    '.news_list li a', '.list_box li a', '.main-list a',
                    'ul li a', '.list a', '.content-list a'
                ]

                for selector in selectors:
                    items = soup.select(selector)
                    if items:
                        article_links.extend(items)
                        break

                # 如果没有找到，尝试查找所有包含标题的链接
                if not article_links:
                    all_links = soup.find_all('a', href=True)
                    for link in all_links:
                        text = link.get_text(strip=True)
                        # 过滤掉导航链接等
                        if text and len(text) > 10 and self._contains_keywords(text):
                            article_links.append(link)

                for link in article_links:
                    title = link.get_text(strip=True)
                    href = link.get('href', '')

                    # 过滤无效链接
                    if not href or href.startswith('javascript:') or href == '#':
                        continue

                    # 检查标题是否包含风险关键词
                    if not self._contains_keywords(title):
                        continue

                    # 构建完整URL
                    full_url = urljoin(list_url, href)

                    # 提取日期（从标题附近或链接属性中）
                    date = self._extract_date(title)

                    # 查找父元素中的日期信息
                    parent = link.find_parent(['li', 'div', 'td'])
                    if parent:
                        parent_text = parent.get_text(strip=True)
                        extracted_date = self._extract_date(parent_text)
                        if extracted_date:
                            date = extracted_date

                    articles.append({
                        'title': title,
                        'url': full_url,
                        'date': date,
                        'type': news_type
                    })

                # 翻页处理
                if page_num < self.max_pages:
                    if not self._goto_next_page():
                        break

        except Exception as e:
            logger.error(f"获取文章列表失败: {e}")

        logger.info(f"[{news_type}] 共找到 {len(articles)} 条相关文章")
        return articles

    def _goto_next_page(self) -> bool:
        """跳转到下一页，返回是否成功"""
        try:
            # 查找下一页按钮
            next_selectors = [
                'a.next', '.next a', '.pagination .next', 'a:contains("下一页")',
                'a[title="下一页"]', '.page-next', '.page_next'
            ]

            for selector in next_selectors:
                try:
                    next_btn = self.page.ele(selector, timeout=2)
                    if next_btn and next_btn.is_displayed():
                        next_btn.click()
                        time.sleep(2)
                        return True
                except:
                    continue

            # 尝试通过页码数字翻页
            current_page = self.page.run_js('return document.querySelector(".current, .active, .cur")?.textContent || "1"')
            try:
                next_page_num = int(current_page) + 1
                page_link = self.page.ele(f'css:a[onclick*="{next_page_num}"], a:contains("{next_page_num}")', timeout=2)
                if page_link:
                    page_link.click()
                    time.sleep(2)
                    return True
            except:
                pass

            return False

        except Exception as e:
            logger.warning(f"翻页失败: {e}")
            return False

    def _get_article_content(self, url: str) -> Tuple[str, str, str]:
        """获取文章详情页的内容和发布日期"""
        try:
            self.page.get(url)
            time.sleep(2)

            html = self.page.html
            soup = BeautifulSoup(html, 'lxml')

            # 移除脚本和样式元素
            for script in soup(["script", "style"]):
                script.decompose()

            # 尝试多种内容选择器
            content_selectors = [
                '.content-detail', '.detail-content', '.article-content',
                '.content_box', '.main-content', '.news-content',
                '#content', '.content', '.text-content', '.TRS_Editor'
            ]

            content = ""
            for selector in content_selectors:
                elem = soup.select_one(selector)
                if elem:
                    content = elem.get_text(separator='\n', strip=True)
                    break

            # 如果没有找到内容，尝试获取body文本
            if not content:
                body = soup.find('body')
                if body:
                    content = body.get_text(separator='\n', strip=True)

            # 获取标题
            title = ""
            title_selectors = ['h1', '.title', '.article-title', '#title']
            for selector in title_selectors:
                elem = soup.select_one(selector)
                if elem:
                    title = elem.get_text(strip=True)
                    break

            # 获取发布日期 - 从中纪委网站的日期格式提取
            date = ""
            date_selectors = [
                '.date', '.time', '.publish-time', '.pub-time',
                '.article-date', '.news-date', '.info-date',
                '.source', '.article-info', '.meta'
            ]
            for selector in date_selectors:
                elem = soup.select_one(selector)
                if elem:
                    date_text = elem.get_text(strip=True)
                    extracted_date = self._extract_date(date_text)
                    if extracted_date and extracted_date != datetime.now().strftime("%Y-%m-%d"):
                        date = extracted_date
                        break

            # 如果还没有找到日期，从URL中提取（中纪委URL常包含日期）
            if not date:
                url_date = self._extract_date_from_url(url)
                if url_date:
                    date = url_date

            return title, content, date

        except Exception as e:
            logger.error(f"获取文章内容失败 [{url}]: {e}")
            return "", "", ""

    def _extract_date_from_url(self, url: str) -> str:
        """从URL中提取日期（中纪委网站URL常包含日期如/t20260128/）"""
        patterns = [
            r'/t(\d{4})(\d{2})(\d{2})_',  # /t20260128_
            r'/(\d{4})(\d{2})/t\d+',      # /202601/t20260128
            r'/(\d{4})-(\d{2})-(\d{2})/',  # /2026-01-28/
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    return f"{groups[0]}-{groups[1]}-{groups[2]}"
        return ""

    def crawl(self) -> List[CorruptionNews]:
        """执行爬取任务"""
        try:
            self._init_browser()

            all_articles = []

            # 遍历所有URL
            for news_type, url in self.urls_dict.items():
                logger.info(f"开始爬取 [{news_type}]...")
                articles = self._get_article_links(url, news_type)
                all_articles.extend(articles)
                time.sleep(1)

            logger.info(f"总共找到 {len(all_articles)} 条相关文章")

            # 去重
            seen_urls = set()
            unique_articles = []
            for article in all_articles:
                if article['url'] not in seen_urls:
                    seen_urls.add(article['url'])
                    unique_articles.append(article)

            logger.info(f"去重后剩余 {len(unique_articles)} 条文章")

            # 获取每篇文章的详细内容
            for article in tqdm(unique_articles, desc="获取文章详情"):
                try:
                    title, content, detail_date = self._get_article_content(article['url'])

                    if not content:
                        logger.warning(f"文章 [{article['title']}] 内容为空，跳过")
                        continue

                    # 使用详情页的日期（如果有），否则使用列表页的日期
                    final_date = detail_date if detail_date else article['date']

                    # 使用KIMI分析内容
                    analyzed = self.analyzer.analyze_content(
                        article['title'],
                        content,
                        article['type']
                    )

                    news = CorruptionNews(
                        日期=final_date,
                        类型=article['type'],
                        姓名=analyzed.get('姓名', '未知'),
                        职务=analyzed.get('职务', '未知'),
                        地区=analyzed.get('地区', '未知'),
                        省份=analyzed.get('省份', '未知'),
                        舆情摘要=analyzed.get('舆情摘要', article['title']),
                        舆情全文=content,
                        详情URL=article['url']
                    )

                    self.results.append(news)
                    logger.info(f"成功处理文章: {news.姓名} - {news.职务}")

                    # 避免请求过快
                    time.sleep(1)

                except Exception as e:
                    logger.error(f"处理文章失败 [{article['url']}]: {e}")
                    continue

        finally:
            self._close_browser()

        return self.results

    def save_to_json(self, filename: str = "corruption_news.json"):
        """保存结果为JSON格式"""
        data = [r.to_dict() for r in self.results]
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"结果已保存到 {filename}")

    def save_to_csv(self, filename: str = "corruption_news.csv"):
        """保存结果为CSV格式"""
        if not self.results:
            logger.warning("没有数据可保存")
            return

        data = [r.to_dict() for r in self.results]
        df = pd.DataFrame(data)
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        logger.info(f"结果已保存到 {filename}")

    def print_summary(self):
        """打印爬取结果摘要"""
        print("\n" + "=" * 80)
        print(f"爬取完成！共获取 {len(self.results)} 条腐败舆情信息")
        print("=" * 80)

        if self.results:
            print("\n【舆情摘要】")
            for i, news in enumerate(self.results, 1):
                print(f"\n{i}. [{news.类型}] {news.姓名} - {news.职务}")
                print(f"   日期: {news.日期}")
                print(f"   地区: {news.地区} ({news.省份})")
                print(f"   摘要: {news.舆情摘要[:100]}...")
                print(f"   URL: {news.详情URL}")


def main():
    """主函数 - 工商银行示例"""
    # 记录开始时间
    start_time = datetime.now()

    # 配置参数
    config = {
        # 要爬取的URL字典
        "urls_dict": {
            "中管干部执纪审查": "https://www.ccdi.gov.cn/scdcn/zggb/zjsc/",
            "中管干部党纪政务处分": "https://www.ccdi.gov.cn/scdcn/zggb/djcf/",
            "国家单位执纪审查": "https://www.ccdi.gov.cn/scdcn/zyyj/zjsc/",
            "国家单位党纪政务处分": "https://www.ccdi.gov.cn/scdcn/zyyj/djcf/"
        },

        # 风险关键词（工商银行相关）
        "risk_keywords": ["工商银行", "工行", "ICBC", "工银"],

        # 最大翻页数量
        "max_pages": 1,

        # KIMI API Key（从环境变量获取或使用默认值）
        "kimi_api_key": os.getenv("MOONSHOT_API_KEY", ""),

        # 是否使用无头浏览器
        "headless": False  # 首次运行建议设为False以便观察
    }

    print("=" * 80)
    print("中纪委网站腐败舆情爬虫 - 工商银行系统示例")
    print("=" * 80)
    print(f"\n配置信息:")
    print(f"  - 监控类型: {list(config['urls_dict'].keys())}")
    print(f"  - 风险关键词: {config['risk_keywords']}")
    print(f"  - 最大翻页: {config['max_pages']}")
    print(f"  - KIMI API: {'已配置' if config['kimi_api_key'] else '未配置（将使用简单规则）'}")
    print(f"  - 无头模式: {config['headless']}")
    print("\n" + "=" * 80)

    # 创建爬虫实例并运行
    crawler = CCDICrawler(
        urls_dict=config["urls_dict"],
        risk_keywords=config["risk_keywords"],
        max_pages=config["max_pages"],
        kimi_api_key=config["kimi_api_key"],
        headless=config["headless"]
    )

    # 执行爬取
    results = crawler.crawl()

    # 保存结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_file = f"icbc_corruption_news_{timestamp}.json"
    csv_file = f"icbc_corruption_news_{timestamp}.csv"

    crawler.save_to_json(json_file)
    crawler.save_to_csv(csv_file)

    # 打印摘要
    crawler.print_summary()

    # 计算执行时间
    end_time = datetime.now()
    elapsed = end_time - start_time
    hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    print(f"\n文件保存位置:")
    print(f"  - JSON: {json_file}")
    print(f"  - CSV: {csv_file}")
    print(f"  - 日志: crawler.log")

    print("\n" + "=" * 80)
    print("执行时间统计")
    print("=" * 80)
    print(f"  开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  总耗时: {hours}小时 {minutes}分钟 {seconds}秒")
    print("=" * 80)

    return results


if __name__ == "__main__":
    main()
