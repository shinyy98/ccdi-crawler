#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中纪委爬虫 FastAPI 服务
提供 RESTful API 接口供外部调用
支持定时任务和Web管理界面
"""

import os
import json
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
import uvicorn

from ccdi_crawler import CCDICrawler, CorruptionNews
from scheduler import TaskScheduler
from config import PRESET_MODELS, DEFAULT_MODEL

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('api.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 全局任务状态存储
task_status: Dict[str, Dict] = {}

# 定时任务调度器
task_scheduler: Optional[TaskScheduler] = None


class ScheduleRequest(BaseModel):
    """定时任务请求"""
    name: str = Field(..., description="任务名称")
    cron: str = Field(..., description="Cron表达式 (如 '0 9 * * *' 表示每天9点)")
    config: dict = Field(..., description="爬虫配置")
    enabled: bool = Field(default=True, description="是否启用")


class ScheduleResponse(BaseModel):
    """定时任务响应"""
    id: str
    name: str
    cron: str
    enabled: bool
    next_run: Optional[str]
    created_at: str


class ScheduleToggleRequest(BaseModel):
    """启用/禁用定时任务请求"""
    enabled: bool = Field(..., description="是否启用")


class ScheduleUpdateRequest(BaseModel):
    """更新定时任务请求"""
    name: Optional[str] = Field(default=None, description="任务名称")
    cron: Optional[str] = Field(default=None, description="Cron表达式")
    config: Optional[dict] = Field(default=None, description="爬虫配置")


class ModelConfig(BaseModel):
    """大模型配置"""
    base_url: str = Field(default="https://api.moonshot.cn/v1", description="API基础URL")
    api_key: str = Field(default="", description="API密钥")
    model: str = Field(default="kimi-k2.5", description="模型名称")
    temperature: float = Field(default=1.0, description="温度参数")


class CrawlRequest(BaseModel):
    """爬虫请求参数"""
    urls_dict: Optional[Dict[str, str]] = Field(
        default={
            "中管干部执纪审查": "https://www.ccdi.gov.cn/scdcn/zggb/zjsc/",
            "中管干部党纪政务处分": "https://www.ccdi.gov.cn/scdcn/zggb/djcf/",
            "国家单位执纪审查": "https://www.ccdi.gov.cn/scdcn/zyyj/zjsc/",
            "国家单位党纪政务处分": "https://www.ccdi.gov.cn/scdcn/zyyj/djcf/"
        },
        description="要爬取的URL字典（支持自定义URL）"
    )
    risk_keywords: List[str] = Field(
        default=["工商银行", "工行", "ICBC", "工银"],
        description="风险关键词列表"
    )
    max_pages: int = Field(default=1, ge=1, le=10, description="最大翻页数量")
    headless: bool = Field(default=True, description="是否使用无头浏览器")
    llm_config: Optional[ModelConfig] = Field(
        default=None,
        description="大模型配置（不填使用默认KIMI云端）"
    )
    preset_model: Optional[str] = Field(
        default=None,
        description="预设模型名称: kimi_cloud, qwen3_instruct, qwen3_reasoning"
    )


class CrawlResponse(BaseModel):
    """爬虫响应"""
    task_id: str
    status: str
    message: str
    created_at: str


class TaskStatus(BaseModel):
    """任务状态"""
    task_id: str
    status: str  # pending, running, completed, failed
    progress: int  # 0-100
    created_at: str
    completed_at: Optional[str] = None
    result_count: Optional[int] = None
    message: Optional[str] = None
    error: Optional[str] = None


class CrawlResult(BaseModel):
    """爬取结果"""
    task_id: str
    status: str
    data: List[Dict]
    total: int
    execution_time: Optional[str] = None


def get_model_config(preset_model: Optional[str], model_config: Optional[Dict]) -> Dict:
    """获取模型配置"""
    # 如果提供了自定义配置，优先使用
    if model_config:
        return model_config

    # 如果指定了预设模型，使用预设配置
    if preset_model and preset_model in PRESET_MODELS:
        return PRESET_MODELS[preset_model]

    # 默认使用KIMI云端
    return PRESET_MODELS[DEFAULT_MODEL]


async def run_scheduled_crawl(config: dict) -> dict:
    """定时任务执行的爬虫回调函数"""
    task_id = generate_task_id()
    created_at = datetime.now().isoformat()

    # 初始化任务状态
    task_status[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0,
        "created_at": created_at,
        "message": "定时任务已创建，等待执行...",
        "is_scheduled": True
    }

    # 获取模型配置
    model_cfg = get_model_config(
        config.get("preset_model"),
        config.get("llm_config")
    )

    # 执行爬虫任务
    await run_crawler_task(
        task_id,
        config.get("urls_dict", {}),
        config.get("risk_keywords", []),
        config.get("max_pages", 1),
        config.get("headless", True),
        model_cfg
    )

    return {"task_id": task_id, "status": "completed"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global task_scheduler

    logger.info("=" * 80)
    logger.info("中纪委爬虫 API 服务启动")
    logger.info("=" * 80)

    # 初始化定时任务调度器
    task_scheduler = TaskScheduler(crawl_callback=run_scheduled_crawl)
    logger.info("定时任务调度器已初始化")

    yield

    # 关闭时清理
    if task_scheduler:
        task_scheduler.shutdown()
    logger.info("API 服务关闭")


app = FastAPI(
    title="中纪委腐败舆情爬虫 API",
    description="提供中纪委网站腐败舆情信息的爬取服务，支持定时任务和Web管理界面",
    version="2.0.0",
    lifespan=lifespan
)

# 模板和静态文件
templates = Jinja2Templates(directory="templates")


def generate_task_id() -> str:
    """生成任务ID"""
    return f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"


async def run_crawler_task(
    task_id: str,
    urls_dict: Dict[str, str],
    risk_keywords: List[str],
    max_pages: int,
    headless: bool,
    model_config: Dict = None
):
    """后台运行爬虫任务"""
    start_time = datetime.now()

    try:
        # 更新任务状态为运行中
        task_status[task_id].update({
            "status": "running",
            "message": "正在初始化爬虫...",
            "progress": 10
        })

        # 创建爬虫实例
        crawler = CCDICrawler(
            urls_dict=urls_dict,
            risk_keywords=risk_keywords,
            max_pages=max_pages,
            headless=headless,
            model_config=model_config
        )

        task_status[task_id].update({
            "message": "正在爬取文章列表...",
            "progress": 30
        })

        # 执行爬取
        results = await asyncio.to_thread(crawler.crawl)

        # 计算执行时间
        end_time = datetime.now()
        elapsed = end_time - start_time
        hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        execution_time = f"{hours}小时 {minutes}分钟 {seconds}秒"

        # 保存结果到文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = "api_results"
        os.makedirs(output_dir, exist_ok=True)

        json_file = f"{output_dir}/crawl_{task_id}_{timestamp}.json"
        csv_file = f"{output_dir}/crawl_{task_id}_{timestamp}.csv"

        crawler.save_to_json(json_file)
        crawler.save_to_csv(csv_file)

        # 更新任务状态为完成
        task_status[task_id].update({
            "status": "completed",
            "progress": 100,
            "completed_at": end_time.isoformat(),
            "result_count": len(results),
            "message": f"爬取完成，共获取 {len(results)} 条记录",
            "execution_time": execution_time,
            "json_file": json_file,
            "csv_file": csv_file,
            "results": [r.to_dict() for r in results]
        })

        logger.info(f"任务 {task_id} 完成，获取 {len(results)} 条记录")

    except Exception as e:
        logger.error(f"任务 {task_id} 执行失败: {e}")
        task_status[task_id].update({
            "status": "failed",
            "error": str(e),
            "message": f"执行失败: {e}",
            "completed_at": datetime.now().isoformat()
        })


@app.get("/", response_class=HTMLResponse)
async def web_dashboard(request: Request):
    """Web管理界面"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/models")
