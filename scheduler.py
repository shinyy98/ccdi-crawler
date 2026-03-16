"""
定时任务调度模块 - 支持自动定时执行和任务管理
"""
import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore
import logging
from typing import Dict, List, Optional, Callable
import json
import os

logger = logging.getLogger(__name__)


class TaskScheduler:
    """任务调度器 - 管理定时爬虫任务"""

    def __init__(self, crawl_callback: Callable):
        """
        初始化调度器
        :param crawl_callback: 爬虫执行回调函数
        """
        self.crawl_callback = crawl_callback
        self.scheduler = AsyncIOScheduler(
            jobstores={'default': MemoryJobStore()},
            timezone='Asia/Shanghai'  # 中国时区
        )
        self.scheduler.start()
        self.scheduled_jobs: Dict[str, dict] = {}  # 存储任务配置
        self.job_history: List[dict] = []  # 执行历史
        self._load_schedules()

    def _load_schedules(self):
        """从文件加载定时任务配置"""
        schedule_file = 'schedules.json'
        if os.path.exists(schedule_file):
            try:
                with open(schedule_file, 'r', encoding='utf-8') as f:
                    schedules = json.load(f)
                    for schedule in schedules:
                        self.add_schedule(
                            name=schedule['name'],
                            cron_expression=schedule['cron'],
                            crawl_config=schedule['config'],
                            enabled=schedule.get('enabled', True)
                        )
                logger.info(f"已加载 {len(schedules)} 个定时任务")
            except Exception as e:
                logger.error(f"加载定时任务配置失败: {e}")

    def _save_schedules(self):
        """保存定时任务配置到文件"""
        schedule_file = 'schedules.json'
        try:
            schedules = []
            for job_id, config in self.scheduled_jobs.items():
                schedules.append({
                    'name': config['name'],
                    'cron': config['cron'],
                    'config': config['config'],
                    'enabled': config.get('enabled', True)
                })
            with open(schedule_file, 'w', encoding='utf-8') as f:
                json.dump(schedules, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存定时任务配置失败: {e}")

    def add_schedule(self, name: str, cron_expression: str,
                     crawl_config: dict, enabled: bool = True) -> str:
        """
        添加定时任务
        :param name: 任务名称
        :param cron_expression: Cron表达式 (如 "0 9 * * *" 表示每天9点)
        :param crawl_config: 爬虫配置
        :param enabled: 是否启用
        :return: 任务ID
        """
        job_id = f"schedule_{name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        if enabled:
            try:
                # 解析cron表达式
                minute, hour, day, month, day_of_week = cron_expression.split()
                trigger = CronTrigger(
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=day_of_week,
                    timezone='Asia/Shanghai'
                )

                # 添加任务
                job = self.scheduler.add_job(
                    func=self._execute_scheduled_task,
                    trigger=trigger,
                    id=job_id,
                    args=[name, crawl_config],
                    replace_existing=True
                )

                self.scheduled_jobs[job_id] = {
                    'id': job_id,
                    'name': name,
                    'cron': cron_expression,
                    'config': crawl_config,
                    'enabled': enabled,
                    'next_run': job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.next_run_time else None,
                    'created_at': datetime.now().isoformat()
                }

                self._save_schedules()
                logger.info(f"添加定时任务成功: {name} ({cron_expression})")
                return job_id

            except Exception as e:
                logger.error(f"添加定时任务失败: {e}")
                raise
        else:
            # 仅保存配置，不添加执行
            self.scheduled_jobs[job_id] = {
                'id': job_id,
                'name': name,
                'cron': cron_expression,
                'config': crawl_config,
                'enabled': enabled,
                'next_run': None,
                'created_at': datetime.now().isoformat()
            }
            self._save_schedules()
            return job_id

    async def _execute_scheduled_task(self, name: str, config: dict):
        """执行定时任务"""
        logger.info(f"开始执行定时任务: {name}")
        start_time = datetime.now()

        try:
            # 调用爬虫回调
            result = await self.crawl_callback(config)

            # 记录执行历史
            self.job_history.append({
                'name': name,
                'start_time': start_time.isoformat(),
                'end_time': datetime.now().isoformat(),
                'status': 'success',
                'result': result
            })

            # 只保留最近100条历史
            self.job_history = self.job_history[-100:]

            logger.info(f"定时任务执行成功: {name}")

        except Exception as e:
            logger.error(f"定时任务执行失败: {name}, 错误: {e}")
            self.job_history.append({
                'name': name,
                'start_time': start_time.isoformat(),
                'end_time': datetime.now().isoformat(),
                'status': 'failed',
                'error': str(e)
            })

    def remove_schedule(self, job_id: str) -> bool:
        """删除定时任务"""
        try:
            if job_id in self.scheduled_jobs:
                self.scheduler.remove_job(job_id)
                del self.scheduled_jobs[job_id]
                self._save_schedules()
                logger.info(f"删除定时任务: {job_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"删除定时任务失败: {e}")
            return False

    def toggle_schedule(self, job_id: str, enabled: bool) -> bool:
        """启用/禁用定时任务"""
        try:
            if job_id not in self.scheduled_jobs:
                return False

            config = self.scheduled_jobs[job_id]

            if enabled:
                # 重新添加任务
                minute, hour, day, month, day_of_week = config['cron'].split()
                trigger = CronTrigger(
                    minute=minute, hour=hour, day=day,
                    month=month, day_of_week=day_of_week,
                    timezone='Asia/Shanghai'
                )
                job = self.scheduler.add_job(
                    func=self._execute_scheduled_task,
                    trigger=trigger,
                    id=job_id,
                    args=[config['name'], config['config']],
                    replace_existing=True
                )
                config['next_run'] = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S')
            else:
                # 移除任务
                try:
                    self.scheduler.remove_job(job_id)
                except:
                    pass
                config['next_run'] = None

            config['enabled'] = enabled
            self._save_schedules()
            return True

        except Exception as e:
            logger.error(f"切换定时任务状态失败: {e}")
            return False

    def update_schedule(self, job_id: str, name: str = None, cron_expression: str = None,
                       crawl_config: dict = None) -> bool:
        """更新定时任务"""
        try:
            if job_id not in self.scheduled_jobs:
                return False

            config = self.scheduled_jobs[job_id]

            # 更新字段
            if name:
                config['name'] = name
            if crawl_config:
                config['config'] = crawl_config

            # 如果cron变化且任务启用，需要重新调度
            if cron_expression and cron_expression != config['cron']:
                config['cron'] = cron_expression

                # 如果任务当前启用，重新调度
                if config.get('enabled', True):
                    try:
                        self.scheduler.remove_job(job_id)
                    except:
                        pass

                    minute, hour, day, month, day_of_week = cron_expression.split()
                    trigger = CronTrigger(
                        minute=minute, hour=hour, day=day,
                        month=month, day_of_week=day_of_week,
                        timezone='Asia/Shanghai'
                    )
                    job = self.scheduler.add_job(
                        func=self._execute_scheduled_task,
                        trigger=trigger,
                        id=job_id,
                        args=[config['name'], config['config']],
                        replace_existing=True
                    )
                    config['next_run'] = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S')

            config['updated_at'] = datetime.now().isoformat()
            self._save_schedules()
            logger.info(f"更新定时任务: {job_id}")
            return True

        except Exception as e:
            logger.error(f"更新定时任务失败: {e}")
            return False

    def clear_history(self) -> bool:
        """清空执行历史"""
        try:
            self.job_history = []
            logger.info("清空执行历史")
            return True
        except Exception as e:
            logger.error(f"清空执行历史失败: {e}")
            return False

    def get_schedule_by_id(self, job_id: str) -> Optional[dict]:
        """获取单个定时任务详情"""
        return self.scheduled_jobs.get(job_id)

    def get_schedules(self) -> List[dict]:
        """获取所有定时任务"""
        schedules = []
        for job_id, config in self.scheduled_jobs.items():
            job_info = config.copy()
            # 更新下次执行时间
            try:
                job = self.scheduler.get_job(job_id)
                if job and job.next_run_time:
                    job_info['next_run'] = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S')
            except:
                pass
            schedules.append(job_info)
        return sorted(schedules, key=lambda x: x['created_at'], reverse=True)

    def get_history(self, limit: int = 20) -> List[dict]:
        """获取执行历史"""
        return sorted(self.job_history, key=lambda x: x['start_time'], reverse=True)[:limit]

    def shutdown(self):
        """关闭调度器"""
        self.scheduler.shutdown()


# 常用Cron表达式示例
CRON_EXAMPLES = {
    '每天9点': '0 9 * * *',
    '每天9点和18点': '0 9,18 * * *',
    '每小时': '0 * * * *',
    '每2小时': '0 */2 * * *',
    '每周一9点': '0 9 * * 1',
    '每月1号9点': '0 9 1 * *',
}
