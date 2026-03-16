# 中纪委腐败舆情爬虫系统

基于FastAPI的智能化中纪委网站腐败舆情爬虫系统，支持定时任务、Web管理和多种大模型配置。

## 功能特性

- **多类型监控**：支持中管干部执纪审查、党纪政务处分、国家单位执纪审查等多种类型
- **AI内容分析**：支持KIMI云端、Qwen3本地等多种大模型智能提取信息
- **定时任务**：支持Cron表达式设置自动爬取（如每天9点）
- **Web管理界面**：可视化操作，无需命令行
- **API服务**：RESTful API，支持远程调用
- **反爬绕过**：使用DrissionPage浏览器自动化技术
- **多格式输出**：支持JSON和CSV格式

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务

```bash
# 启动API服务（包含Web界面）
python api.py

# 或使用自定义端口
python api.py 8080
```

服务启动后访问：
- **Web管理界面**: http://localhost:8000/
- **API文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

### 3. 配置大模型（可选但推荐）

#### KIMI云端模型（默认）
```bash
# Windows
set MOONSHOT_API_KEY=sk-your-api-key

# Linux/Mac
export MOONSHOT_API_KEY=sk-your-api-key
```

#### 本地模型（如Qwen3）
在Web界面的"大模型配置"中选择"Qwen3 Instruct"或"Qwen3 Reasoning"

## 使用方式

### 方式一：Web界面（推荐）

1. 打开浏览器访问 http://localhost:8000/
2. 在"大模型配置"中选择或配置模型
3. 在"快速操作"中选择要爬取的任务类型
4. 点击"立即开始爬取"
5. 在"任务执行状态"中查看进度
6. 完成后可下载JSON或CSV格式结果

### 方式二：API调用

```python
import requests

# 创建爬取任务
response = requests.post("http://localhost:8000/crawl", json={
    "urls_dict": {
        "国家单位执纪审查": "https://www.ccdi.gov.cn/scdcn/zyyj/zjsc/",
        "国家单位党纪政务处分": "https://www.ccdi.gov.cn/scdcn/zyyj/djcf/"
    },
    "risk_keywords": ["工商银行", "工行", "ICBC", "工银"],
    "max_pages": 2,
    "headless": True
})
task_id = response.json()["task_id"]
print(f"任务已创建: {task_id}")

# 查询任务状态
status = requests.get(f"http://localhost:8000/tasks/{task_id}").json()
print(f"状态: {status['status']}, 进度: {status['progress']}%")

# 下载结果（任务完成后）
json_url = f"http://localhost:8000/tasks/{task_id}/download/json"
csv_url = f"http://localhost:8000/tasks/{task_id}/download/csv"
```

### 方式三：定时任务

通过API创建定时任务：

```python
import requests

# 创建每天9点执行的定时任务
requests.post("http://localhost:8000/schedules", json={
    "name": "每日9点爬取",
    "cron": "0 9 * * *",
    "config": {
        "urls_dict": {"国家单位执纪审查": "https://www.ccdi.gov.cn/scdcn/zyyj/zjsc/"},
        "risk_keywords": ["工商银行", "工行"],
        "max_pages": 2,
        "headless": True
    },
    "enabled": True
})
```

或在Web界面的"定时任务管理"中添加。

## 支持的模型

| 模型 | 类型 | 配置方式 |
|------|------|----------|
| KIMI云端 | 云端API | 设置MOONSHOT_API_KEY环境变量 |
| Qwen3 Instruct | 本地部署 | base_url: http://10.29.40.143:9655/v1 |
| Qwen3 Reasoning | 本地部署 | base_url: http://10.29.40.141:9654/v1 |
| 自定义 | 其他模型 | Web界面中配置base_url、api_key、model |

## 项目结构

```
.
├── api.py                 # FastAPI服务主文件
├── ccdi_crawler.py        # 爬虫核心逻辑
├── scheduler.py           # 定时任务调度器
├── config.py              # 配置文件
├── utils.py               # 工具函数
├── run.py                 # 命令行入口（可选）
├── requirements.txt       # Python依赖
├── urls_config.json       # URL配置
├── templates/
│   └── index.html         # Web管理界面
├── README.md              # 项目说明
├── DEPLOYMENT.md          # 部署指南
├── QUICKSTART.md          # 快速开始
└── SCHEDULER_USAGE.md     # 调度器使用说明
```

## API端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | Web管理界面 |
| `/crawl` | POST | 创建爬取任务 |
| `/tasks` | GET | 获取所有任务 |
| `/tasks/{id}` | GET | 获取任务状态 |
| `/tasks/{id}` | DELETE | 删除任务 |
| `/tasks/{id}/results` | GET | 获取任务结果 |
| `/tasks/{id}/download/json` | GET | 下载JSON结果 |
| `/tasks/{id}/download/csv` | GET | 下载CSV结果 |
| `/schedules` | GET/POST | 获取/创建定时任务 |
| `/schedules/{id}` | GET/PUT/DELETE | 获取/更新/删除定时任务 |
| `/schedules/{id}/toggle` | POST | 启用/禁用定时任务 |
| `/schedules/history` | GET/DELETE | 获取/清空执行历史 |
| `/models` | GET | 获取可用模型列表 |
| `/health` | GET | 健康检查 |
| `/docs` | GET | API文档（Swagger） |

## 输出字段

| 字段 | 说明 |
|------|------|
| 日期 | 信息发布日期 |
| 类型 | 舆情类型（如"国家单位执纪审查"） |
| 姓名 | 当事人姓名 |
| 职务 | 当事人的职务 |
| 地区 | 案件相关地区 |
| 省份 | 根据地区推断的省份 |
| 舆情摘要 | 200字以内的摘要 |
| 舆情全文 | 详情页的完整内容 |
| 详情URL | 原文链接 |

## 生产部署

详见 [DEPLOYMENT.md](DEPLOYMENT.md)，支持：
- Docker部署
- Linux服务器部署
- Nginx反向代理
- HTTPS配置

## 依赖环境

- Python 3.8+
- Chrome浏览器（用于爬虫）
- 可选：KIMI API Key

## 免责声明

本工具仅供学习和研究使用，请遵守相关法律法规，不要用于非法用途。使用本工具产生的一切后果由使用者自行承担。
