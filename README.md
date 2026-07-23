# Polaris ModelOps — 기후 물리 리스크 계산 엔진

기업 사업장의 **기후 물리 리스크(Physical Risk)** 를 정량 평가하는 배치·계산 엔진입니다.
H(Hazard) × E(Exposure) × V(Vulnerability) 프레임워크와 AAL(연평균 손실)을 기반으로,
9개 기후 리스크에 대해 SSP 시나리오별(2021–2100) 리스크 점수와 손실액을 계산합니다.

- **서버**: FastAPI (포트 **8001**)
- **배치**: APScheduler (연 1회 전국 격자 사전 계산 + 매일 재난문자 ETL)
- **DB**: PostgreSQL (Data Warehouse — 기후 격자·계산 결과)

---

## 목차

1. [3-레포 아키텍처에서의 역할](#3-레포-아키텍처에서의-역할)
2. [H×E×V·AAL 프레임워크](#hev--aal-프레임워크)
3. [프로젝트 구조](#프로젝트-구조)
4. [기술 스택](#기술-스택)
5. [배치 스케줄](#배치-스케줄)
6. [로컬 실행 방법](#로컬-실행-방법)
7. [환경변수](#환경변수)
8. [API 요약](#api-요약)
9. [배포 개요](#배포-개요)
10. [문서](#문서)

---

## 3-레포 아키텍처에서의 역할

Polaris 백엔드는 3개 레포로 구성되며, 이 레포는 **계산 엔진(ModelOps)** 입니다.

```
┌───────────────────┐   REST    ┌───────────────────┐   REST    ┌───────────────────────┐
│  Spring Boot 서버  │ ────────▶ │  FastAPI AI 서버   │ ────────▶ │  ModelOps (이 레포)     │
│  사용자/사업장 관리  │ ◀──────── │  LLM 보고서 생성    │ ◀──────── │  H·E·V·P(H)·AAL 계산   │
│                   │  콜백      │                   │  콜백      │  배치 + On-Demand API  │
└───────────────────┘           └───────────────────┘           └───────────┬───────────┘
                                                                            │
                                                                   PostgreSQL Data Warehouse
                                                                   (기후 격자 데이터·계산 결과)
```

- **Spring Boot**: 사용자·사업장(사이트) 관리, 프론트엔드 API 게이트웨이
- **FastAPI AI 서버**: 계산 결과를 입력으로 LLM 기반 TCFD 보고서 생성
- **ModelOps(이 레포)**: 기후 데이터 ETL → 리스크 계산(배치/온디맨드) → DB 저장 → 콜백

## H×E×V · AAL 프레임워크

| 단계 | 항목 | 내용 |
|------|------|------|
| 1 | **H (Hazard)** | 기후 시나리오(SSP126/245/370/585) 기반 재해 강도 점수. 배치로 전국 격자 사전 계산 후 DB 조회 |
| 2 | **P(H) (Probability)** | 재해 발생 확률 시계열 (2021–2100). 배치 사전 계산 |
| 3 | **E (Exposure)** | 건물 정보(용도·규모·입지) 기반 노출도 |
| 4 | **V (Vulnerability)** | 건물 특성(구조·연식·내진 등) 기반 취약성 |
| 5 | **통합 리스크** | `H × E × V / 10000` |
| 6 | **AAL** | `base_aal × F_vuln × (1 - insurance_rate)`, `F_vuln = 0.9 + (V/100) × 0.2` |

**지원 리스크 9종**: 극한 고온, 극한 한파, 산불, 가뭄, 물 부족, 해수면 상승, 하천 홍수, 도시 홍수, 태풍

## 프로젝트 구조

```
polaris_backend_modelops/
├── main.py                  # FastAPI 앱 + APScheduler 배치 등록
├── pyproject.toml           # 의존성·도구 설정 (black/ruff/pytest/mypy)
├── Dockerfile               # 멀티스테이지 빌드 (Python 3.11 + GDAL/NetCDF)
├── .env.example             # 환경변수 템플릿
├── modelops/                # 계산 엔진 패키지 (26k LOC)
│   ├── agents/              #   리스크별 계산 에이전트
│   │   ├── hazard_calculate/          # H 점수 (9종)
│   │   ├── probability_calculate/     # P(H) 확률 (9종)
│   │   ├── exposure_calculate/        # E 노출도 (9종)
│   │   ├── vulnerability_calculate/   # V 취약성 (9종)
│   │   ├── risk_assessment/           # AAL 스케일링
│   │   └── site_assessment/           # 사업장 평가·이전 후보지 추천
│   ├── api/                 #   FastAPI 라우터·스키마 (site-assessment, batch-trigger, health)
│   ├── api_clients/         #   외부 API 클라이언트 (건축물대장·태풍·WAMIS)
│   ├── batch/               #   배치 실행기 (H/P(H) 시계열, EVAAL 온디맨드)
│   ├── config/              #   settings(.env), 재해 상수, fallback 상수
│   ├── data_loaders/        #   기후·공간·건물 데이터 로더
│   ├── database/            #   PostgreSQL 커넥션 풀
│   ├── preprocessing/       #   기후 지표 파생·기준기간 분리
│   ├── triggers/            #   PostgreSQL LISTEN/NOTIFY 리스너
│   └── utils/               #   격자 매핑·FWI 계산 등 유틸
├── ETL/                     # 기후 원본 → DB 적재 스크립트 (최초 1회)
├── src/esg_trends_agent/    # ESG 뉴스 수집·분석 LangGraph 에이전트 (Slack 알림)
├── scripts/                 # 실행·배포 스크립트
│   ├── run_three_sites_full.py   # 3개 사업장 전체 계산 (H/PH→건물→E/V/AAL)
│   ├── run_step3_only.py         # E/V/AAL만 재계산
│   ├── run_esg_agent.py          # ESG 에이전트 실행
│   └── deploy.sh, docker-*.sh, monitor.sh   # 배포·모니터링 (레포 루트에서 실행)
├── system_setting/          # 서버 초기 설정·cron 등록 스크립트
├── tests/                   # 테스트 (pytest)
└── docs/                    # 문서 (배치 가이드, ERD, 계산 로직, 인수인계 등)
```

## 기술 스택

| 분류 | 기술 |
|------|------|
| 언어/런타임 | Python 3.11+ |
| 웹 프레임워크 | FastAPI, Uvicorn |
| 스케줄러 | APScheduler (BackgroundScheduler + CronTrigger) |
| DB | PostgreSQL (psycopg2, ThreadedConnectionPool, LISTEN/NOTIFY) |
| 과학 계산 | NumPy, SciPy, GeoPandas, Shapely, rasterio, netCDF4, h5py |
| 설정 관리 | pydantic-settings, python-dotenv |
| ESG 에이전트 | LangGraph, LangChain(OpenAI), Tavily/DuckDuckGo, Slack SDK |
| 품질 도구 | black(line-length 100), ruff, mypy, pytest |
| 패키징/배포 | uv, Docker(멀티스테이지), GitHub Actions, GCP Artifact Registry |

## 배치 스케줄

`main.py` 의 APScheduler CronTrigger 기준 (상세: [docs/BATCH_JOBS.md](docs/BATCH_JOBS.md)):

| 배치 | 주기 | 시간(KST) | 내용 |
|------|------|-----------|------|
| P(H) Timeseries | 매년 1월 1일 | 02:00 | 전국 격자 × 9개 리스크 발생 확률 계산 |
| Hazard Score Timeseries | 매년 1월 1일 | 04:00 | P(H) 완료 후 H 점수 계산 |
| 재난안전데이터 ETL | 매일 | 09:00 | 긴급재난문자 수집·적재 (최근 5년) |
| ESG Trends Agent | 주 2회 (월·목) | 09:00 | 기후 뉴스 수집·분석 후 Slack 발송 (cron) |

등록된 스케줄은 API로 조회할 수 있습니다: `GET /api/batch-trigger/scheduled-jobs`.
(과거의 배치 강제 실행 POST 라우트들은 소비처가 없어 계약 정리 시 삭제되었습니다.)

## 로컬 실행 방법

```bash
# 1. 클론 및 의존성 설치
git clone https://github.com/On-Do-Polaris/polaris_backend_modelops.git
cd polaris_backend_modelops
uv sync                      # 또는: pip install -e .

# 2. 환경변수 설정 (비밀번호 기본값 없음 — 반드시 설정)
cp .env.example .env
# .env 편집: DW_DB_PASSWORD 등 입력

# 3. (최초 1회) ETL로 기후 데이터 적재
python ETL/01_run_all_etl.py

# 4. FastAPI 서버 실행 (포트 8001)
uvicorn main:app --host 0.0.0.0 --port 8001
# API 문서: http://localhost:8001/docs
# Health Check: http://localhost:8001/api/health
```

실행 스크립트 (레포 루트에서):

```bash
# 3개 사업장 전체 계산 (H/PH → 건물 데이터 → E/V/AAL)
python scripts/run_three_sites_full.py [--log-file three_sites_full.log]

# E/V/AAL 단계만 재계산
python scripts/run_step3_only.py [--log-file step3_only.log]
```

> DB 접속 정보는 코드에 하드코딩하지 않고 `.env`/환경변수로만 주입합니다.
> `DW_DB_PASSWORD` 가 비어 있으면 DB 연결 시 명확한 에러가 발생합니다.

## 테스트

`tests/unit/` 은 순수 계산 로직(KDE 확률·AAL 스케일링·H×E×V 통합 점수·격자 유틸) 단위 테스트로, DB·네트워크 없이 결정론적으로 실행됩니다.

```bash
python -m venv .venv && .venv/Scripts/pip install pytest pytest-cov "numpy<2" scipy pydantic pydantic-settings python-dotenv psycopg2-binary requests
.venv/Scripts/python -m pytest tests/unit -v --no-cov
```

## 환경변수

`.env.example` 과 동일한 목록입니다.

변수 이름은 공통 규약([docs/CONVENTIONS.md](docs/CONVENTIONS.md) §4)의 정식 명칭을 따릅니다.

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DW_DB_HOST` / `DW_DB_PORT` / `DW_DB_NAME` / `DW_DB_USER` / `DW_DB_PASSWORD` | `localhost` / `5433` / `skala_datawarehouse` / `skala_dw_user` / (없음 — 필수) | 데이터웨어하우스 (기후 원본·격자·계산 결과 — ModelOps 메인 DB) |
| `APP_DB_HOST` / `APP_DB_PORT` / `APP_DB_NAME` / `APP_DB_USER` / `APP_DB_PASSWORD` | `localhost` / `5432` / `skala_application` / `skala_app_user` / (필수) | 애플리케이션 DB (Spring Boot 연동) |
| `FASTAPI_BASE_URL` | `http://localhost:8000` | FastAPI AI 서버 콜백 URL |
| `INTERNAL_API_KEY` | (빈 값) | 서비스 간 인증 키 (`X-API-Key` 헤더) |
| `PROBABILITY_SCHEDULE_MONTH/DAY/HOUR/MINUTE` | `1/1/2/0` | P(H) 배치 스케줄 (매년 1/1 02:00) |
| `HAZARD_SCHEDULE_MONTH/DAY/HOUR/MINUTE` | `1/1/4/0` | H 배치 스케줄 (매년 1/1 04:00) |
| `PARALLEL_WORKERS` | `4` | 배치 병렬 워커 수 |
| `BATCH_SIZE` | `1000` | 배치 크기 |
| `NOTIFY_CHANNEL` | `aiops_trigger` | PostgreSQL LISTEN/NOTIFY 채널 |

## API 요약

경로·파라미터 명칭은 공통 규약([docs/CONVENTIONS.md](docs/CONVENTIONS.md))과
서비스 간 계약 표([docs/API_CONTRACT.md](docs/API_CONTRACT.md))를 따릅니다.

| 구분 | 메서드·경로 | 설명 | 계약 # |
|------|------------|------|--------|
| 제공 | `POST /api/site-assessment/calculate` | 사업장 리스크 계산 (H·E·V·AAL, 백그라운드) — body는 camelCase (`buildingInfo`, `assetInfo`) | #18 |
| 제공 | `POST /api/site-assessment/recommend-locations` | 이전 후보지 추천 (비동기 + 완료 콜백) — body는 camelCase (`batchId`, `candidateGrids`, `searchCriteria`) | #19 |
| 제공 | `GET /api/health` · `GET /api/health/db` | 헬스체크 (`{status:"ok", service:"modelops", version}`) | #24, #25 |
| 제공 | `GET /api/site-assessment/task-status/{task_id}` · `/tasks` · `DELETE /task/{task_id}` | 백그라운드 작업 상태 조회·삭제 (소비처 확인 전 존치 — 계약 §3-5) | — |
| 제공 | `GET /api/batch-trigger/scheduled-jobs` | 스케줄된 배치 작업 조회 (운영자용 — 계약 §3-5) | — |
| 발신 | `POST {FASTAPI_BASE_URL}/api/internal/callbacks/recommendation-complete?batchId=` | 후보지 추천 완료 콜백 (`X-API-Key` 인증) | #21 |

## 배포 개요

GitHub Actions 기반 CI/CD (`.github/workflows/`):

1. **CI** (`ci_modelops.yaml`): develop push/PR 시 black·ruff·mypy·pytest 검사 →
   main push 시 Docker 이미지 빌드 후 **GCP Artifact Registry** 푸시
2. **CD** (`cd_modelops.yaml`): CI 성공 시 SSH로 운영 서버 접속 →
   최신 이미지 pull → 기존 컨테이너 교체(Recreate) → `/api/health` 헬스체크
3. 환경변수는 GitHub Secrets → 컨테이너 `-e` 주입 (비밀번호는 코드·이미지에 미포함)

수동 배포·모니터링 스크립트는 `scripts/` 에 있습니다 (레포 루트에서 실행):

```bash
./scripts/deploy.sh [IMAGE_TAG] [PORT]   # 빌드→배포
./scripts/monitor.sh                     # 컨테이너 상태 확인
```

## 문서

| 문서 | 내용 |
|------|------|
| [docs/CONVENTIONS.md](docs/CONVENTIONS.md) | 3-레포 공통 규약 (네이밍·환경변수·통신·폴더 구조) |
| [docs/API_CONTRACT.md](docs/API_CONTRACT.md) | 서비스 간 API 계약 표 (정식 경로·파라미터·체크리스트) |
| [docs/BATCH_JOBS.md](docs/BATCH_JOBS.md) | 전체 배치 작업 목록·스케줄·수동 실행법 |
| [docs/BATCH_SCHEDULE_GUIDE.md](docs/BATCH_SCHEDULE_GUIDE.md) | 배치 스케줄링 상세 가이드 (APScheduler/cron) |
| [docs/PhysicalRiskLogic.md](docs/PhysicalRiskLogic.md) | 리스크 계산 로직 상세 |
| [docs/API_TEST_GUIDE.md](docs/API_TEST_GUIDE.md) | API 테스트 가이드 |
| [docs/modelops_handover/](docs/modelops_handover/) | 계산 로직·데이터 스키마·API 명세 인수인계 문서 |
| [docs/README_frontend.md](docs/README_frontend.md) | (참고) 프론트엔드 레포 README |
| [ETL/README.md](ETL/README.md) | ETL 파이프라인 가이드 |
