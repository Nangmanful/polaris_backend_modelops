# SKALA Physical Risk AI System - ETL Pipeline

SKALA Physical Risk AI 시스템의 데이터 수집 및 적재(ETL) 파이프라인입니다.
기후 데이터, 지리 정보, 건축물 정보 등 물리적 리스크 분석에 필요한 데이터를 수집하여 PostgreSQL Datawarehouse에 적재합니다.

## 디렉토리 구조

```
etl/
├── .env                          # 환경변수 설정 (API 키, DB 접속 정보)
├── .gitignore                    # Git 제외 파일
├── .venv/                        # Python 가상환경
├── utils.py                      # 통합 유틸리티 (DB 연결, 로깅, API 클라이언트)
├── requirements.txt              # Python 의존성
├── logs/                         # 실행 로그 디렉토리
│
├── 01_run_all_etl.py            # ETL 전체 실행 스크립트
├── 02_load_climate_geocode.py   # 기후 데이터 + 역지오코딩 통합 적재
├── 03_load_buildings.py         # 건축물대장 API 모듈
├── 03.1_load_buildings_example.py # 건축물대장 적재 예제
│
└── etl_base/                     # 기존 ETL 스크립트 (레거시)
    ├── local/                    # 로컬 파일 기반 ETL
    │   ├── data/                # 원본 데이터 파일 (NetCDF, GeoJSON 등)
    │   └── scripts/             # 로컬 데이터 적재 스크립트
    └── api/                      # API 기반 ETL
        └── scripts/             # API 데이터 수집 스크립트
```

## 환경 설정

### 1. Python 가상환경 생성

```bash
cd modelops/etl
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 환경변수 설정 (.env)

`.env` 파일에 다음 정보를 설정합니다:

```bash
# Database (PostgreSQL with PostGIS)
DW_DB_HOST=localhost
DW_DB_PORT=5555
DW_DB_NAME=datawarehouse
DW_DB_USER=skala
DW_DB_PASSWORD=<비밀번호>

# 공공데이터포털 API
PUBLICDATA_API_KEY=your_api_key

# V-World API (역지오코딩)
VWORLD_API_KEY=your_api_key

# 재난안전데이터공유플랫폼
RIVER_API_KEY=your_api_key
EMERGENCYMESSAGE_API_KEY=your_api_key

# 기상청 API
TYPHOON_API_KEY=your_api_key
```

## ETL 스크립트

### 메인 스크립트

| 스크립트 | 설명 | 대상 테이블 |
|---------|------|------------|
| `01_run_all_etl.py` | 전체 ETL 실행 | 모든 테이블 |
| `02_load_climate_geocode.py` | 기후 데이터 + 역지오코딩 | 16개 기후 테이블 + location_grid |
| `03_load_buildings.py` | 건축물대장 API 모듈 | api_buildings |
| `03.1_load_buildings_example.py` | 건축물대장 적재 예제 | api_buildings |

### etl_base/local/scripts (로컬 데이터)

| 스크립트 | 설명 | 대상 테이블 |
|---------|------|------------|
| `01_load_admin_regions.py` | 행정구역 경계 | admin_regions |
| `02_load_weather_stations.py` | 기상 관측소 정보 | weather_stations |
| `03_load_grid_station_mappings.py` | 격자-관측소 매핑 | grid_station_mappings |
| `04_load_population.py` | 인구 데이터 | population_data |
| `05_load_landcover.py` | 토지피복도 | raw_landcover |
| `06_load_dem.py` | 수치표고모델 (DEM) | raw_dem |
| `07_load_drought.py` | 가뭄 지수 | drought_data |
| `08_load_climate_grid.py` | 기후 격자 데이터 | 기후 관련 테이블 |
| `09_load_sea_level.py` | 해수면 상승 | sea_level_data |
| `10_load_water_stress.py` | 물 스트레스 | water_stress_data |
| `11_load_site_data.py` | SK 사업장 데이터 | site_data |

### etl_base/api/scripts (API 데이터)

| 스크립트 | 설명 | API 소스 |
|---------|------|----------|
| `01_load_river_info.py` | 하천 정보 | 재난안전데이터공유플랫폼 |
| `02_load_emergency_messages.py` | 긴급재난문자 | 재난안전데이터공유플랫폼 |
| `03_load_vworld_geocode.py` | 역지오코딩 | VWorld API |
| `04_load_typhoon.py` | 태풍 정보 | 기상청 API Hub |
| `05_load_wamis.py` | 수문 정보 | WAMIS |
| `06_load_buildings.py` | 건축물대장 | 국토교통부 |
| `15_load_disaster_yearbook.py` | 재해연보 | 행정안전부 |
| `16_load_typhoon_besttrack.py` | 태풍 베스트트랙 | 기상청 |

## 사용법

### 전체 ETL 실행

```bash
cd modelops/etl
source .venv/bin/activate
python 01_run_all_etl.py
```

### 테스트 모드 (샘플 데이터)

```bash
# SAMPLE_LIMIT 환경변수로 테스트 데이터 수 제한
SAMPLE_LIMIT=10 python 01_run_all_etl.py
```

### 특정 스크립트 실행

```bash
# 기후 데이터 적재
SAMPLE_LIMIT=5 python 02_load_climate_geocode.py

