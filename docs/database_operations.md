# ModelOps API - Database Operations Reference

> ModelOps Risk Assessment API의 모든 데이터베이스 읽기/쓰기 작업 종합 문서

**작성일**: 2024-12-08
**버전**: v1.0

---

## 목차

1. [개요](#개요)
2. [데이터 읽기 (READ) 작업](#데이터-읽기-read-작업)
3. [데이터 쓰기 (WRITE) 작업](#데이터-쓰기-write-작업)
4. [배치 작업 데이터 흐름](#배치-작업-데이터-흐름)
5. [API 엔드포인트별 DB 작업](#api-엔드포인트별-db-작업)
6. [테이블별 작업 요약](#테이블별-작업-요약)

---

## 개요

ModelOps API는 PostgreSQL + PostGIS를 사용하며, 다음과 같은 주요 DB 작업을 수행합니다:

- **기후 데이터 조회**: 14개 테이블에서 기후 지표 수집 (월간/연간)
- **건물 정보 조회**: 공간 쿼리를 통한 자산 데이터 검색
- **리스크 계산 결과 저장**: H, P(H), E, V, AAL 5개 결과 테이블
- **배치 작업 추적**: 실시간 진행률 업데이트 (0-100%)

**핵심 파일**: [modelops/database/connection.py](../modelops/database/connection.py)

---

## 데이터 읽기 (READ) 작업

### 1. 기후 데이터 조회

#### `fetch_climate_data(latitude, longitude, risk_type=None, ssp_scenario='ssp2')`
**위치**: [connection.py:55-139](../modelops/database/connection.py#L55-L139)

**설명**: 특정 그리드의 기후 데이터를 조회하고, 리스크별 전처리 수행

**읽는 테이블**:
- `location_grid` - 그리드 좌표 → grid_id 매핑
- 월간 데이터 (6개): `ta_data`, `rn_data`, `ws_data`, `rhm_data`, `si_data`, `spei12_data`
- 연간 데이터 (8개): `wsdi_data`, `csdi_data`, `rx1day_data`, `rx5day_data`, `cdd_data`, `rain80_data`, `sdii_data`, `sea_level_data`

**반환**:
```python
{
    'climate_data': {
        'ta': [21.5, 22.1, ...],        # 월평균 기온
        'rn': [80.5, 95.2, ...],        # 월 강수량
        'wsdi': [12, 15, 18, ...],      # 연간 폭염일수
        # ... 기타 지표
    }
}
```

**사용 예시**:
```python
# 극한 고온 리스크용 데이터 조회 (전처리 포함)
data = DatabaseConnection.fetch_climate_data(
    latitude=37.5665,
    longitude=126.9780,
    risk_type='extreme_heat',
    ssp_scenario='ssp2'
)
```

---

#### `fetch_grid_coordinates()`
**위치**: [connection.py:43-52](../modelops/database/connection.py#L43-L52)

**설명**: 전체 그리드 좌표 목록 조회 (배치 작업용)

**읽는 테이블**: `climate_data`

**반환**:
```python
[
    {'latitude': 33.1, 'longitude': 126.1},
    {'latitude': 33.1, 'longitude': 126.2},
    # ... 전체 그리드
]
```

---

#### `fetch_sea_level_data(grid_id, ssp_scenario='ssp2')`
**위치**: [connection.py:240-278](../modelops/database/connection.py#L240-L278)

**설명**: 해수면 상승 예측 데이터 조회

**읽는 테이블**: `sea_level_grid`, `sea_level_data`

**반환**:
```python
[0.0, 0.5, 1.2, 1.9, ...]  # 2020-2100년 연간 SLR (cm)
```

---

### 2. 건물 정보 조회

#### `fetch_building_info(latitude, longitude, search_radius=500)`
**위치**: [connection.py:349-383](../modelops/database/connection.py#L349-L383)

**설명**: 좌표 주변 가장 가까운 건물 정보 조회 (공간 쿼리)

**읽는 테이블**: `api_buildings`

**공간 쿼리**: `ST_Distance(geom, ST_Point(longitude, latitude))`

**반환**:
```python
{
    'building_age': 25,
    'structure': 'RC',
    'main_purpose': 'office',
    'floors_above': 10,
    'floors_below': 2,
    'total_area': 5000.0,
    'arch_area': 500.0
}
```

---

### 3. 인구 데이터 조회

#### `fetch_population_data(latitude, longitude)`
**위치**: [connection.py:785-839](../modelops/database/connection.py#L785-L839)

**설명**: 행정구역 인구 데이터 조회 (2020-2050 예측)

**읽는 테이블**: `location_admin`

**공간 쿼리**: `ST_Contains(geom, ST_Point(longitude, latitude))`

**반환**:
```python
{
    'admin_name': '서울특별시 강남구',
    'population_2020': 561052,
    'population_2025': 548000,
    # ... 2030, 2035, 2040, 2045
    'population_2050': 520000,
    'population_change_2020_2050': -41052,
    'population_change_rate_percent': -7.31
}
```

---

### 4. 계산 결과 조회

#### `fetch_hazard_results(latitude, longitude, risk_types=None)`
**위치**: [connection.py:696-737](../modelops/database/connection.py#L696-L737)

**설명**: Hazard Score 조회 (사전 계산된 H 값)

**읽는 테이블**: `hazard_results`

**반환**:
```python
{
    'extreme_heat': {
        'hazard_score': 0.75,
        'hazard_score_100': 75,
        'hazard_level': 'High'
    },
    'river_flood': {
        'hazard_score': 0.42,
        'hazard_score_100': 42,
        'hazard_level': 'Medium'
    }
    # ... 9개 리스크
}
```

---

#### `fetch_probability_results(latitude, longitude, risk_types=None)`
**위치**: [connection.py:740-782](../modelops/database/connection.py#L740-L782)

**설명**: Probability & AAL 조회 (사전 계산된 P(H) 값)

**읽는 테이블**: `probability_results`

**반환**:
```python
{
    'extreme_heat': {
        'aal': 0.082,
        'bin_probabilities': {
            'bin1': 0.65,
            'bin2': 0.25,
            'bin3': 0.08,
            'bin4': 0.02
        },
        'calculation_details': { /* JSONB */ },
        'bin_data': { /* JSONB */ }
    }
    # ... 9개 리스크
}
```

---

#### `fetch_base_aals(latitude, longitude, risk_types=None)`
**위치**: [connection.py:386-405](../modelops/database/connection.py#L386-L405)

**설명**: 기준 AAL 값 조회 (AAL Scaling 계산용)

**읽는 테이블**: `probability_results`

**반환**:
```python
{
    'extreme_heat': 0.082,
    'river_flood': 0.125,
    # ... 9개 리스크
}
```

---

## 데이터 쓰기 (WRITE) 작업

### 1. 계산 결과 저장 (Upsert 패턴)

모든 결과 저장 메서드는 **ON CONFLICT DO UPDATE** 패턴을 사용하여 재계산 시 덮어쓰기를 지원합니다.

---

#### `save_hazard_results(results: List[Dict])`
**위치**: [connection.py:328-346](../modelops/database/connection.py#L328-L346)

**설명**: Hazard Score 저장

**쓰는 테이블**: `hazard_results`

**Primary Key**: `(latitude, longitude, risk_type)`

**입력 스키마**:
```python
[
    {
        'latitude': 37.5665,
        'longitude': 126.9780,
        'risk_type': 'extreme_heat',
        'hazard_score': 0.75,
        'hazard_score_100': 75,
        'hazard_level': 'High',
        'calculated_at': datetime.now()
    }
]
```

---

#### `save_probability_results(results: List[Dict])`
**위치**: [connection.py:281-325](../modelops/database/connection.py#L281-L325)

**설명**: Probability & AAL 저장

**쓰는 테이블**: `probability_results`

**Primary Key**: `(latitude, longitude, risk_type)`

**입력 스키마**:
```python
[
    {
        'latitude': 37.5665,
        'longitude': 126.9780,
        'risk_type': 'extreme_heat',
        'aal': 0.082,
        'bin_probabilities': {  # JSONB
            'bin1': 0.65,
            'bin2': 0.25,
            'bin3': 0.08,
            'bin4': 0.02
        },
        'calculation_details': { /* JSONB */ },
        'bin_data': { /* JSONB */ },
        'calculated_at': datetime.now()
    }
]
```

---

#### `save_exposure_results(results: List[Dict])`
**위치**: [connection.py:408-442](../modelops/database/connection.py#L408-L442)

**설명**: Exposure Score 저장 (On-Demand)

**쓰는 테이블**: `exposure_results`

**Primary Key**: `(latitude, longitude, risk_type)`

**입력 스키마**:
```python
[
    {
        'latitude': 37.5665,
        'longitude': 126.9780,
        'risk_type': 'extreme_heat',
        'exposure_score': 0.68,
        'proximity_factor': 0.85,
        'normalized_asset_value': 0.72,
        'calculated_at': datetime.now()
    }
]
```

---

#### `save_vulnerability_results(results: List[Dict])`
**위치**: [connection.py:445-483](../modelops/database/connection.py#L445-L483)

**설명**: Vulnerability Score 저장 (On-Demand)

**쓰는 테이블**: `vulnerability_results`

**Primary Key**: `(latitude, longitude, risk_type)`

**입력 스키마**:
```python
[
    {
        'latitude': 37.5665,
        'longitude': 126.9780,
        'risk_type': 'extreme_heat',
        'vulnerability_score': 0.55,
        'vulnerability_level': 'Medium',
        'factors': {  # JSONB
            'building_age': 25,
            'structure': 'RC',
            'floors': 10
        },
        'calculated_at': datetime.now()
    }
]
```

---

#### `save_aal_scaled_results(results: List[Dict])`
**위치**: [connection.py:486-526](../modelops/database/connection.py#L486-L526)

**설명**: AAL Scaled 저장 (On-Demand)

**쓰는 테이블**: `aal_scaled_results`

**Primary Key**: `(latitude, longitude, risk_type)`

**입력 스키마**:
```python
[
    {
        'latitude': 37.5665,
        'longitude': 126.9780,
        'risk_type': 'extreme_heat',
        'base_aal': 0.082,
        'vulnerability_scale': 1.55,
        'final_aal': 0.127,
        'insurance_rate': 0.00127,
        'expected_loss': 127000.0,
        'calculated_at': datetime.now()
    }
]
```

---

### 2. 배치 작업 관리

#### `create_batch_job(job_type: str, input_params: Dict) -> str`
**위치**: [connection.py:531-556](../modelops/database/connection.py#L531-L556)

**설명**: 새 배치 작업 생성 (UUID 발급)

**쓰는 테이블**: `batch_jobs`

**반환**: `batch_id` (UUID string)

**예시**:
```python
batch_id = DatabaseConnection.create_batch_job(
    job_type='ondemand_risk_calculation',
    input_params={
        'latitude': 37.5665,
        'longitude': 126.9780,
        'risk_types': ['extreme_heat', 'river_flood']
    }
)
# batch_id: "550e8400-e29b-41d4-a716-446655440000"
```

---

#### `update_batch_progress(batch_id, progress, current_step=None, ...)`
**위치**: [connection.py:559-600](../modelops/database/connection.py#L559-L600)

**설명**: 배치 진행률 업데이트 (0-100%)

**쓰는 테이블**: `batch_jobs`

**예시**:
```python
# 10% 완료
DatabaseConnection.update_batch_progress(
    batch_id,
    progress=10,
    current_step="Fetching H and P(H)"
)

# 50% 완료
DatabaseConnection.update_batch_progress(
    batch_id,
    progress=50,
    current_step="Calculating E for extreme_heat",
    completed_items=5
)
```

---

#### `complete_batch_job(batch_id, results: Dict)`
**위치**: [connection.py:603-622](../modelops/database/connection.py#L603-L622)

**설명**: 배치 작업 완료 처리 (status='completed', progress=100)

**쓰는 테이블**: `batch_jobs`

**예시**:
```python
DatabaseConnection.complete_batch_job(
    batch_id,
    results={
        'integrated_risk': {
            'extreme_heat': 0.285,
            'river_flood': 0.142
        }
    }
)
```

---

#### `fail_batch_job(batch_id, error_message, error_stack_trace=None)`
**위치**: [connection.py:625-644](../modelops/database/connection.py#L625-L644)

**설명**: 배치 작업 실패 처리 (status='failed')

**쓰는 테이블**: `batch_jobs`

**예시**:
```python
DatabaseConnection.fail_batch_job(
    batch_id,
    error_message="Database connection timeout",
    error_stack_trace=traceback.format_exc()
)
```

---

#### `get_batch_status(batch_id) -> Dict`
**위치**: [connection.py:647-691](../modelops/database/connection.py#L647-L691)

**설명**: 배치 작업 상태 조회

**읽는 테이블**: `batch_jobs`

**반환**:
```python
{
    'batch_id': '550e8400-...',
    'job_type': 'ondemand_risk_calculation',
    'status': 'running',
    'progress': 50,
    'total_items': 9,
    'completed_items': 5,
    'failed_items': 0,
    'input_params': { /* JSONB */ },
    'results': None,
    'error_message': None,
    'created_at': '2024-12-08T10:00:00',
    'completed_at': None
}
```

---

## 배치 작업 데이터 흐름

### 1. Hazard Batch (H 계산)

**파일**: [modelops/batch/hazard_batch.py](../modelops/batch/hazard_batch.py)

**실행 주기**: Cron (매일 자정)

**데이터 흐름**:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. READ: 그리드 좌표 목록                                    │
│    fetch_grid_coordinates()                                 │
│    → [(lat1, lon1), (lat2, lon2), ...]                     │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. READ: 각 그리드별 기후 데이터 (9개 리스크별 반복)          │
│    fetch_climate_data(lat, lon, risk_type='extreme_heat')  │
│    → {ta, rn, wsdi, csdi, ...} (전처리 완료)               │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. COMPUTE: Hazard Agent 계산                               │
│    HazardAgent.calculate_hazard_score(climate_data)        │
│    → {hazard_score: 0.75, hazard_level: 'High'}           │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. WRITE: 결과 저장 (Upsert)                                │
│    save_hazard_results([                                    │
│      {lat, lon, risk_type, hazard_score, hazard_level}     │
│    ])                                                       │
│    → hazard_results 테이블                                  │
└─────────────────────────────────────────────────────────────┘
```

**처리량**: 전체 그리드 × 9개 리스크 (약 1,000+ 레코드/일)

---

### 2. Probability Batch (P(H) & AAL 계산)

**파일**: [modelops/batch/probability_batch.py](../modelops/batch/probability_batch.py)

**실행 주기**: Cron (매일 자정, Hazard Batch 이후)

**데이터 흐름**:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. READ: 그리드 좌표 + 기후 데이터                            │
│    fetch_grid_coordinates()                                 │
│    fetch_climate_data(lat, lon, risk_type)                 │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. READ: API 클라이언트 데이터 (필요시)                       │
│    - WAMIS: 수문 데이터                                      │
│    - Typhoon: 태풍 이력                                      │
│    - Building: 건물 정보                                     │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. COMPUTE: Probability Agent 계산                          │
│    ProbabilityAgent.calculate_probability(climate_data)    │
│    → {aal, bin_probabilities, calculation_details}         │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. WRITE: 결과 저장 (Upsert)                                │
│    save_probability_results([                               │
│      {lat, lon, risk_type, aal, bin_probabilities, ...}    │
│    ])                                                       │
│    → probability_results 테이블                             │
└─────────────────────────────────────────────────────────────┘
```

**처리량**: 전체 그리드 × 9개 리스크 (약 1,000+ 레코드/일)

---

### 3. On-Demand Risk Assessment (E, V, AAL 계산)

**파일**: [modelops/batch/ondemand_risk_batch.py](../modelops/batch/ondemand_risk_batch.py)

**실행 주기**: 사용자 요청 시 (On-Demand)

**데이터 흐름**:

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: H, P(H) 조회 (0% → 10%)                             │
│   READ: hazard_results, probability_results                │
│   → {hazard_scores, probabilities}                         │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 2: E 계산 (10% → 50%)                                  │
│   READ: api_buildings, location_admin                      │
│   COMPUTE: ExposureAgent (9개 리스크 순차)                  │
│   WRITE: exposure_results                                  │
│   UPDATE: batch_jobs (progress: 10→20→...→50)             │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 3: V 계산 (50% → 80%)                                  │
│   READ: api_buildings (building attributes)                │
│   COMPUTE: VulnerabilityAgent (9개 리스크 순차)             │
│   WRITE: vulnerability_results                             │
│   UPDATE: batch_jobs (progress: 50→55→...→80)             │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 4: AAL Scaled 계산 (80% → 95%)                         │
│   READ: probability_results (base_aal)                     │
│   READ: vulnerability_results (vulnerability_score)        │
│   COMPUTE: AALScalingAgent (9개 리스크 순차)                │
│   WRITE: aal_scaled_results                                │
│   UPDATE: batch_jobs (progress: 80→85→...→95)             │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 5: Integrated Risk 계산 (95% → 100%)                   │
│   READ: H, E, V, AAL (이전 단계 결과)                       │
│   COMPUTE: IntegratedRiskAgent                             │
│   → H × E × V = Physical Risk                             │
│   WRITE: batch_jobs (results, status='completed')         │
└─────────────────────────────────────────────────────────────┘
```

**처리 시간**: 1개 위치 × 9개 리스크 ≈ 8초

**WebSocket 진행률**:
- 0%: 시작
- 10%: H, P(H) 조회 완료
- 50%: E 계산 완료 (9개 리스크)
- 80%: V 계산 완료 (9개 리스크)
- 95%: AAL 계산 완료 (9개 리스크)
- 100%: 통합 리스크 계산 완료

---

## API 엔드포인트별 DB 작업

### POST `/api/v1/risk-assessment/calculate`

**파일**: [modelops/api/routes/risk_assessment.py:29-72](../modelops/api/routes/risk_assessment.py#L29-L72)

**DB 작업**:
1. **WRITE**: `create_batch_job()` → `batch_jobs` 테이블에 작업 생성
2. **비동기 실행**: Background task로 `OnDemandRiskBatch.run()` 실행
   - READ: `hazard_results`, `probability_results`
   - WRITE: `exposure_results`, `vulnerability_results`, `aal_scaled_results`
   - UPDATE: `batch_jobs` (progress 0% → 100%)

**요청**:
```json
{
  "latitude": 37.5665,
  "longitude": 126.9780,
  "risk_types": ["extreme_heat", "river_flood"]
}
```

**응답**:
```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "websocket_url": "ws://localhost:8001/api/v1/risk-assessment/ws/550e8400-..."
}
```

---

### GET `/api/v1/risk-assessment/status/{request_id}`

**파일**: [modelops/api/routes/risk_assessment.py:126-145](../modelops/api/routes/risk_assessment.py#L126-L145)

**DB 작업**:
- **READ**: In-memory store (batch_jobs 테이블 아님)

**응답**:
```json
{
  "request_id": "550e8400-...",
  "status": "running",
  "progress": 50,
  "current_step": "Calculating E for extreme_heat"
}
```

---

### WebSocket `/api/v1/risk-assessment/ws/{request_id}`

**파일**: [modelops/api/routes/risk_assessment.py:148-213](../modelops/api/routes/risk_assessment.py#L148-L213)

**DB 작업**:
- **READ**: In-memory store (실시간 진행률 스트리밍)

**메시지 예시**:
```json
{"progress": 10, "status": "running", "step": "Fetching H and P(H)"}
{"progress": 50, "status": "running", "step": "Calculating E"}
{"progress": 100, "status": "completed", "results": {...}}
```

---

### GET `/api/v1/risk-assessment/results/{lat}/{lon}`

**파일**: [modelops/api/routes/risk_assessment.py:216-315](../modelops/api/routes/risk_assessment.py#L216-L315)

**DB 작업**:
- **READ**: `exposure_results`, `vulnerability_results`, `aal_scaled_results`

**응답**:
```json
{
  "latitude": 37.5665,
  "longitude": 126.978,
  "exposure": {
    "extreme_heat": {"exposure_score": 0.68, ...},
    "river_flood": {"exposure_score": 0.52, ...}
  },
  "vulnerability": {
    "extreme_heat": {"vulnerability_score": 0.55, ...},
    "river_flood": {"vulnerability_score": 0.48, ...}
  },
  "aal_scaled": {
    "extreme_heat": {"final_aal": 0.127, ...},
    "river_flood": {"final_aal": 0.089, ...}
  }
}
```

---

### GET `/api/health/db`

**파일**: [modelops/api/routes/health.py:27-55](../modelops/api/routes/health.py#L27-L55)

**DB 작업**:
- **READ**: `SELECT 1` (연결 테스트)

**응답**:
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2024-12-08T10:30:00Z"
}
```

---

## 테이블별 작업 요약

### 입력 데이터 테이블 (Read-Only)

| 테이블명 | 용도 | 읽는 메서드 | 레코드 수 |
|---------|------|------------|----------|
| `location_grid` | 그리드 좌표 | `_fetch_raw_climate_data()` | ~1,000 |
| `ta_data` | 월평균 기온 | `_fetch_raw_climate_data()` | ~360,000 |
| `rn_data` | 월 강수량 | `_fetch_raw_climate_data()` | ~360,000 |
| `ws_data` | 월평균 풍속 | `_fetch_raw_climate_data()` | ~360,000 |
| `rhm_data` | 월평균 상대습도 | `_fetch_raw_climate_data()` | ~360,000 |
| `si_data` | 월 일사량 | `_fetch_raw_climate_data()` | ~360,000 |
| `spei12_data` | 월 SPEI-12 (가뭄지수) | `_fetch_raw_climate_data()` | ~360,000 |
| `wsdi_data` | 연 폭염일수 | `_fetch_raw_climate_data()` | ~30,000 |
| `csdi_data` | 연 한파일수 | `_fetch_raw_climate_data()` | ~30,000 |
| `rx1day_data` | 연 최대 1일 강수량 | `_fetch_raw_climate_data()` | ~30,000 |
| `rx5day_data` | 연 최대 5일 강수량 | `_fetch_raw_climate_data()` | ~30,000 |
| `cdd_data` | 연 최대 무강수일수 | `_fetch_raw_climate_data()` | ~30,000 |
| `rain80_data` | 연 80mm 이상 강수일수 | `_fetch_raw_climate_data()` | ~30,000 |
| `sdii_data` | 연 강수강도지수 | `_fetch_raw_climate_data()` | ~30,000 |
| `sea_level_grid` | 해수면 그리드 | `_fetch_sea_level_data()` | ~500 |
| `sea_level_data` | 해수면 상승 예측 | `_fetch_sea_level_data()` | ~40,000 |
| `api_buildings` | 건물 정보 | `fetch_building_info()`, BuildingClient | ~1,000,000 |
| `api_wamis_stations` | 수문 관측소 | WamisClient | ~300 |
| `api_wamis_cache` | 수문 관측 데이터 | WamisClient | ~10,000,000 |
| `api_typhoon_list` | 태풍 목록 | TyphoonClient | ~500 |
| `api_typhoon_tracks` | 태풍 이동 경로 | TyphoonClient | ~50,000 |
| `location_admin` | 행정구역 인구 | `fetch_population_data()` | ~250 |

---

### 출력 데이터 테이블 (Read-Write)

| 테이블명 | 용도 | Primary Key | 쓰는 메서드 | 읽는 메서드 | 업데이트 주기 |
|---------|------|------------|------------|------------|-------------|
| `hazard_results` | H 점수 | (lat, lon, risk_type) | `save_hazard_results()` | `fetch_hazard_results()` | 배치 (매일) |
| `probability_results` | P(H), AAL | (lat, lon, risk_type) | `save_probability_results()` | `fetch_probability_results()` | 배치 (매일) |
| `exposure_results` | E 점수 | (lat, lon, risk_type) | `save_exposure_results()` | API route | On-Demand |
| `vulnerability_results` | V 점수 | (lat, lon, risk_type) | `save_vulnerability_results()` | API route | On-Demand |
| `aal_scaled_results` | AAL (E×V 반영) | (lat, lon, risk_type) | `save_aal_scaled_results()` | API route | On-Demand |
| `batch_jobs` | 배치 작업 추적 | (batch_id) | `create_batch_job()`, `update_batch_progress()`, `complete_batch_job()`, `fail_batch_job()` | `get_batch_status()` | 실시간 |

---

## 주요 패턴 및 최적화

### 1. Upsert 패턴 (재계산 지원)

모든 결과 테이블은 `ON CONFLICT DO UPDATE` 사용:

```sql
INSERT INTO hazard_results (latitude, longitude, risk_type, hazard_score, ...)
VALUES (%s, %s, %s, %s, ...)
ON CONFLICT (latitude, longitude, risk_type)
DO UPDATE SET
    hazard_score = EXCLUDED.hazard_score,
    hazard_level = EXCLUDED.hazard_level,
    calculated_at = EXCLUDED.calculated_at
```

**장점**: 재계산 시 기존 데이터 자동 덮어쓰기, 중복 방지

---

### 2. JSONB 컬럼 사용

복잡한 계산 결과는 JSONB로 저장:

- `probability_results.bin_probabilities` - 확률 분포
- `probability_results.calculation_details` - 계산 세부사항
- `vulnerability_results.factors` - 취약성 요인
- `batch_jobs.input_params` - 입력 파라미터
- `batch_jobs.results` - 최종 결과

**장점**: 스키마 유연성, 중첩 데이터 저장

---

### 3. 공간 쿼리 (PostGIS)

건물/행정구역 검색에 공간 인덱스 사용:

```sql
-- 거리 기반 검색
SELECT * FROM api_buildings
WHERE ST_DWithin(geom, ST_Point(%s, %s), %s)
ORDER BY ST_Distance(geom, ST_Point(%s, %s))
LIMIT 1

-- 포함 검색
SELECT * FROM location_admin
WHERE ST_Contains(geom, ST_Point(%s, %s))
```

**장점**: 빠른 공간 검색 (GIST 인덱스)

---

### 4. SSP 시나리오 동적 컬럼

SSP 시나리오별 데이터 저장:

```python
# ssp1, ssp2, ssp3, ssp5 컬럼
climate_data = {
    'ssp1': [21.5, 22.1, ...],
    'ssp2': [22.0, 22.8, ...],  # 기본
    'ssp3': [22.5, 23.5, ...],
    'ssp5': [23.0, 24.2, ...]
}
```

**장점**: 다양한 시나리오 지원, 유연한 쿼리

---

### 5. 배치 진행률 실시간 업데이트

`batch_jobs` 테이블로 진행률 추적:

```python
# 0% → 10% → 50% → 80% → 95% → 100%
for idx, risk_type in enumerate(risk_types):
    # 계산 수행
    result = agent.calculate(...)

    # 진행률 업데이트
    progress = 10 + int((idx + 1) / len(risk_types) * 40)
    DatabaseConnection.update_batch_progress(
        batch_id, progress, f"Calculating E for {risk_type}"
    )
```

**장점**: WebSocket 실시간 스트리밍, 사용자 경험 향상

---

## 성능 고려사항

### 읽기 최적화

- **인덱스**: `(latitude, longitude, risk_type)` 복합 인덱스
- **공간 인덱스**: GIST 인덱스 (PostGIS)
- **연결 풀링**: psycopg2 connection pooling (향후 구현 권장)

### 쓰기 최적화

- **배치 INSERT**: 단일 쿼리로 여러 레코드 삽입
- **Upsert**: 중복 체크 없이 안전한 덮어쓰기
- **비동기 처리**: Background task로 메인 스레드 차단 방지

### 병렬 처리

- **Hazard/Probability Batch**: ProcessPoolExecutor (멀티프로세스)
- **On-Demand**: 순차 처리 (단일 위치, WebSocket 진행률 제공)

---

## 향후 개선 사항

1. **Connection Pooling**: `psycopg2.pool` 도입으로 연결 재사용
2. **Read Replica**: 읽기 전용 복제본 활용 (조회 성능 향상)
3. **Caching**: Redis/Memcached로 자주 조회되는 결과 캐싱
4. **Partitioning**: 결과 테이블 파티셔닝 (연도별, 리스크별)
5. **Materialized Views**: 자주 조인되는 쿼리 미리 계산

---

**문서 버전**: 1.0
**최종 업데이트**: 2024-12-08
**작성자**: ModelOps Team
