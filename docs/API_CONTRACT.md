# Polaris Backend — 서비스 간 API 계약 (API_CONTRACT)

> `CONVENTIONS.md`의 별첨 계약 표. 3개 레포(`polaris_backend_springboot` · `polaris_backend_fastapi` · `polaris_backend_modelops`)의 **코드를 전수 조사**해 작성했다 (문서가 아니라 라우트 데코레이터·클라이언트 호출 코드가 근거).
> 조사 기준 커밋: 1단계 리팩토링 반영 상태. 조사일: 2026-07-23.
>
> 파일 경로는 각 레포 루트 기준 상대경로. 접두어 `SB=polaris_backend_springboot`, `FA=polaris_backend_fastapi`, `MO=polaris_backend_modelops`.

## 0. 요약

| 구분 | edge 수 |
|---|---|
| 활성 통합 지점(edge) 총계 | **25** (Spring→FastAPI 17 · FastAPI→ModelOps 2 · 콜백 2 · 헬스 4) |
| 변경 필요 | **18** |
| 유지 (이미 규약 부합) | **7** |
| 삭제 대상 (주석 처리된 dead 계약) | **6** |
| Spring 대외(프론트) API 정규화 대상 | 2개 컨트롤러 (`/api/site`, `/api/report`) + query-param 식별자 정리 |

변경의 3대 축:
1. **파라미터 정식 명칭 통일** — `jobid`→`jobId`, `disaster_type`→`disasterType`, `batch_id`→`batchId`, `ssp_scenario`→`scenario` 등 (CONVENTIONS §2 표).
2. **콜백 경로 통일** — `/api/internal/callbacks/<이벤트>` (CONVENTIONS §3).
3. **헬스 통일** — 세 서비스 모두 `GET /api/health` (+ Dockerfile HEALTHCHECK 동반 수정).

---

## 1. 정식 계약 표

표기: **변경** = 규약 위반이라 경로/파라미터를 고침, **유지** = 이미 규약 부합, **복원** = 소비측은 호출하는데 제공측 라우트가 주석 처리되어 현재 깨져 있음(제공측 구현 필요), **삭제 대상** = 양측 모두 주석/미사용.

### 1-A. Spring Boot → FastAPI (인증: `X-API-Key`)

