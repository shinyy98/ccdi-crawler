# 中纪委爬虫系统架构文档

## 一、项目概述

本项目是一个基于 FastAPI 的中纪委腐败舆情爬虫系统，采用分层架构设计，支持 Web 管理界面、定时任务调度、多种大模型配置等功能。

## 二、系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户交互层                                │
├────────────────────────────┬────────────────────────────────────┤
│     Web 管理界面            │         API 客户端                  │
│   (templates/index.html)    │    (api_quickstart.py)              │
├────────────────────────────┴────────────────────────────────────┤
│                         API 网关层                                │
│                      FastAPI (api.py)                            │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐       │
│  │  爬虫API     │  定时任务API │  模型配置API │  文件下载API │       │
│  └─────────────┴─────────────┴─────────────┴─────────────┘       │
├─────────────────────────────────────────────────────────────────┤
│                        业务逻辑层                                 │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐        │
│  │  爬虫调度器     │  │  定时任务调度器 │  │  LLM解析器     │        │
│  │ scheduler.py  │  │  scheduler.py │  │  ccdi_crawler │        │
│  └───────────────┘  └───────────────┘  └───────┬───────┘        │
├────────────────────────────────────────────────┼────────────────┤
│                        核心引擎层               │                │
│  ┌──────────────────────┐  ┌──────────────────┐│                │
│  │   DrissionPage       │  │   多模型LLM      ││                │
│  │   (浏览器自动化)      │  │   (KIMI/Qwen3)   ││                │
│  └──────────────────────┘  └──────────────────┘│                │
├─────────────────────────────────────────────────────────────────┤
│                        数据存储层                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  JSON结果文件 │  │  CSV结果文件  │  │  内存状态    │           │
│  │ api_results/ │  │ api_results/ │  │ task_status  │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

## 三、文件架构详解

### 3.1 核心文件（7个）

| 文件 | 类型 | 职责 | 依赖关系 |
|------|------|------|----------|
| `api.py` | 入口/控制器 | FastAPI服务主文件，提供HTTP接口 | 依赖 scheduler, ccdi_crawler |
| `ccdi_crawler.py` | 核心引擎 | 爬虫逻辑、LLM解析、数据提取 | 依赖 config, utils |
| `scheduler.py` | 调度器 | APScheduler定时任务管理 | 独立模块 |
| `config.py` | 配置 | 全局配置、常量定义 | 无依赖 |
| `utils.py` | 工具 | 通用工具函数 | 无依赖 |
| `run.py` | CLI入口 | 命令行版本入口 | 依赖 ccdi_crawler |
| `urls_config.json` | 配置 | URL映射配置 | 无依赖 |

### 3.2 文件依赖关系图

```
                    ┌─────────────┐
                    │   用户请求   │
                    └──────┬──────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │  api.py    │  │  run.py    │  │  Web界面   │
    │ (FastAPI)  │  │  (CLI)     │  │ (Browser)  │
    └─────┬──────┘  └─────┬──────┘  └────────────┘
          │               │
          │    ┌──────────┘
          │    │
          ▼    ▼
    ┌─────────────────┐
    │  ccdi_crawler   │
    │    .py          │
    │  (爬虫核心引擎)  │
    └───────┬─────────┘
            │
    ┌───────┴───────┐
    │               │
    ▼               ▼
┌──────────┐  ┌──────────┐
│ config   │  │  utils   │
│ .py      │  │  .py     │
└──────────┘  └──────────┘
            │
            ▼
    ┌───────────────┐
    │  scheduler    │
    │    .py        │
    │ (定时任务调度) │
    └───────────────┘
```

## 四、核心模块详解

### 4.1 FastAPI 服务层 (api.py)

**框架**: FastAPI + Uvicorn

**构建方法**:
```python
from fastapi import FastAPI

app = FastAPI(
    title="中纪委爬虫API",
    description="提供腐败舆情爬取服务",
    version="1.0.0"
)

# 挂载静态文件（Web界面）
app.mount("/", StaticFiles(directory="templates"), name="static")

# 定义API端点
@app.post("/crawl")
async def create_crawl_task(request: CrawlRequest):
    # 业务逻辑
    pass
```

**核心功能**:
- RESTful API 设计
- 异步请求处理
- 后台任务管理
- 静态文件服务（Web界面）

### 4.2 爬虫引擎层 (ccdi_crawler.py)

**框架**: DrissionPage + OpenAI API

**架构模式**: 策略模式（多模型支持）

**核心类设计**:
```python
class CCDICrawler:
    """爬虫主类"""

    def __init__(self, model_config):
        self.page = ChromiumPage()  # 浏览器实例
        self.llm = LLMParser(model_config)  # LLM解析器

    def crawl(self, urls, keywords):
        # 爬取逻辑
        pass

    def extract_with_llm(self, content):
        # AI内容解析
        pass
```

**构建方法**:
1. 使用 DrissionPage 创建浏览器实例
2. 配置反爬策略（User-Agent、WebDriver隐藏）
3. 通过 KIMI/Qwen3 API 解析提取结构化数据
4. 输出 JSON/CSV 格式

### 4.3 定时任务调度器 (scheduler.py)