async def list_models():
    """
    获取可用的大模型列表
    """
    return {
        "models": [
            {
                "id": key,
                "name": config["name"],
                "description": config["description"],
                "model": config["model"],
                "base_url": config["base_url"]
            }
            for key, config in PRESET_MODELS.items()
        ],
        "default": DEFAULT_MODEL
    }


@app.get("/api")
async def api_info():
    """API 信息"""
    return {
        "name": "中纪委腐败舆情爬虫 API",
        "version": "2.0.0",
        "docs": "/docs",
        "endpoints": {
            "爬虫任务": {
                "POST /crawl": "启动爬虫任务",
                "GET /tasks": "获取所有任务列表",
                "GET /tasks/{task_id}": "获取任务状态",
                "GET /tasks/{task_id}/results": "获取任务结果",
                "GET /tasks/{task_id}/download/json": "下载JSON结果",
                "GET /tasks/{task_id}/download/csv": "下载CSV结果"
            },
            "定时任务": {
                "GET /schedules": "获取所有定时任务",
                "POST /schedules": "添加定时任务",
                "POST /schedules/{schedule_id}/toggle": "启用/禁用定时任务",
                "DELETE /schedules/{schedule_id}": "删除定时任务",
                "GET /scheduler/history": "获取定时任务执行历史"
            }
        }
    }