| # | 용도 | 메서드 | 정식 경로(신) | 파라미터(정식 명칭) | 제공측 (FA) | 소비측 (SB) | 현재 경로(구) | 변경 여부 |
|---|---|---|---|---|---|---|---|---|
| 1 | 분석 시작(배치) | POST | `/api/analysis/start` | body: `userId`, `sites[]`, `hazardTypes[]`, `priority`, `options` | `src/routes/analysis.py:33` | `client/fastapi/FastApiClient.java:90` | 동일 | **유지** (단, hazardTypes 값 한글 변환 문제 — §3-1 참고) |
| 2 | 분석 작업 상태 조회 | GET | `/api/analysis/{jobId}/status` | path: `jobId` | `src/routes/analysis.py:167` | `FastApiClient.java:118-135 (uri :122)` | `GET /api/analysis/status?userId={userId}&jobid={jobid}` | **변경** — `jobid`→`jobId`, 식별자 path화. userId 최신 작업 조회는 `GET /api/analysis/status?userId=`로 확정(§3-2 해결, 2026-07-23) |
| 3 | 대시보드 요약 | GET | `/api/dashboard/summary?siteIds=…` | query: `siteIds`(복수, 필터) | `src/routes/dashboard.py:15` | `FastApiClient.java:145-155 (uri :148)` | 동일 | **유지** |
| 4 | 물리 리스크 점수 | GET | `/api/analysis/sites/{siteId}/physical-risk-scores?hazardType=&term=` | path: `siteId` / query: `hazardType`, `term` | `src/routes/analysis.py:218` | `FastApiClient.java:166-177 (uri :168)` | `GET /api/analysis/physical-risk-scores?siteId=…` | **변경** — 식별자 path화 |
| 5 | 재무 영향(AAL) | GET | `/api/analysis/sites/{siteId}/financial-impacts?hazardType=&term=` | path: `siteId` / query: `hazardType`, `term` | `src/routes/analysis.py:270` | `FastApiClient.java:227-238 (uri :229)` | `GET /api/analysis/financial-impacts?siteId=…` | **변경** — 식별자 path화 |
| 6 | 취약성 분석 | GET | `/api/analysis/sites/{siteId}/vulnerability` | path: `siteId` | `src/routes/analysis.py:309` | `FastApiClient.java:248-257 (uri :250)` | `GET /api/analysis/vulnerability?siteId=…` | **변경** — 식별자 path화 |
| 7 | 분석 개요 | GET | `/api/analysis/sites/{siteId}/summary` | path: `siteId` (latitude/longitude는 §3-3 미해결) | `src/routes/analysis.py:353` | `FastApiClient.java:465-477 (uri :468)` | `GET /api/analysis/summary?siteId=&latitude=&longitude=` | **변경** — 식별자 path화 |
| 8 | 사업장 이전 비교 시뮬레이션 | POST | `/api/simulation/relocation/compare` | body (RelocationSimulationRequest) | `src/routes/simulation.py:16` | `FastApiClient.java:288-295 (uri :290)` | 동일 | **유지** |
| 9 | 기후 시뮬레이션 | POST | `/api/simulation/climate` | body (ClimateSimulationRequest) | `src/routes/simulation.py:39` | `FastApiClient.java:305-330 (uri :309)` | 동일 | **유지** |
| 10 | 이전 후보지 추천 조회 | GET | `/api/simulation/sites/{siteId}/location-recommendation` | path: `siteId` | `src/routes/simulation.py:57` | `FastApiClient.java:487-497 (uri :490)` | `GET /api/simulation/location/recommendation?siteId=…` | **변경** — 식별자 path화 |
| 11 | 리포트 생성 | POST | `/api/reports` | body (CreateReportRequest) | `src/routes/reports.py:19` **(주석 처리 — 제공측 부재)** | `FastApiClient.java:340-347 (uri :342)` | `POST /api/reports` | **복원** — 경로는 규약 부합, FA 라우트 주석 해제/구현 필요 |
| 12 | 사용자별 리포트 조회 | GET | `/api/reports?userId=…` | query: `userId`(필터) | `src/routes/reports.py:29` | `FastApiClient.java:507-517 (uri :510)` | 동일 | **유지** |
| 13 | 리포트 웹 뷰 | GET | `/api/reports/{reportId}/web` | path: `reportId` | `src/routes/reports.py:70` **(주석 처리 — 제공측 부재)** | `FastApiClient.java:357-366 (uri :359)` | `GET /api/reports/web?reportId=…` | **변경+복원** — 식별자 path화, FA 라우트 복원 필요 |
| 14 | 리포트 PDF | GET | `/api/reports/{reportId}/pdf` | path: `reportId` | `src/routes/reports.py:112` **(주석 처리 — 제공측 부재)** | `FastApiClient.java:393-402 (uri :395)` | `GET /api/reports/pdf?reportId=…` | **변경+복원** — 식별자 path화, FA 라우트 복원 필요 |
| 15 | 리포트 삭제(사용자 단위) | DELETE | `/api/reports?userId=…` | query: `userId`(필터) | `src/routes/reports.py:223` **(주석 처리 — 제공측 부재)** | `FastApiClient.java:428-438 (uri :431)` | `DELETE /api/reports?userId=…` | **복원(보류)** — §3-4 미해결. 계약 확정 전 소비측 호출 유지 여부 결정 필요 |
| 16 | 리포트 추가 데이터 등록 | POST | `/api/reports/data` | multipart form: `userId`, `siteId`, `file` | `src/routes/reports.py:173` | `FastApiClient.java:529-558 (uri :541)` | 동일 | **유지** |
| 17 | 과거 재해 이력 | GET | `/api/past?year=&disasterType=&severity=` | query: `year`, `disasterType`, `severity` (모두 필터) | `src/routes/past.py:15` (alias `disasterType`) | `FastApiClient.java:570-590 (uri :574, `disaster_type` 송신)` | `GET /api/past?disaster_type=…` | **변경** — 소비측만 수정: `disaster_type`→`disasterType`. **현재 파라미터 불일치로 필터가 무시되는 실버그** |

**삭제 대상 (양측 또는 소비측 주석 처리 — 계약에서 제외, 코드 삭제)**