# 건축물대장 적재
SAMPLE_LIMIT=10 python 03.1_load_buildings_example.py
```

### 특정 ETL만 실행 (01_run_all_etl.py)

```bash
# L1 ~ L11: 로컬 데이터, A1 ~ A7: API 데이터
python 01_run_all_etl.py --only L1,L2,L3
python 01_run_all_etl.py --only A1,A2
```

## 데이터 소스

### 로컬 파일 데이터

| 데이터 | 형식 | 위치 | 설명 |
|-------|------|------|-----|
| 기후 시나리오 | NetCDF (.nc) | `etl_base/local/data/` | SSP1/2/3/5 기후 예측 데이터 |
| 행정구역 | GeoJSON | `etl_base/local/data/admin/` | 시군구 경계 폴리곤 |
| DEM | ASCII XYZ / ZIP | `etl_base/local/data/DEM/` | 수치표고모델 (경기도, 서울 등) |
| 토지피복도 | GeoTIFF | `etl_base/local/data/landcover/` | 환경부 토지피복도 |

### API 데이터

| API | 제공 기관 | 주요 데이터 |
|-----|----------|-----------|
| 공공데이터포털 | 행정안전부 | 재해연보, 인구통계 |
| VWorld | 국토지리정보원 | 역지오코딩 |
| 재난안전데이터공유플랫폼 | MOIS | 하천정보, 긴급재난문자 |
| 기상청 API Hub | 기상청 | 태풍, AWS 기상 관측 |
| WAMIS | 한국수자원공사 | 수문 정보 |
| 건축물대장 | 국토교통부 | 건축물 정보 |

## 데이터베이스

### 대상 데이터베이스

- **Host**: localhost (또는 환경변수 `DW_DB_HOST`)
- **Port**: 5555 (또는 환경변수 `DW_DB_PORT`)
- **Database**: datawarehouse
- **Extension**: PostGIS (공간 데이터 처리)

### 주요 테이블

#### 위치 데이터
- `location_grid`: 1km 격자 정보 (울산 지역)
- `admin_regions`: 행정구역 경계
- `sk_sites`: SK 사업장 좌표

#### 기후 데이터 (SSP 시나리오)
- `ta_data`: 평균기온 (월별)
- `tamax_data`: 최고기온 (월별)
- `tamin_data`: 최저기온 (월별)
- `rn_data`: 강수량 (월별)
- `ws_data`: 풍속 (월별)
- `rhm_data`: 상대습도 (월별)
- `csdi_data`: 한파일수 (연별)
- `wsdi_data`: 폭염일수 (연별)
- `rx1day_data`: 최대 1일 강수량 (연별)
- `rx5day_data`: 최대 5일 강수량 (연별)
- `cdd_data`: 연속 무강수일수 (연별)
- `rain80_data`: 호우 발생일수 (연별)
- `sdii_data`: 강수강도 (연별)
- `spei12_data`: 가뭄지수 (월별)

#### 래스터 데이터
- `raw_dem`: 수치표고모델 (Point)
- `raw_landcover`: 토지피복도

#### API 캐시 테이블
- `api_river_info`: 하천 정보
- `api_emergency_messages`: 긴급재난문자
- `api_typhoon_data`: 태풍 정보
- `api_buildings`: 건축물대장

## 로깅

모든 ETL 스크립트는 실행 로그를 `logs/` 디렉토리에 저장합니다.

```
logs/
├── load_climate_geocode_20251212.log
├── load_buildings_20251212.log
└── ...
```

로그 형식:
```
2025-12-12 15:30:45 - load_climate_geocode - INFO - 울산 1km 격자 1000개 생성
2025-12-12 15:30:46 - load_climate_geocode - INFO - SK 사업장 7개 삽입
```

## 기후 시나리오 (SSP)

ETL은 IPCC AR6 기후 시나리오 데이터를 처리합니다:

| 시나리오 | 설명 | 2100년 온도 상승 |
|---------|------|-----------------|
| SSP1-2.6 | 지속가능 발전 | +1.8°C |
| SSP2-4.5 | 중간 경로 | +2.7°C |
| SSP3-7.0 | 지역 경쟁 | +3.6°C |
| SSP5-8.5 | 화석연료 의존 | +4.4°C |

## 주의사항

### API 호출 제한
- 재난안전데이터공유플랫폼: 1,000회/일
- 공공데이터포털: 서비스별 상이 (일반적으로 1,000회/일)
- VWorld: 10,000회/일

테스트 시 `SAMPLE_LIMIT` 환경변수를 사용하여 API 호출 횟수를 제한하세요.

### 대용량 데이터
- DEM 데이터는 포인트 수가 많아 메모리 사용량이 높을 수 있습니다
- 기후 NetCDF 파일은 파일당 수백 MB 크기입니다
- 배치 처리를 통해 메모리 효율적으로 데이터를 적재합니다

### 좌표계
- 기본 좌표계: EPSG:5174 (Korea 2000 / Unified CS)
- VWorld API: EPSG:4326 (WGS84)
- 필요시 ST_Transform을 사용하여 변환

## 트러블슈팅

### 데이터베이스 연결 오류
```bash
# PostgreSQL 서비스 확인
docker ps  # Docker 컨테이너 확인
psql -h localhost -p 5555 -U skala -d datawarehouse
```

### API 키 오류
```bash
# .env 파일에 API 키가 설정되어 있는지 확인
cat .env | grep API_KEY
```

### 메모리 부족
```bash
# SAMPLE_LIMIT으로 데이터 양 제한
SAMPLE_LIMIT=100 python 06_load_dem.py
```

## 라이선스

SKALA Physical Risk AI System - Internal Use Only

---

**마지막 업데이트**: 2025-12-12
**버전**: v2.0 (디렉토리 구조 개편)
