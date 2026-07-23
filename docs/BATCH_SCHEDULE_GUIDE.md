# 배치 작업 스케줄링 가이드

## 개요

기후 리스크 분석을 위한 H (Hazard Score)와 P(H) (Probability) 배치 작업의 스케줄링 가이드입니다.

### 배치 작업 일정

| 작업 | 파일 | 실행 시간 | 설명 |
|------|------|-----------|------|
| P(H) 배치 | `probability_timeseries_batch.py` | 매년 1월 1일 02:00 | 확률 P(H) 시계열 계산 |
| H 배치 | `hazard_timeseries_batch.py` | 매년 1월 1일 04:00 | Hazard Score 시계열 계산 |

## 방법 1: Python APScheduler 사용 (권장)

### 설치

```bash
pip install apscheduler
```

### 스케줄러 실행

```bash
# 포그라운드 실행
python -m modelops.batch.batch_scheduler

# 백그라운드 실행 (Linux/Mac)
nohup python -m modelops.batch.batch_scheduler > scheduler.log 2>&1 &

# 프로세스 확인
ps aux | grep batch_scheduler

# 프로세스 종료
kill <PID>
```

### 스케줄러 특징

- **자동 재시작**: 실패 시 로그 기록 후 다음 스케줄 대기
- **로그 파일**: `batch_scheduler.log`에 모든 실행 기록 저장
- **독립 실행**: 각 배치 작업이 독립적으로 실행됨

## 방법 2: Linux Cron 사용

### Crontab 설정

```bash
# Crontab 편집
crontab -e

# 다음 내용 추가
# P(H) 배치: 매년 1월 1일 02:00
0 2 1 1 * cd /path/to/modelops && /usr/bin/python3 -m modelops.batch.probability_timeseries_batch >> /var/log/probability_batch.log 2>&1

# H 배치: 매년 1월 1일 04:00
0 4 1 1 * cd /path/to/modelops && /usr/bin/python3 -m modelops.batch.hazard_timeseries_batch >> /var/log/hazard_batch.log 2>&1
```

### Cron 표현식 설명

```
분 시 일 월 요일 명령어
0  2  1  1  *   (매년 1월 1일 02:00)
0  4  1  1  *   (매년 1월 1일 04:00)
```

### Crontab 확인

```bash
# 현재 설정된 크론 작업 확인
crontab -l

# 크론 로그 확인 (Ubuntu/Debian)
grep CRON /var/log/syslog
```

## 방법 3: Windows Task Scheduler 사용

### GUI를 통한 설정

1. **작업 스케줄러** 열기
   - 시작 → "작업 스케줄러" 검색

2. **P(H) 배치 작업 생성**
   - 작업 만들기 → 기본 작업 만들기
   - 이름: `P(H) Timeseries Batch`
   - 트리거: 매년 1월 1일 02:00
   - 작업: 프로그램 시작
   - 프로그램: `python.exe`
   - 인수: `-m modelops.batch.probability_timeseries_batch`
   - 시작 위치: `C:\Users\SKAX\Desktop\modelops`

3. **H 배치 작업 생성**
   - 작업 만들기 → 기본 작업 만들기
   - 이름: `Hazard Timeseries Batch`
   - 트리거: 매년 1월 1일 04:00
   - 작업: 프로그램 시작
   - 프로그램: `python.exe`
   - 인수: `-m modelops.batch.hazard_timeseries_batch`
   - 시작 위치: `C:\Users\SKAX\Desktop\modelops`

### PowerShell을 통한 설정

```powershell
# P(H) 배치 작업 생성
$action_p = New-ScheduledTaskAction -Execute "python.exe" `
    -Argument "-m modelops.batch.probability_timeseries_batch" `
    -WorkingDirectory "C:\Users\SKAX\Desktop\modelops"

$trigger_p = New-ScheduledTaskTrigger -Daily -At 2:00AM -DaysInterval 365

Register-ScheduledTask -TaskName "P(H) Timeseries Batch" `
    -Action $action_p -Trigger $trigger_p -Description "Annual P(H) calculation"

# H 배치 작업 생성
$action_h = New-ScheduledTaskAction -Execute "python.exe" `
    -Argument "-m modelops.batch.hazard_timeseries_batch" `
    -WorkingDirectory "C:\Users\SKAX\Desktop\modelops"

$trigger_h = New-ScheduledTaskTrigger -Daily -At 4:00AM -DaysInterval 365

Register-ScheduledTask -TaskName "Hazard Timeseries Batch" `
    -Action $action_h -Trigger $trigger_h -Description "Annual Hazard Score calculation"
```

## 수동 실행 방법

### 전체 배치 실행 (테스트용)

```bash
# P(H) 배치 (전체)
python -m modelops.batch.probability_timeseries_batch

# H 배치 (전체)
python -m modelops.batch.hazard_timeseries_batch
```