@app.post("/crawl", response_model=CrawlResponse)
async def start_crawl(
    request: CrawlRequest,
    background_tasks: BackgroundTasks
):
    """
    启动爬虫任务

    参数:
    - urls_dict: 要爬取的URL字典（支持自定义URL）
    - risk_keywords: 风险关键词列表
    - max_pages: 最大翻页数量(1-10)
    - headless: 是否使用无头浏览器
    - model_config: 自定义模型配置（可选）
    - preset_model: 预设模型名称 kimi_cloud/qwen3_instruct/qwen3_reasoning（可选）

    返回任务ID，可以通过任务ID查询任务状态
    """
    task_id = generate_task_id()
    created_at = datetime.now().isoformat()

    # 初始化任务状态
    task_status[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0,
        "created_at": created_at,
        "message": "任务已创建，等待执行..."
    }

    # 获取模型配置
    model_cfg = get_model_config(
        request.preset_model,
        request.llm_config.dict() if request.llm_config else None
    )

    logger.info(f"使用模型: {model_cfg.get('model', 'unknown')} @ {model_cfg.get('base_url', 'unknown')}")

    # 在后台运行爬虫任务
    background_tasks.add_task(
        run_crawler_task,
        task_id,
        request.urls_dict,
        request.risk_keywords,
        request.max_pages,
        request.headless,
        model_cfg
    )

    logger.info(f"创建任务 {task_id}")

    return CrawlResponse(
        task_id=task_id,
        status="pending",
        message="爬虫任务已启动，请通过任务ID查询状态",
        created_at=created_at
    )


@app.get("/tasks", response_model=List[TaskStatus])
async def list_tasks():
    """
    获取所有任务列表
    """
    return [
        TaskStatus(
            task_id=task_id,
            status=info.get("status", "unknown"),
            progress=info.get("progress", 0),
            created_at=info.get("created_at", ""),
            completed_at=info.get("completed_at"),
            result_count=info.get("result_count"),
            message=info.get("message")
        )
        for task_id, info in task_status.items()
    ]


