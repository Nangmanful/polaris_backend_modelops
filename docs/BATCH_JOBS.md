# 배치 작업 목록 및 스케줄

> SKALA Physical Risk AI ModelOps 플랫폼의 모든 배치 작업 정리

최종 수정일: 2025-12-19
버전: v1.0

---

## 📋 목차

- [배치 작업 개요](#배치-작업-개요)
- [자동 스케줄 배치](#자동-스케줄-배치)
- [On-Demand API 배치](#on-demand-api-배치)
- [배치 작업 모니터링](#배치-작업-모니터링)

---

## 배치 작업 개요

본 시스템에서 운영 중인 배치 작업은 크게 두 가지로 분류됩니다:

1. **자동 스케줄 배치**: 정기적으로 자동 실행되는 배치 (APScheduler, Cron)
2. **On-Demand API 배치**: 사용자 요청 시 실행되는 백그라운드 배치 (FastAPI BackgroundTasks)

---

## 자동 스케줄 배치

### 배치 작업 목록

| 배치 작업명 | 실행 주기 | 실행 시간 | 담당 서비스 | 설명 |
|------------|----------|----------|------------|------|
| **Probability 계산** | 매년 1월 1일 | 새벽 2시 (02:00 KST) | ModelOps | 451,351개 그리드 × 9개 재해 유형의 확률 계산 (약 12-15시간 소요) |
| **Hazard Score 계산** | 매년 1월 1일 | 새벽 4시 (04:00 KST) | ModelOps | Probability 계산 완료 후 자동 실행되는 위험도 점수 계산 |
| **재난안전데이터 ETL** | 매일 | 오전 9시 (09:00 KST) | ModelOps | 긴급재난문자 API 수집 및 DB 적재 (9종 재난 유형, 최근 5년 데이터) |
| **ESG Trends Agent** | 주 2회 | 월요일, 목요일 09:00 KST | ModelOps | 기후 관련 뉴스 수집 및 GPT-4o-mini 분석 후 Slack 알림 발송 |
| **사업장 리스크 계산** | On-Demand | API 요청 시 | ModelOps | N개 사업장 × 4개 시나리오 × 80개 연도 × 9개 리스크 타입의 E, V, AAL 계산 (병렬 처리, max_workers=8) |
| **사업장 이전 후보지 추천** | On-Demand | API 요청 시 | ModelOps | N개 사업장 × M개 후보지의 통합 리스크 평가 및 추천 (Early Callback 최적화, max_workers=8) |
| **서버 상태 보고** | 매일 | 오전 8시 (08:00 KST) | server-monitor | 전일 서버 리소스 사용 현황 이메일 리포트 생성 |
| **서버 리소스 모니터링** | 1분마다 | 연속 실행 | server-monitor | CPU/Memory/Disk 사용률 80% 초과 시 이메일 알림 (6시간마다 재알림) |

---

## 1. Probability 계산 배치

### 기본 정보

- **배치 ID**: `probability_batch`
- **실행 주기**: 매년 1월 1일 새벽 2시
- **담당 서비스**: ModelOps
- **소요 시간**: 약 12-15시간

### 작업 내용

451,351개 그리드 포인트에 대해 9개 재해 유형의 발생 확률(P(H))과 AAL(연간 평균 손실률)을 계산합니다.

**처리 대상**:
- **그리드 포인트**: 451,351개
- **재해 유형**: 9개 (극한 고온, 극한 한파, 가뭄, 하천홍수, 도시홍수, 해수면상승, 태풍, 산불, 수자원 스트레스)
- **총 계산 수**: 451,351 × 9 = 4,062,159개

**데이터 소스**:
- Datawarehouse (PostgreSQL 5433 포트)
- 기후 데이터 (NetCDF)
- 시나리오: SSP126, SSP245, SSP370, SSP585

**저장 위치**:
- Application DB (PostgreSQL 5432 포트)
- `probability_results` 테이블

### 설정 방법

`.env` 파일:

```bash
PROBABILITY_SCHEDULE_MONTH=1
PROBABILITY_SCHEDULE_DAY=1
PROBABILITY_SCHEDULE_HOUR=2
PROBABILITY_SCHEDULE_MINUTE=0

PARALLEL_WORKERS=4
BATCH_SIZE=1000
```

---

## 2. Hazard Score 계산 배치

### 기본 정보

- **배치 ID**: `hazard_batch`
- **실행 주기**: 매년 1월 1일 새벽 4시
- **담당 서비스**: ModelOps
- **선행 조건**: Probability 계산 완료 후 실행

### 작업 내용

Probability 계산 완료 후 자동 실행되는 위험도 점수 계산 배치입니다.

**처리 대상**:
- Probability 계산 결과 기반
- 위험도 등급 분류 (MINIMAL, LOW, MEDIUM, HIGH, CRITICAL)

**위험도 등급**:
- MINIMAL: 0-20
- LOW: 20-40
- MEDIUM: 40-60
- HIGH: 60-80
- CRITICAL: 80-100

**저장 위치**:
- Application DB
- `hazard_results` 테이블

### 설정 방법

`.env` 파일:

```bash
HAZARD_SCHEDULE_MONTH=1
HAZARD_SCHEDULE_DAY=1
HAZARD_SCHEDULE_HOUR=4
HAZARD_SCHEDULE_MINUTE=0
```

---

## 3. ESG Trends Agent 배치

### 기본 정보

- **배치 ID**: `esg_trends_agent`
- **실행 주기**: 주 2회 (월요일, 목요일)
- **실행 시간**: 오전 9시 (09:00 KST)
- **담당 서비스**: ModelOps
- **실행 방식**: Cron

### 작업 내용

기후 관련 뉴스를 수집하고 GPT-4o-mini로 분석하여 Slack 알림을 발송합니다.

**데이터 수집**:
- 기상청 단기예보 API (날씨 + 물리적 리스크)
- esgeconomy.com 크롤링 (국내 ESG 뉴스)
- KOTRA ESG 동향뉴스 API (글로벌 ESG)
- Fallback: Tavily/DuckDuckGo 검색

**LLM 분석**:
- ESG 키워드 필터링 (E, S, G 카테고리)
- GPT-4o-mini 기반 트렌드 분석
- 급변 이슈 탐지 및 권고사항 생성
- 데이터 품질 검증 (최대 2회 재시도)

**리포트 생성**:
- 8개 섹션 구조화 리포트
- Slack 자동 발송 (페이지네이션)
- 마크다운 형식 메시지

### 설정 방법

Cron 설정:

```bash
# 월요일, 목요일 오전 9시 실행
0 9 * * 1,4 cd /path/to/backend_aiops && ./system_setting/run.sh >> logs/cron.log 2>&1
```

`.env` 파일:

```bash
# ESG Trends Agent - APIs
KMA_API_KEY=your_kma_api_key
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o-mini
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
KOTRA_API_KEY=your_kotra_api_key
TAVILY_API_KEY=your_tavily_api_key

# ESG Trends Agent - Settings
WEATHER_LOCATIONS=서울,성남,대전
SLACK_CHANNEL=auto
ESG_LOG_LEVEL=INFO
```

---

## 4. 서버 상태 보고 배치

### 기본 정보

- **배치 ID**: `server_status_report`
- **실행 주기**: 매일
- **실행 시간**: 오전 8시 (08:00 KST)
- **담당 서비스**: server-monitor

### 작업 내용

전일 서버 리소스 사용 현황을 이메일 리포트로 생성합니다.

**모니터링 항목**:
- CPU 사용률
- Memory 사용률
- Disk 사용률
- Network I/O

---

## 5. 서버 리소스 모니터링 배치

### 기본 정보

- **배치 ID**: `server_resource_monitor`
- **실행 주기**: 1분마다
- **실행 시간**: 연속 실행
- **담당 서비스**: server-monitor

### 작업 내용

CPU/Memory/Disk 사용률이 80%를 초과하면 이메일 알림을 발송합니다 (6시간마다 재알림).

**알림 조건**:
- CPU 사용률 > 80%
- Memory 사용률 > 80%
- Disk 사용률 > 80%

**재알림 주기**: 6시간

---

## On-Demand API 배치

사용자 요청 시 백그라운드에서 실행되는 배치 작업입니다.

### 1. 사업장 리스크 계산 배치

#### API 엔드포인트

```
POST /api/site-assessment/calculate
```

#### 작업 내용

여러 사업장에 대한 종합 리스크(E, V, AAL)를 계산합니다.

**처리 흐름**:

```
API 요청 (N개 사업장)
↓
백그라운드 작업 생성 (task_id)
↓
병렬 처리 (ThreadPoolExecutor, max_workers=8)
├─ 사업장 1 → 4개 시나리오 × 80개 연도 (2021-2100) = 320개 계산
├─ 사업장 2 → 320개 계산
└─ 사업장 N → 320개 계산
↓
각 계산마다 9개 리스크 타입 평가
├─ H (Hazard) - DB 조회
├─ E (Exposure) - 건물 정보 기반
├─ V (Vulnerability) - 건물 구조 기반
└─ AAL (Annual Average Loss) - P × DR 계산
↓
Application DB 저장 (evaal_results 테이블)
↓
진행률 실시간 업데이트
```

**병렬 처리 전략**:
- **최대 워커 수**: 8개
- **시나리오**: SSP126, SSP245, SSP370, SSP585 (4개)
- **연도 범위**: 2021-2100 (80년)
- **리스크 타입**: 9개
- **총 계산 수**: `사업장 수 × 4 × 80 × 9`

**실시간 로깅**:

```
logs/task_[task_id]/
├── [site_id]_start.log          # 시작 로그
├── [site_id]_[year]_[scenario].log  # 연도별 완료 로그
└── [site_id]_summary.log        # 요약 로그
```

**진행률 조회**:

```
GET /api/site-assessment/task-status/{task_id}
```

**응답 예시**:

```json
{
  "task_id": "abc-123-def-456",
  "task_type": "calculate",
  "status": "running",
  "total_sites": 5,
  "completed_sites": 2,
  "failed_sites": 0,
  "total_years": 320,
  "progress_percentage": 40.0,
  "current_progress": {
    "site_1": {
      "completed_years": 320,
      "failed_years": 0
    },
    "site_2": {
      "completed_years": 320,
      "failed_years": 0
    },
    "site_3": {
      "completed_years": 128,
      "failed_years": 0
    }
  }
}
```

---

### 2. 사업장 이전 후보지 추천 배치

#### API 엔드포인트

```
POST /api/site-assessment/recommend-locations
```

#### 작업 내용

사업장 이전을 위한 최적 후보지를 평가하고 추천합니다.

**처리 흐름**:

```
API 요청
├─ N개 사업장 정보
├─ M개 후보지 좌표 (또는 고정 10개 위치 사용)
├─ 검색 기준 (시나리오, 목표연도)
└─ 건물/자산 정보
↓
Early Callback 체크
├─ DB에 후보지 데이터 90% 이상 존재?
│   ├─ YES → 즉시 FastAPI 서버에 콜백 호출
│   └─ NO → 계산 진행
↓
병렬 처리 (ThreadPoolExecutor, max_workers=8)
├─ 사업장 1 → M개 후보지 평가
├─ 사업장 2 → M개 후보지 평가
└─ 사업장 N → M개 후보지 평가
↓
각 후보지마다
├─ 이미 DB에 존재? → 건너뛰기
├─ E, V, AAL 온디맨드 계산
├─ 통합 리스크 점수 계산 (H × E × V / 10000)
└─ candidate_sites 테이블에 저장
    ├─ latitude, longitude
    ├─ risk_score (0-100)
    ├─ total_aal
    ├─ aal_by_risk (9개 리스크별)
    └─ risks (9개 리스크별 점수)
↓
계산 완료 후 콜백 호출 (Early Callback 미호출 시)
↓
FastAPI 서버에 완료 알림
```

**병렬 처리 전략**:
- **최대 워커 수**: 8개
- **후보지 수**: 사용자 제공 또는 고정 10개 위치
- **시나리오**: 단일 (기본 SSP245)
- **목표연도**: 단일 (기본 2040)
- **리스크 타입**: 9개
- **총 계산 수**: `사업장 수 × 후보지 수 × 9`

**Early Callback 최적화**:
- DB에 후보지 데이터가 90% 이상 존재하면 즉시 콜백 호출
- 불필요한 재계산 방지
- 프론트엔드 응답 시간 단축

**고정 후보지 위치** (LOCATION_MAP):

```python
# 10개 고정 후보지 좌표
[
  {"lat": 37.5665, "lng": 126.9780},  # 서울
  {"lat": 35.1796, "lng": 129.0756},  # 부산
  {"lat": 37.4563, "lng": 126.7052},  # 인천
  {"lat": 35.8714, "lng": 128.6014},  # 대구
  {"lat": 36.3504, "lng": 127.3845},  # 대전
  {"lat": 35.5384, "lng": 129.3114},  # 울산
  {"lat": 35.1595, "lng": 126.8526},  # 광주
  {"lat": 36.6424, "lng": 127.4890},  # 세종
  {"lat": 37.2636, "lng": 127.0286},  # 수원
  {"lat": 33.4996, "lng": 126.5312}   # 제주
]
```

**콜백 URL**:

```
POST {FASTAPI_BASE_URL}/api/internal/callbacks/recommendation-complete?batchId={batch_id}
```

---

## 배치 작업 모니터링

### 작업 상태 조회

**모든 작업 조회**:

```bash
GET /api/site-assessment/tasks
```

**특정 작업 조회**:

```bash
GET /api/site-assessment/task-status/{task_id}
```

**스케줄된 작업 조회**:

```bash
GET /api/batch-trigger/scheduled-jobs
```

### 로그 확인

**ESG Trends Agent 로그**:

```bash
tail -f logs/cron.log
tail -f logs/esg_agent.log
```

**ModelOps 배치 로그**:

```bash
tail -f logs/task_[task_id]/[site_id]_start.log
tail -f logs/task_[task_id]/[site_id]_summary.log
```

**FastAPI 서버 로그**:

```bash
tail -f logs/modelops_server.log
```

### 작업 삭제

```bash
DELETE /api/site-assessment/task/{task_id}
```

---

## 배치 작업 성능 최적화

### 병렬 처리 워커 수 조정

`.env` 파일:

```bash
# ModelOps 배치
PARALLEL_WORKERS=4
BATCH_SIZE=1000

# On-Demand API (코드 내 MAX_WORKERS)
# site_assessment.py: MAX_WORKERS = 8
```

### DB 연결 풀 설정

```bash
# Datawarehouse
DW_POOL_SIZE=10
DW_MAX_OVERFLOW=20

# Application DB
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
```

---

## 문제 해결

### 배치 작업이 실행되지 않을 때

1. **APScheduler 상태 확인**:

```bash
GET /api/batch-trigger/scheduled-jobs
```

2. **Cron 작업 확인**:

```bash
crontab -l
tail -f logs/cron.log
```

3. **서버 로그 확인**:

```bash
tail -f logs/modelops_server.log
```

### 배치 작업이 실패할 때

1. **작업 상태 확인**:

```bash
GET /api/site-assessment/task-status/{task_id}
```

2. **로그 파일 확인**:

```bash
cat logs/task_[task_id]/[site_id]_summary.log
```

3. **DB 연결 확인**:

```bash
psql -h localhost -p 5432 -U skala_app_user -d skala_application
psql -h localhost -p 5433 -U skala_dw_user -d skala_datawarehouse
```

---

## 관련 문서

- [README.md](../README.md) - 프로젝트 전체 개요
- [BATCH_SCHEDULE_GUIDE.md](BATCH_SCHEDULE_GUIDE.md) - 배치 스케줄 상세 가이드
- [API_TEST_GUIDE.md](API_TEST_GUIDE.md) - API 테스트 가이드

---

**최종 수정**: 2025-12-19
**담당**: SKALA Physical Risk AI Team