| 용도 | 구 경로 | 소비측 (SB, 주석) | 제공측 (FA, 주석) |
|---|---|---|---|
| 과거 재난 이력(분석 기반) | `GET /api/analysis/past-events` | `FastApiClient.java:179-196` | `src/routes/analysis.py:257` |
| SSP 시나리오 전망 | `GET /api/analysis/ssp` | `FastApiClient.java:198-217` | `src/routes/analysis.py:402` |
| 통합 분석 결과 | `GET /api/analysis/total` | `FastApiClient.java:259-278` | `src/routes/analysis.py:339` |
| 리포트 웹뷰(userId 기반, deprecated) | `GET /api/reports/web?userId` | `FastApiClient.java:368-383` | (없음) |
| 리포트 PDF(userId 기반, deprecated) | `GET /api/reports/pdf?userId` | `FastApiClient.java:404-418` | (없음) |
| 리포트 삭제(deprecated wrapper) | — | `FastApiClient.java:440-453` | (없음) |

또한 FA 쪽 소비처 없는 라우트: `src/routes/analysis.py:94(/status 구버전)`, `:126(/enhance)`, `src/routes/disaster_history.py` 전체(3개 모두 주석), `src/routes/recommendation.py`(410 tombstone 4개) — §3-5 참고.

### 1-B. FastAPI → ModelOps (현재 인증: `Authorization: Bearer` → **`X-API-Key`로 변경**)

| # | 용도 | 메서드 | 정식 경로(신) | 파라미터(정식 명칭) | 제공측 (MO) | 소비측 (FA) | 현재 경로(구) | 변경 여부 |
|---|---|---|---|---|---|---|---|---|
| 18 | 사업장 리스크 계산 (H·E·V·AAL) | POST | `/api/site-assessment/calculate` | body: `sites{}`, `buildingInfo`, `assetInfo`, `targetYears[]` (camelCase alias) | `modelops/api/routes/site_assessment.py:288` (모델 `modelops/api/schemas/site_models.py:38`) | `ai_agent/services/modelops_client.py:161` | 경로 동일, body 필드 snake_case (`building_info`, `asset_info`, `target_years`) | **변경(필드)** — 경로 유지, JSON 필드 camelCase화(Pydantic alias). `target_years`는 스키마에 없는 필드 — §3-6 |
| 19 | 이전 후보지 추천(비동기, 콜백 연동) | POST | `/api/site-assessment/recommend-locations` | body: `sites{}`, `batchId`, `candidateGrids[]`, `buildingInfo`, `assetInfo`, `searchCriteria{maxCandidates, scenario, targetYear}` | `site_assessment.py:702` (모델 `site_models.py:74`) | `modelops_client.py:248` | 경로 동일, body 필드 snake_case (`batch_id`, `ssp_scenario`, `search_criteria` 등) | **변경(필드)** — `batch_id`→`batchId`, `ssp_scenario`→`scenario`(금지 표기 sspScenario 계열), `target_year`→`targetYear`, 나머지 camelCase화 |

MO 쪽 소비처 확인 안 되는 라우트(§3-5): `site_assessment.py:804 /task-status/{task_id}` · `:861 /tasks` · `:907 /task/{task_id}` · `batch_trigger.py:275 /api/batch-trigger/scheduled-jobs` (batch_trigger의 나머지 POST 11개는 전부 주석 = 삭제 대상). FA `main.py:189`의 `/modelops-proxy/{path:path}`는 테스트 콘솔(static/index.html) 전용 프록시.

### 1-C. 콜백 (정식: `/api/internal/callbacks/<이벤트>`, 인증: `X-API-Key`)

| # | 용도 | 메서드 | 정식 경로(신) | 파라미터 | 제공측 | 소비측 | 현재 경로(구) | 변경 여부 |
|---|---|---|---|---|---|---|---|---|
| 20 | 분석/리포트 완료 알림 (FastAPI→Spring, 이메일 발송 트리거) | POST | `/api/internal/callbacks/analysis-complete` | body: `userId`, `report`(boolean) | SB `controller/AnalysisController.java:558 (@PostMapping("/complete"), 클래스 @RequestMapping("/api/analysis") :38)` | FA `ai_agent/services/springboot_client.py:79-81` | `POST /api/analysis/complete` | **변경** — 경로 재명명. SB에 내부 콜백 컨트롤러 분리 권장(§2-1) |
| 21 | 후보지 추천 완료 알림 (ModelOps→FastAPI) | POST | `/api/internal/callbacks/recommendation-complete` | query: `batchId` | FA `src/routes/analysis.py:420 (/modelops/recommendation-completed)` | MO `modelops/api/routes/site_assessment.py:57,66` | `POST /api/analysis/modelops/recommendation-completed?batchId=` | **변경** — 경로 재명명. 파라미터 `batchId`는 이미 정식 명칭(유지) |

