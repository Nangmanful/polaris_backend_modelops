"""
Background Task Manager
백그라운드 작업 관리 및 상태 추적 모듈
"""

import threading
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum


class TaskStatus(str, Enum):
    """작업 상태"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BackgroundTaskManager:
    """백그라운드 작업 관리자 (싱글톤)"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._initialized = True

    def create_task(
        self,
        task_id: str,
        task_type: str,
        total_sites: int,
        total_years: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        새로운 작업 생성

        Args:
            task_id: 작업 ID
            task_type: 작업 타입 ('calculate' 또는 'recommend')
            total_sites: 총 사업장 개수
            total_years: 총 연도 개수
            metadata: 추가 메타데이터

        Returns:
            생성된 작업 정보
        """
        with self._lock:
            task_info = {
                "task_id": task_id,
                "task_type": task_type,
                "status": TaskStatus.PENDING,
                "total_sites": total_sites,
                "total_years": total_years,
                "completed_sites": 0,
                "failed_sites": 0,
                "current_progress": {},  # {site_id: {completed_years: int, failed_years: int}}
                "created_at": datetime.now(),
                "started_at": None,
                "completed_at": None,
                "error_message": None,
                "metadata": metadata or {},
            }
            self._tasks[task_id] = task_info
            return task_info

    def start_task(self, task_id: str):
        """작업 시작"""
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id]["status"] = TaskStatus.RUNNING
                self._tasks[task_id]["started_at"] = datetime.now()

    def update_site_progress(
        self, task_id: str, site_id: str, completed_years: int = 0, failed_years: int = 0
    ):
        """사업장별 진행 상황 업데이트"""
        with self._lock:
            if task_id in self._tasks:
                progress = self._tasks[task_id]["current_progress"]
                if site_id not in progress:
                    progress[site_id] = {"completed_years": 0, "failed_years": 0}

                progress[site_id]["completed_years"] += completed_years
                progress[site_id]["failed_years"] += failed_years

    def complete_site(self, task_id: str, site_id: str, success: bool = True):
        """사업장 계산 완료"""
        with self._lock:
            if task_id in self._tasks:
                if success:
                    self._tasks[task_id]["completed_sites"] += 1
                else:
                    self._tasks[task_id]["failed_sites"] += 1

    def complete_task(self, task_id: str, error_message: Optional[str] = None):
        """작업 완료"""
        with self._lock:
            if task_id in self._tasks:
                if error_message:
                    self._tasks[task_id]["status"] = TaskStatus.FAILED
                    self._tasks[task_id]["error_message"] = error_message
                else:
                    self._tasks[task_id]["status"] = TaskStatus.COMPLETED
                self._tasks[task_id]["completed_at"] = datetime.now()

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """작업 정보 조회"""
        with self._lock:
            return self._tasks.get(task_id)

    def get_all_tasks(self) -> Dict[str, Dict[str, Any]]:
        """모든 작업 정보 조회"""
        with self._lock:
            return self._tasks.copy()

    def delete_task(self, task_id: str) -> bool:
        """작업 삭제"""
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                return True
            return False


# 싱글톤 인스턴스
task_manager = BackgroundTaskManager()