@app.get("/tasks/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """
    获取任务状态
    """
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="任务不存在")

    info = task_status[task_id]
    return TaskStatus(
        task_id=task_id,
        status=info.get("status", "unknown"),
        progress=info.get("progress", 0),
        created_at=info.get("created_at", ""),
        completed_at=info.get("completed_at"),
        result_count=info.get("result_count"),
        message=info.get("message"),
        error=info.get("error")
    )


@app.get("/tasks/{task_id}/results", response_model=CrawlResult)
async def get_task_results(task_id: str):
    """
    获取任务结果数据

    只在任务完成后返回数据
    """
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="任务不存在")

    info = task_status[task_id]

    if info["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"任务尚未完成，当前状态: {info['status']}"
        )

    return CrawlResult(
        task_id=task_id,
        status=info["status"],
        data=info.get("results", []),
        total=info.get("result_count", 0),
        execution_time=info.get("execution_time")
    )


@app.get("/tasks/{task_id}/download/json")
async def download_json(task_id: str):
    """
    下载JSON格式结果文件
    """
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="任务不存在")

    info = task_status[task_id]

    if info["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"任务尚未完成，当前状态: {info['status']}"
        )

    json_file = info.get("json_file")
    if not json_file or not os.path.exists(json_file):
        raise HTTPException(status_code=404, detail="结果文件不存在")

    return FileResponse(
        json_file,
        media_type="application/json",
        filename=f"crawl_result_{task_id}.json"
    )


@app.get("/tasks/{task_id}/download/csv")
async def download_csv(task_id: str):
    """
    下载CSV格式结果文件
    """
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="任务不存在")

    info = task_status[task_id]

    if info["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"任务尚未完成，当前状态: {info['status']}"
        )

    csv_file = info.get("csv_file")
    if not csv_file or not os.path.exists(csv_file):
        raise HTTPException(status_code=404, detail="结果文件不存在")

    return FileResponse(
        csv_file,
        media_type="text/csv",
        filename=f"crawl_result_{task_id}.csv"
    )


@app.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """
    删除任务及其结果
    """
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="任务不存在")

    info = task_status[task_id]

    # 删除结果文件
    for file_key in ["json_file", "csv_file"]:
        file_path = info.get(file_key)
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"删除文件: {file_path}")

    # 删除任务记录
    del task_status[task_id]
    logger.info(f"删除任务: {task_id}")

    return {"message": f"任务 {task_id} 已删除"}


@app.get("/health")
async def health_check():
    """
    健康检查接口
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_tasks": len([t for t in task_status.values() if t["status"] in ["pending", "running"]]),
        "total_tasks": len(task_status),
        "scheduled_tasks": len(task_scheduler.scheduled_jobs) if task_scheduler else 0
    }


# ==================== 定时任务管理 API ====================

@app.get("/schedules", response_model=List[ScheduleResponse])
async def list_schedules():
    """
    获取所有定时任务
    """
    if not task_scheduler:
        raise HTTPException(status_code=503, detail="调度器未初始化")

    schedules = task_scheduler.get_schedules()
    return [
        ScheduleResponse(
            id=s["id"],
            name=s["name"],
            cron=s["cron"],
            enabled=s.get("enabled", True),
            next_run=s.get("next_run"),
            created_at=s["created_at"]
        )
        for s in schedules
    ]


# 注意：/scheduler/history 必须在 /schedules/{schedule_id} 之前定义
@app.get("/scheduler/history")
async def get_schedule_history(limit: int = 20):
    """
    获取定时任务执行历史
    """
    if not task_scheduler:
        raise HTTPException(status_code=503, detail="调度器未初始化")

    history = task_scheduler.get_history(limit=limit)
    return history


@app.delete("/scheduler/history")
async def clear_schedule_history():
    """
    清空定时任务执行历史
    """
    if not task_scheduler:
        raise HTTPException(status_code=503, detail="调度器未初始化")

    success = task_scheduler.clear_history()

    if not success:
        raise HTTPException(status_code=500, detail="清空历史失败")

    return {"message": "执行历史已清空"}