**框架**: APScheduler

**架构模式**: 单例模式 + 观察者模式

**核心组件**:
```python
class TaskScheduler:
    """定时任务调度器"""

    def __init__(self, crawl_callback):
        self.scheduler = AsyncIOScheduler()  # 异步调度器
        self.scheduled_jobs = {}  # 任务存储
        self.crawl_callback = crawl_callback  # 爬虫回调

    def add_schedule(self, name, cron, config):
        # 添加Cron定时任务
        trigger = CronTrigger.from_crontab(cron)
        job = self.scheduler.add_job(
            func=self._execute,
            trigger=trigger,
            args=[name, config]
        )
```

**构建方法**:
1. 使用 APScheduler 创建异步调度器
2. 支持 Cron 表达式（如 `0 9 * * *` 每天9点）
3. 任务状态持久化（JSON文件）
4. 执行历史记录

## 五、数据流图

### 5.1 单次爬取流程

```
用户请求
    │
    ▼
┌────────────┐
│  api.py    │  1. 接收请求，创建任务ID
│  POST /crawl│
└─────┬──────┘
      │
      ▼
┌────────────────┐
│  BackgroundTask│  2. 后台异步执行
└─────┬──────────┘
      │
      ▼
┌────────────────┐
│ ccdi_crawler   │  3. 浏览器访问中纪委网站
│ .crawl()       │  4. 抓取文章列表
└─────┬──────────┘
      │
      ▼
┌────────────────┐
│  LLM解析       │  5. AI提取关键信息
│ extract_info() │  6. 结构化数据
└─────┬──────────┘
      │
      ▼
┌────────────────┐
│  输出文件       │  7. 保存JSON/CSV
│ api_results/   │  8. 更新任务状态
└────────────────┘
```

### 5.2 定时任务流程

```
┌──────────────┐
│  APScheduler │  1. 根据Cron触发
│  定时触发     │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ TaskScheduler│  2. 查找任务配置
│ _execute()   │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ api.py       │  3. 调用爬虫API
│ crawl()      │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ ccdi_crawler │  4. 执行爬取
│ .crawl()     │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ 记录历史      │  5. 保存执行结果
│ job_history  │
└──────────────┘
```

## 六、扩展性设计

### 6.1 多模型支持

```python
# 模型配置字典
AVAILABLE_MODELS = {
    "kimi_cloud": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "api_key": "${MOONSHOT_API_KEY}"
    },
    "qwen3_instruct": {
        "base_url": "http://10.29.40.143:9655/v1",
        "model": "FundGPT-large"
    },
    "qwen3_reasoning": {
        "base_url": "http://10.29.40.141:9654/v1",
        "model": "FundGPT-R"
    }
}
```

**扩展方法**: 在 `AVAILABLE_MODELS` 中添加新配置即可支持新模型。

### 6.2 新URL类型扩展

在 `urls_config.json` 中添加：
```json
{
    "新类型名称": "https://www.ccdi.gov.cn/xxx/xxx/"
}
```

### 6.3 API端点扩展

在 `api.py` 中添加：
```python
@app.post("/new-endpoint")
async def new_feature(request: RequestModel):
    # 实现逻辑
    pass
```

## 七、部署架构

### 7.1 生产环境部署

```
                    用户
                     │
                     ▼
            ┌─────────────────┐
            │    Nginx        │  反向代理、SSL、静态文件
            │    :80/:443     │
            └────────┬────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
┌─────────────────┐    ┌─────────────────┐
│   Gunicorn      │    │  静态文件服务    │
│   (4 workers)   │    │  templates/     │
│   :8000         │    └─────────────────┘
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   FastAPI       │
│   (api.py)      │
└─────────────────┘
```

### 7.2 Docker 部署

```dockerfile
FROM python:3.11-slim

# 安装Chrome
RUN apt-get update && apt-get install -y chromium

# 安装依赖
COPY requirements.txt .
RUN pip install -r requirements.txt

# 复制代码
COPY . .

# 启动
CMD ["gunicorn", "api:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker"]
```

## 八、开发指南

### 8.1 添加新功能流程

1. **修改数据模型**: 在 `api.py` 的 Pydantic Model 中添加字段
2. **实现业务逻辑**: 在 `ccdi_crawler.py` 或 `scheduler.py` 中实现
3. **添加API端点**: 在 `api.py` 中添加路由
4. **更新前端**: 在 `templates/index.html` 中添加界面
5. **更新文档**: 修改 `README.md`

### 8.2 调试方法

```bash
# 1. 前台启动，查看日志
python api.py

# 2. 使用测试脚本
python api_quickstart.py

# 3. 访问API文档
open http://localhost:8000/docs

# 4. 查看爬虫日志
tail -f crawler.log
```

## 九、总结

本项目采用**分层架构**设计：
- **表现层**: Web界面、API接口
- **业务层**: 爬虫逻辑、定时调度
- **数据层**: 文件存储、内存状态

核心优势：
1. **模块化**: 各模块职责清晰，易于维护
2. **可扩展**: 支持多模型、多URL类型
3. **易部署**: 支持Docker、云服务器多种部署方式
4. **高性能**: 异步处理、后台任务、浏览器复用