### 1-D. 헬스체크 (정식: 세 서비스 모두 `GET /api/health`)

| # | 서비스 | 정식 경로(신) | 현재 경로(구) | 제공측 | 소비측/참조처 | 변경 여부 |
|---|---|---|---|---|---|---|
| 22 | springboot | `GET /api/health` | `GET /api/health` | `controller/HealthController.java:30,66` | SB `Dockerfile:39-40`은 `/actuator/health` 참조 | **유지** (Dockerfile은 §3-7 판단 필요) |
| 23 | fastapi | `GET /api/health` | `GET /api/v1/health` (`src/routes/meta.py:28-29`) + `GET /health,/health/ready,/health/detailed,/health/live` (`ai_agent/api/health_router.py:31,145,156,181,232`) | 좌동 | FA `Dockerfile:118-119`(→`/api/v1/health`), `Dockerfile.cloudrun:43-44`(→`:8080/health`) | **변경** — `/api/health`로 통일. **Dockerfile 2종 HEALTHCHECK 경로 동반 수정 필수.** 이중 구현 통합은 §3-8 |
| 24 | modelops | `GET /api/health` | `GET /health` (`modelops/api/routes/health.py:17`) | 좌동 | FA `modelops_client.py:280`, MO `Dockerfile:96-97` | **변경** — 제공측·소비측·**Dockerfile HEALTHCHECK 3곳 동시 수정 필수** |
| 25 | modelops (DB) | `GET /api/health/db` | `GET /health/db` (`health.py:31`) | 좌동 | FA `modelops_client.py:311` | **변경** — `/api` 접두 통일 |

### 1-E. Spring 대외(프론트) API — 컨트롤러 12개 베이스 경로

| 컨트롤러 (파일:라인) | 현재 베이스 경로 | 주요 엔드포인트 | 판정 |
|---|---|---|---|
| `AnalysisController.java:38` | `/api/analysis` | POST /start, GET /status, GET /summary, GET /physical-risk, GET /aal, GET /vulnerability, POST /complete | 유지. 단 `/complete`은 #20으로 내부 콜백 이동 |
| `AuthController.java:35` | `/api/auth` | /register-email, /register-verificationCode, /register, /login, /logout, /refresh, /password/reset-* | 유지 |
| `DashboardController.java:28` | `/api/dashboard` | GET | 유지 |
| `GoogleOAuthController.java:33` | (클래스 매핑 없음) `GET /oauth2callback` | — | 예외 유지 — Google 리다이렉트 URI 고정(§3-9) |
| `HealthController.java:30` | `/api/health` | GET, GET /cors-check | 유지 |
| `MetaController.java:30` | `/api/meta` | GET /hazards, /industries, /ssp-scenarios | 유지 |
| `PastController.java:31` | `/api/past` | GET | 유지 |
| `ReportController.java:34` | **`/api/report`** | GET, POST /data | **정규화 대상 → `/api/reports`** (단수형 금지) |
| `SimulationController.java:34` | `/api/simulation` | GET /location/recommendation, POST /location/compare, POST /climate | 유지 |
| `SiteController.java:34` | **`/api/site`** | GET(?siteName=), POST, PATCH(?siteId=), DELETE(?siteId=) | **정규화 대상 → `/api/sites`** + PATCH/DELETE의 `?siteId=` → `/{siteId}` path화(:267, :327). `SitesController`와 병합 검토(§3-10) |
| `SitesController.java:28` | `/api/sites` | GET | 유지 |
| `UserController.java:29` | `/api/users` | GET /me, PATCH /me, DELETE /me | 유지 |

---

## 2. 레포별 변경 체크리스트

### 2-1. polaris_backend_springboot

