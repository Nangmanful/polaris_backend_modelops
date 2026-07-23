"""
Log Writer
사업장별 계산 진행 로그 파일 작성 모듈
"""

from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class LogWriter:
    """로그 파일 작성 유틸리티"""

    def __init__(self, base_log_dir: str = "logs"):
        """
        Args:
            base_log_dir: 기본 로그 디렉토리 경로 (프로젝트 루트 기준)
        """
        # 프로젝트 루트에서 logs 폴더 생성
        # modelops 상위 폴더가 프로젝트 루트
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent  # backend_aiops
        self.base_log_dir = project_root / base_log_dir

    def _ensure_site_log_dir(self, site_id: str) -> Path:
        """
        사업장별 로그 디렉토리 생성

        Args:
            site_id: 사업장 ID

        Returns:
            사업장 로그 디렉토리 경로
        """
        site_log_dir = self.base_log_dir / site_id
        site_log_dir.mkdir(parents=True, exist_ok=True)
        return site_log_dir

    def write_year_completed_log(
        self,
        site_id: str,
        year: int,
        scenario: str,
        status: str = "success",
        error_message: Optional[str] = None,
        task_type: str = "calculate",
    ):
        """
        1년치 계산 완료 로그 작성

        Args:
            site_id: 사업장 ID
            year: 계산 완료된 연도
            scenario: 시나리오 (예: SSP126, SSP245)
            status: 상태 (success/failed)
            error_message: 실패 시 에러 메시지
            task_type: 작업 타입 (calculate/recommend)
        """
        try:
            site_log_dir = self._ensure_site_log_dir(site_id)

            # 로그 파일명: {year}_{scenario}_{status}.txt
            log_filename = f"{year}_{scenario}_{status}.txt"
            log_filepath = site_log_dir / log_filename

            # 로그 내용 작성
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_content = [
                f"Task Type: {task_type}",
                f"Site ID: {site_id}",
                f"Year: {year}",
                f"Scenario: {scenario}",
                f"Status: {status}",
                f"Timestamp: {timestamp}",
            ]

            if error_message:
                log_content.append(f"Error: {error_message}")

            # 파일에 쓰기
            with open(log_filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(log_content))

            logger.debug(f"로그 작성 완료: {log_filepath}")

        except Exception as e:
            logger.error(
                f"로그 파일 작성 실패 (site_id={site_id}, year={year}): {e}", exc_info=True
            )

    def write_site_summary_log(
        self,
        site_id: str,
        total_years: int,
        completed_years: int,
        failed_years: int,
        task_type: str = "calculate",
        scenarios: Optional[list] = None,
    ):
        """
        사업장 전체 계산 요약 로그 작성

        Args:
            site_id: 사업장 ID
            total_years: 총 연도 개수
            completed_years: 완료된 연도 개수
            failed_years: 실패한 연도 개수
            task_type: 작업 타입
            scenarios: 처리된 시나리오 목록
        """
        try:
            site_log_dir = self._ensure_site_log_dir(site_id)

            # 요약 파일명: summary.txt
            summary_filepath = site_log_dir / "summary.txt"

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            summary_content = [
                f"=== Site Calculation Summary ===",
                f"Task Type: {task_type}",
                f"Site ID: {site_id}",
                f"Total Years: {total_years}",
                f"Completed Years: {completed_years}",
                f"Failed Years: {failed_years}",
                (
                    f"Success Rate: {completed_years / total_years * 100:.1f}%"
                    if total_years > 0
                    else "N/A"
                ),
                f"Completed At: {timestamp}",
            ]

            if scenarios:
                summary_content.append(f"Scenarios: {', '.join(scenarios)}")

            with open(summary_filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(summary_content))

            logger.info(f"요약 로그 작성 완료: {summary_filepath}")

        except Exception as e:
            logger.error(f"요약 로그 작성 실패 (site_id={site_id}): {e}", exc_info=True)

    def write_task_start_log(
        self, site_id: str, task_type: str, total_years: int, scenarios: Optional[list] = None
    ):
        """
        사업장 계산 시작 로그 작성

        Args:
            site_id: 사업장 ID
            task_type: 작업 타입
            total_years: 총 연도 개수
            scenarios: 처리할 시나리오 목록
        """
        try:
            site_log_dir = self._ensure_site_log_dir(site_id)

            start_filepath = site_log_dir / "task_start.txt"

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            start_content = [
                f"=== Task Started ===",
                f"Task Type: {task_type}",
                f"Site ID: {site_id}",
                f"Total Years: {total_years}",
                f"Started At: {timestamp}",
            ]

            if scenarios:
                start_content.append(f"Scenarios: {', '.join(scenarios)}")

            with open(start_filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(start_content))

            logger.debug(f"시작 로그 작성 완료: {start_filepath}")

        except Exception as e:
            logger.error(f"시작 로그 작성 실패 (site_id={site_id}): {e}", exc_info=True)


# 싱글톤 인스턴스
log_writer = LogWriter()