### 특정 조건으로 실행

```bash
# 특정 시나리오만 (SSP245)
python -m modelops.batch.probability_timeseries_batch --scenario SSP245

# 특정 연도 범위 (2021-2030)
python -m modelops.batch.hazard_timeseries_batch --start-year 2021 --end-year 2030

# 워커 수 조정 (8개 병렬 프로세스)
python -m modelops.batch.probability_timeseries_batch --workers 8

# 조합 예시
python -m modelops.batch.hazard_timeseries_batch \
    --scenario SSP245 \
    --start-year 2021 \
    --end-year 2030 \
    --batch-size 50 \
    --workers 6
```

## CLI 옵션

| 옵션 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `--scenario` | str | 전체 | 단일 시나리오 (SSP126, SSP245, SSP370, SSP585) |
| `--start-year` | int | 2021 | 시작 연도 |
| `--end-year` | int | 2100 | 종료 연도 |
| `--batch-size` | int | 100 | DB 저장 배치 크기 |
| `--workers` | int | 4 | 병렬 워커 프로세스 수 |

## 로그 확인

### APScheduler 로그

```bash
# 실시간 로그 확인
tail -f batch_scheduler.log

# 최근 100줄 확인
tail -n 100 batch_scheduler.log
```

### 배치 실행 로그

각 배치 실행 시 표준 출력으로 다음 정보 제공:
- 전체 작업 수
- 완료/실패 건수
- 성공률
- 실행 시간
- 평균 처리 속도

## 모니터링 및 알림

### 배치 실행 상태 확인

```python
# DB에서 최근 배치 실행 결과 조회
SELECT scenario, target_year, COUNT(*) as total_records,
       AVG(hazard_score) as avg_hazard_score
FROM hazard_results
WHERE created_at > NOW() - INTERVAL '1 day'
GROUP BY scenario, target_year;
```

### 실패 알림 설정 (선택사항)

스케줄러에서 실패 시 이메일/Slack 알림을 추가하려면:

1. `batch_scheduler.py`의 각 job 함수에 예외 처리 추가
2. SMTP/Slack API를 사용한 알림 전송 구현

예시:
```python
def hazard_batch_job():
    try:
        run_hazard_batch(...)
        logger.info("SUCCESS")
    except Exception as e:
        logger.error(f"FAILED: {e}")
        send_slack_notification(f"Hazard batch failed: {e}")
        raise
```

## 성능 최적화

### 워커 수 조정 지침

- **CPU 코어 수**: 시스템 코어 수보다 1-2개 적게 설정
- **메모리**: 각 워커당 약 2GB 메모리 필요
- **권장 설정**:
  - 4 코어 시스템: `--workers 2-3`
  - 8 코어 시스템: `--workers 6-7`
  - 16 코어 시스템: `--workers 12-14`

### 배치 크기 조정

- **작은 배치 (50-100)**: DB 부하 분산, 메모리 절약
- **큰 배치 (200-500)**: DB 접속 횟수 감소, 처리 속도 향상

## 트러블슈팅

### 문제: 스케줄러가 시작되지 않음

**해결방법**:
```bash
# APScheduler 설치 확인
pip show apscheduler

# 재설치
pip uninstall apscheduler
pip install apscheduler
```

### 문제: 배치 실행 중 메모리 부족

**해결방법**:
- `--workers` 수를 줄임 (예: 4 → 2)
- `--batch-size`를 줄임 (예: 100 → 50)

### 문제: DB 연결 실패

**해결방법**:
- DB 연결 정보 확인 (`database/connection.py`)
- DB 서버 상태 확인
- 방화벽/네트워크 설정 확인

## 백업 및 복구

### 배치 실행 전 DB 백업 (권장)

```bash
# PostgreSQL 백업 예시
pg_dump -h localhost -U username -d dbname > backup_$(date +%Y%m%d).sql

# MySQL 백업 예시
mysqldump -u username -p dbname > backup_$(date +%Y%m%d).sql
```

### 실패한 배치 재실행

```bash
# 특정 시나리오/연도만 재실행
python -m modelops.batch.hazard_timeseries_batch \
    --scenario SSP245 \
    --start-year 2050 \
    --end-year 2050
```

## 참고 사항

1. **실행 순서**: P(H) 배치가 H 배치보다 먼저 실행되도록 2시간 간격 설정
2. **연간 실행**: 1년에 한 번만 실행되므로 테스트는 수동 실행으로 진행
3. **병렬 처리**: Windows 환경에서는 `if __name__ == "__main__"` 필수
4. **로그 보관**: 로그 파일이 계속 증가하므로 주기적으로 정리 필요

## 연락처

문제 발생 시 시스템 관리자에게 문의하세요.