**클라이언트 (FastApiClient.java — `src/main/java/com/skax/physicalrisk/client/fastapi/`)**
- [ ] `:122-130` getAnalysisStatus — `jobid`→`jobId`, 정식 경로 `/api/analysis/{jobId}/status` 반영 (#2)
- [ ] `:168-173` getPhysicalRiskScores — `/api/analysis/sites/{siteId}/physical-risk-scores` (#4)
- [ ] `:229-234` getFinancialImpact — `/api/analysis/sites/{siteId}/financial-impacts` (#5)
- [ ] `:250-253` getVulnerability — `/api/analysis/sites/{siteId}/vulnerability` (#6)
- [ ] `:468-473` getAnalysisSummary — `/api/analysis/sites/{siteId}/summary` (#7)
- [ ] `:490-493` getLocationRecommendation — `/api/simulation/sites/{siteId}/location-recommendation` (#10)
- [ ] `:359-362` getReportWebViewByReportId — `/api/reports/{reportId}/web` (#13)
- [ ] `:395-398` getReportPdfByReportId — `/api/reports/{reportId}/pdf` (#14)
- [ ] `:574-585` getPastDisasters — query `disaster_type`→`disasterType` (#17, 실버그 수정)
- [ ] 주석 메서드 6개 삭제: `:179-196`, `:198-217`, `:259-278`, `:368-383`, `:404-418`, `:440-453`
- [ ] `:67` HazardTypeMapper 한글 변환 제거 여부 — §3-1 확정 후

**컨트롤러**
- [ ] `AnalysisController.java:558` `/complete` → 신규 내부 콜백 컨트롤러 `POST /api/internal/callbacks/analysis-complete`로 이동 (#20). SecurityConfig의 permit/인증 경로 목록도 함께 갱신
- [ ] `ReportController.java:34` `/api/report` → `/api/reports` (#1-E)
- [ ] `SiteController.java:34` `/api/site` → `/api/sites`, `:264-267` PATCH·`:324-327` DELETE의 `@RequestParam siteId` → `@PathVariable` (#1-E)

**설정·환경변수**
- [ ] `src/main/resources/application.yml:52` `api-key: ${FASTAPI_API_KEY}` → `${INTERNAL_API_KEY}` / `application-local.yml:35` 동일 (`:51` `FASTAPI_BASE_URL`은 이미 규약 부합 — 유지)
- [ ] `application-prod.yml:15` base-url 하드코딩 → `${FASTAPI_BASE_URL}` 주입으로
- [ ] `.env.example:33-34` — `FASTAPI_BASE_URL` 유지, `FASTAPI_API_KEY`→`INTERNAL_API_KEY`
- [ ] `.github/workflows/cd_java.yaml:89` `-e FASTAPI_API_KEY=` → `-e INTERNAL_API_KEY=` (+ `FASTAPI_BASE_URL` 주입 추가)
- [ ] `Dockerfile:39-40` HEALTHCHECK — `/actuator/health` 유지 여부 §3-7 결정 후 필요 시 `/api/health`로

### 2-2. polaris_backend_fastapi

**라우트 (제공측)**
- [ ] `src/routes/analysis.py:167-214` `/status` — `jobid` alias 제거, `/{jobId}/status`로 (#2)
- [ ] `src/routes/analysis.py:218,270,309,353` — `siteId` query → path (`/sites/{siteId}/…`) (#4-#7)
- [ ] `src/routes/analysis.py:420-450` `/modelops/recommendation-completed` → `/api/internal/callbacks/recommendation-complete` (#21) — 신규 internal 라우터 권장
- [ ] `src/routes/simulation.py:57-83` — `siteId` query → path (#10)
- [ ] `src/routes/reports.py:19(POST), :70(web), :112(pdf), :223(DELETE)` — 주석 라우트 복원(신 경로로) 또는 계약 제외 확정 (#11, #13-#15, §3-4)
- [ ] `src/routes/past.py:15-36` — 이미 `disasterType` alias. 변경 없음(소비측 수정으로 해결)
- [ ] `src/routes/meta.py:8` prefix `/api/v1` — `/api/v1/health`→`/api/health`(#23), `/api/v1/health/database`→`/api/health/database`, `/api/v1/meta/hazards`→`/api/meta/hazards` (§3-5 소비처 확인 후)
- [ ] `ai_agent/api/health_router.py:31` prefix `/health` → `/api/health` 통합 (§3-8) + `main.py:100` 등록부
- [ ] 삭제 대상 정리: `src/routes/analysis.py:94,126,257,339,402` 주석 블록, `src/routes/disaster_history.py` 전체, `src/routes/recommendation.py`(410 tombstone) — §3-5 확정 후

**클라이언트 (소비측)**
- [ ] `ai_agent/services/modelops_client.py:150-157, 229-245` — body 키 camelCase: `buildingInfo`/`assetInfo`/`targetYears`/`batchId`/`candidateGrids`/`searchCriteria{maxCandidates, scenario, targetYear}` (#18, #19)
- [ ] `modelops_client.py:69` `Authorization: Bearer` → `X-API-Key` 헤더 (CONVENTIONS §3)
- [ ] `modelops_client.py:58,346` `MODELOPS_URL` → `MODELOPS_BASE_URL` / `:347` `MODELOPS_API_KEY` → `INTERNAL_API_KEY`
- [ ] `modelops_client.py:280` `/health`→`/api/health`, `:311` `/health/db`→`/api/health/db` (#24, #25)
- [ ] `ai_agent/services/springboot_client.py:79-81` — `/api/analysis/complete` → `/api/internal/callbacks/analysis-complete` (#20) + `X-API-Key` 헤더 추가(현재 무인증 호출)
- [ ] `springboot_client.py:42,116` `SPRING_BOOT_BASE_URL` → `SPRINGBOOT_BASE_URL`
- [ ] `main.py:189-196` `/modelops-proxy` — `MODELOPS_BASE_URL` 사용은 유지(이미 정식 명칭). 프록시 존치 여부 §3-5

**설정·환경변수**
- [ ] `src/core/config.py:18` `API_KEY` → `INTERNAL_API_KEY` (+ `src/core/auth.py:8` 참조부)
- [ ] `.env.example` — `:45 API_KEY`→`INTERNAL_API_KEY`, `:58 MODELOPS_URL`→`MODELOPS_BASE_URL`, `:61 MODELOPS_API_KEY` 삭제(INTERNAL_API_KEY로 통합), `:67 SPRING_BOOT_BASE_URL`→`SPRINGBOOT_BASE_URL`, `:88-89 SPRINGBOOT_API_URL/SPRINGBOOT_API_KEY`는 코드 사용처 없음 → 삭제
- [ ] `.github/workflows/cd_python.yaml` — `:83 API_KEY`→`INTERNAL_API_KEY`, `:95 MODELOPS_URL` 삭제, `:96 MODELOPS_BASE_URL` 유지, `:97 SPRING_BOOT_BASE_URL`→`SPRINGBOOT_BASE_URL`
- [ ] `Dockerfile:118-119` HEALTHCHECK `/api/v1/health` → `/api/health` (#23)
- [ ] `Dockerfile.cloudrun:43-44` HEALTHCHECK `http://localhost:8080/health` → `/api/health` (포트도 재확인)

### 2-3. polaris_backend_modelops

**라우트 (제공측)**
- [ ] `modelops/api/routes/health.py:17` `/health` → `/api/health`, `:31` `/health/db` → `/api/health/db` (#24, #25)
- [ ] `modelops/api/schemas/site_models.py:11-88` — 요청 모델에 camelCase alias 부여 (`buildingInfo`, `assetInfo`, `batchId`, `candidateGrids`, `searchCriteria`, `maxCandidates`, `scenario`(구 `ssp_scenario`), `targetYear`) (#18, #19)
- [ ] `modelops/api/routes/batch_trigger.py` — 주석 POST 11개 삭제 대상, `:275 /scheduled-jobs` 존치 여부 §3-5
- [ ] `modelops/api/routes/site_assessment.py:804,861,907` task 관련 3개 — 소비처 없음, 존치 여부 §3-5
- [ ] `main.py:249-258` root 응답의 `"health": "/health"` 안내 문자열 갱신

**콜백 (소비측)**
- [ ] `modelops/api/routes/site_assessment.py:57` 콜백 URL → `{FASTAPI_BASE_URL}/api/internal/callbacks/recommendation-complete` (#21) — `:66`의 `params={"batchId": …}`는 유지

**설정·환경변수**
- [ ] `modelops/config/settings.py:67` `FASTAPI_URL` → `FASTAPI_BASE_URL`, `:68` `FASTAPI_API_KEY` → `INTERNAL_API_KEY` (`:35` 기본값 필드 포함)
- [ ] `.env.example:23-24` — `FASTAPI_URL`→`FASTAPI_BASE_URL`, `FASTAPI_API_KEY`→`INTERNAL_API_KEY`
- [ ] `.github/workflows/cd_modelops.yaml:87-88` — `-e FASTAPI_URL=`→`-e FASTAPI_BASE_URL=`, `-e FASTAPI_API_KEY=`→`-e INTERNAL_API_KEY=`
- [ ] `Dockerfile:96-97` HEALTHCHECK `http://localhost:8001/health` → `/api/health` (#24) — **라우트 변경과 반드시 같은 커밋으로**

---

## 3. 모호·미해결 항목 (코드만으로 판단 불가)

1. **hazardTypes 값 변환** — SB `FastApiClient.java:67`이 `HazardTypeMapper.toFastApiValues()`로 영문→**한글** 변환 후 FA에 전달. CONVENTIONS §2는 `hazardType` 값을 영문 snake_case 9종으로 규정. FA 내부(AnalysisService)가 한글 값을 기대하는지 확인 후, 영문 snake_case로 통일하고 매퍼를 제거할지 결정 필요.
2. **userId 기반 최신 작업 조회 — 해결(2026-07-23)**: `GET /api/analysis/status?userId=` 유지로 확정. userId는 리소스 식별자가 아니라 "해당 사용자의 최신 작업"을 고르는 **필터**이므로 CONVENTIONS §2(query=필터)에 부합. FA 라우트 복원 완료(`analysis.py`), 특정 작업 조회는 `/{jobId}/status` 병행.
3. **`/summary`의 latitude/longitude** — 사업장 좌표를 매 호출마다 query로 전달(SB `:468-472`). siteId로 DB에서 좌표를 조회하면 파라미터 자체가 불필요. 데이터 소유권(사이트 정보는 SB 소유) 관점에서 팀 결정 필요.
4. **리포트 삭제 계약** — SB는 `DELETE /api/reports?userId=`를 호출하지만 FA 라우트는 주석(`reports.py:223`, 원래도 파라미터 없는 전체 삭제 스텁). "사용자 단위 삭제"가 실제 요구인지, reportId 단위(`DELETE /api/reports/{reportId}`)로 갈지 미정.
5. **소비처 불명 라우트 존치 여부** — FA: `/api/v1/meta/hazards`(SB MetaController와 중복), `/api/additional-data/*` 5개(SB는 `/api/reports/data`만 호출 — 프론트 직접 호출 여부 불명), `/modelops-proxy/*`(테스트 콘솔 전용), `/api/recommendation/*`(410 tombstone — 언제 제거?). MO: `/api/site-assessment/task-status·tasks·task`, `/api/batch-trigger/scheduled-jobs`(운영자 수동 조회용으로 추정). 호출 주체(프론트/운영 도구) 확인 전 삭제 금지.
6. **`target_years` 스키마 누락** — FA `modelops_client.py:156-157`은 `target_years`를 body에 넣지만 MO `SiteRiskRequest`(`site_models.py:38-45`)에는 해당 필드가 없어 현재 **조용히 무시**된다. 계약에 포함할지(모델에 추가) 제거할지 결정 필요.
7. **SB Dockerfile HEALTHCHECK** — 현재 `/actuator/health`(`Dockerfile:39-40`). 컨테이너 내부 체크는 actuator 유지가 무난하나, 규약의 `/api/health`로 통일할지 여부는 운영 판단.
8. **FA 헬스 이중 구현** — `meta.py`의 DB 포함 헬스와 `health_router.py`의 GCP/K8s용 probe(`/ready`, `/live`, `/detailed`)가 병존. `/api/health` 하나로 합칠 때 probe 세분 경로(`/api/health/live` 등)를 어떻게 남길지 결정 필요.
9. **`/oauth2callback`** — Google Cloud Console에 등록된 리다이렉트 URI라 경로 변경 시 외부 설정 동반 변경. 규약 예외로 명시 유지 권장.
10. **SiteController vs SitesController 병합** — `/api/site`(CRUD)와 `/api/sites`(목록)가 분리돼 있다. `/api/sites`로 정규화하면 자연스럽게 한 컨트롤러로 병합되나, 기존 프론트 호환 기간(구경로 리다이렉트/deprecation 기간) 정책 필요.
11. **분석 결과 sub-resource 계층** — #4~#7, #10의 정식 경로를 `/api/analysis/sites/{siteId}/…` 계층으로 제안했다(식별자 path화의 최소 변경안). `/api/sites/{siteId}/analysis/…` 대안도 가능하므로 팀 확정 필요 — 확정 시 이 표를 갱신할 것.