@app.post("/schedules", response_model=ScheduleResponse)
async def create_schedule(request: ScheduleRequest):
    """
    创建定时任务

    参数:
    - name: 任务名称
    - cron: Cron表达式 (如 "0 9 * * *" 表示每天9点)
    - config: 爬虫配置
    - enabled: 是否启用

    Cron表达式格式: 分 时 日 月 周
    - 0 9 * * * : 每天9点
    - 0 9,18 * * * : 每天9点和18点
    - 0 9 * * 1 : 每周一9点
    - 0 9 1 * * : 每月1号9点
    """
    if not task_scheduler:
        raise HTTPException(status_code=503, detail="调度器未初始化")

    try:
        job_id = task_scheduler.add_schedule(
            name=request.name,
            cron_expression=request.cron,
            crawl_config=request.config,
            enabled=request.enabled
        )

        # 获取创建的任务信息
        schedules = task_scheduler.get_schedules()
        schedule = next((s for s in schedules if s["id"] == job_id), None)

        if schedule:
            return ScheduleResponse(
                id=schedule["id"],
                name=schedule["name"],
                cron=schedule["cron"],
                enabled=schedule.get("enabled", True),
                next_run=schedule.get("next_run"),
                created_at=schedule["created_at"]
            )
        else:
            raise HTTPException(status_code=500, detail="创建任务失败")

    except Exception as e:
        logger.error(f"创建定时任务失败: {e}")
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")


@app.post("/schedules/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: str, request: ScheduleToggleRequest):
    """
    启用/禁用定时任务
    """
    if not task_scheduler:
        raise HTTPException(status_code=503, detail="调度器未初始化")

    success = task_scheduler.toggle_schedule(schedule_id, request.enabled)

    if not success:
        raise HTTPException(status_code=404, detail="定时任务不存在")

    return {
        "message": f"任务已{'启用' if request.enabled else '禁用'}",
        "schedule_id": schedule_id,
        "enabled": request.enabled
    }


@app.get("/schedules/{schedule_id}")
async def get_schedule_detail(schedule_id: str):
    """
    获取定时任务详情（用于编辑）
    """
    if not task_scheduler:
        raise HTTPException(status_code=503, detail="调度器未初始化")

    logger.info(f"获取任务详情, ID: {repr(schedule_id)}")
    logger.info(f"可用任务: {list(task_scheduler.scheduled_jobs.keys())}")

    schedule = task_scheduler.get_schedule_by_id(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="定时任务不存在")

    return schedule


@app.put("/schedules/{schedule_id}")
async def update_schedule(schedule_id: str, request: ScheduleUpdateRequest):
    """
    更新定时任务
    """
    if not task_scheduler:
        raise HTTPException(status_code=503, detail="调度器未初始化")

    success = task_scheduler.update_schedule(
        job_id=schedule_id,
        name=request.name,
        cron_expression=request.cron,
        crawl_config=request.config
    )

    if not success:
        raise HTTPException(status_code=404, detail="定时任务不存在或更新失败")

    schedule = task_scheduler.get_schedule_by_id(schedule_id)
    return {
        "message": "定时任务已更新",
        "schedule_id": schedule_id,
        "schedule": schedule
    }


@app.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str):
    """
    删除定时任务
    """
    if not task_scheduler:
        raise HTTPException(status_code=503, detail="调度器未初始化")

    success = task_scheduler.remove_schedule(schedule_id)

    if not success:
        raise HTTPException(status_code=404, detail="定时任务不存在")

    return {"message": "定时任务已删除", "schedule_id": schedule_id}


@app.delete("/tasks")
async def clear_all_tasks():
    """
    清空所有已完成的任务记录
    """
    global task_status

    completed_tasks = [
        task_id for task_id, info in task_status.items()
        if info.get("status") in ["completed", "failed"]
    ]

    deleted_count = 0
    for task_id in completed_tasks:
        info = task_status[task_id]
        for file_key in ["json_file", "csv_file"]:
            file_path = info.get(file_key)
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"删除文件: {file_path}")
        del task_status[task_id]
        deleted_count += 1

    logger.info(f"清空了 {deleted_count} 个任务记录")

    return {
        "message": f"已清空 {deleted_count} 个已完成/失败的任务记录",
        "deleted_count": deleted_count,
        "remaining_count": len(task_status)
    }


def main():
    """启动API服务"""
    import sys
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except:
            pass
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
