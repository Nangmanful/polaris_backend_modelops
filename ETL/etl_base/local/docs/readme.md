# SKALA Physical Risk AI - ETL 파이프라인

> SKALA Datawarehouse를 위한 데이터 로딩 스크립트 - 기후, 공간, API 캐시 데이터 수집

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue.svg)](https://www.postgresql.org/)
[![PostGIS](https://img.shields.io/badge/PostGIS-3.4-green.svg)](https://postgis.net/)

최종 수정일: 2025-11-25
버전: v03 (Wide Format 전환 - 기후 데이터 17개 테이블)

---

## 개요

이 ETL(Extract, Transform, Load) 파이프라인은 FastAPI AI 에이전트 분석을 위해 기후 예측 데이터, 공간 정보 및 외부 API 캐시 데이터를 SKALA Datawarehouse에 로드합니다.

### 이 파이프라인의 기능

- 📍 **행정구역**: 5,259개 한국 행정구역 경계 로드 (Shapefile → PostGIS)
- 🌡️ **기후 데이터**: 433M+ 행의 SSP 기후 예측 로드 (NetCDF → PostgreSQL)
- 🌊 **해수면 데이터**: 6,880개 해수면 상승 예측 로드 (NetCDF → PostgreSQL)
- 🗺️ **래스터 데이터**: DEM, 토지피복, 가뭄 데이터 로드 (GeoTIFF/HDF5 → PostGIS)
- 🏥 **API 캐시**: 오프라인 분석을 위한 12개 외부 API 데이터셋 사전 캐시

### 지원 데이터 형식

| 형식 | 용도 | 예시 |
|--------|-------|----------|
| NetCDF (.nc) | 기후 시계열 | SSP 시나리오, 기온, 강수량 |
| Shapefile (.shp) | 행정구역 경계 | 읍면동, 시군구 지역 |
| ASC/ASCII Grid | 래스터 기후 데이터 | TAMAX, TAMIN 일별 격자 |
| GeoTIFF (.tif) | 토지피복 | 위성 영상 분류 |
| HDF5 (.h5) | 가뭄 지수 | MODIS/SMAP 데이터 |
| Excel (.xlsx) | 인구 예측 | 인구조사 데이터 |
| tar.gz | 압축 아카이브 | ASC 파일 모음 |

---

## 주요 기능

- **이중 모드 운영**: 테스트용 샘플 모드(10개 레코드), 프로덕션용 전체 모드
- **트랜잭션 안전성**: 포괄적인 에러 처리로 에러 시 자동 롤백
- **배치 처리**: 433M+ 행 데이터셋에 최적화된 배치 삽입
- **진행 로깅**: 타임스탬프 및 행 개수가 포함된 상세 로그
- **지오메트리 처리**: 자동 좌표 변환 (WGS84 ↔ EPSG:5174)
- **재개 기능**: 존재 확인으로 이미 로드된 데이터 건너뛰기
- **메모리 효율**: 대용량 파일을 위한 스트리밍 읽기

---

## 빠른 시작

### 사전 요구사항

- Python 3.9+
- PostgreSQL 16 with PostGIS 3.4 ([skala-database](https://github.com/your-org/skala-database)를 통해 실행)
- **GDAL 3.0+** (raster 데이터 처리용 - landcover, DEM, drought)
- 8GB+ RAM 권장
- 전체 데이터 로드 시 100GB+ 디스크 공간

### 설치

1. **저장소 클론**
```bash
git clone https://github.com/your-org/skala-etl.git
cd skala-etl
```

2. **가상 환경 생성**
```bash
# uv 사용 (권장 - 더 빠름)
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt

# 또는 pip 사용
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. **환경 설정**
```bash
cp .env.example .env
# .env 파일에 Datawarehouse 자격 증명 입력
```

4. **데이터 디렉토리 준비**

**📦 데이터 다운로드**

전체 데이터셋(~67GB)은 Google Drive에서 다운로드하세요:
- **Google Drive 링크**: https://drive.google.com/drive/folders/1sbEoJcoE8m8IBUKQtckgCYv8t9l62wsO?usp=drive_link

다운로드 후 `data/` 디렉토리에 배치:
```bash
# 데이터 파일을 data/ 디렉토리에 배치
# 구조:
# data/
# ├── administrative_regions/
# ├── climate/
# │   ├── monthly_grid/
# │   ├── yearly_grid/
# │   └── sea_level/
# └── raster/
```

5. **샘플 로드 테스트 실행**
```bash
# 데이터 유형별 10개 샘플로 테스트
export SAMPLE_LIMIT=10
./test_sample_load.sh
```

---

## 디렉토리 구조

```
.
├── README.md                    # 본 문서
├── SETUP.md                     # 상세 설치 가이드
├── USAGE.md                     # 사용 사례
├── .env.example                 # 환경변수 템플릿
├── .gitignore                   # Git 제외 규칙
├── requirements.txt             # Python 의존성
├── pyproject.toml               # 패키지 구성
├── test_sample_load.sh          # 샘플 데이터 테스트 스크립트
│
├── scripts/                     # ETL 스크립트
│   ├── __init__.py
│   ├── db_config.py             # 데이터베이스 연결 유틸리티
│   ├── utils.py                 # 공통 헬퍼 함수
│   │
│   ├── load_admin_regions.py   # 행정구역 경계 로드 (Shapefile)
│   ├── load_population.py      # 인구 예측 로드 (Excel)
│   ├── load_sea_level_netcdf.py # 해수면 데이터 로드 (NetCDF)
│   ├── load_sgg261_data.py     # TAMAX/TAMIN 데이터 로드 (tar.gz ASC)
│   ├── load_monthly_grid_data.py # 월별 기후 로드 (NetCDF)
│   ├── load_yearly_grid_data.py  # 연별 기후 로드 (NetCDF)
│   ├── load_landcover.py       # 토지피복 래스터 로드 (GeoTIFF)
│   ├── load_dem.py              # DEM 래스터 로드 (ASCII Grid)
│   ├── load_drought.py          # 가뭄 데이터 로드 (HDF5)
│   │
│   ├── load_weather_stations.py        # 기상 관측소 로드 (JSON)
│   ├── load_grid_station_mappings.py   # 격자-관측소 매핑 로드 (JSON)
│   ├── load_water_stress_rankings.py   # WRI Aqueduct 물 스트레스 로드 (Excel)
│   │
│   ├── load_site_dc_power_simple.py      # 판교DC 전력 사용량 로드 (Excel)
│   ├── load_site_campus_energy_simple.py # 판교캠퍼스 에너지 로드 (Excel)
│   │
│   ├── inspect_netcdf.py        # NetCDF 검사 유틸리티
│   └── extract_monthly_nc.sh    # NetCDF 추출 헬퍼
│
├── data/                        # 데이터 파일 (사용자 제공)
│   ├── administrative_regions/
│   ├── climate/
│   ├── population/
│   ├── raster/
│   └── site_energy/             # 사이트별 에너지 사용량 데이터
│
├── logs/                        # 실행 로그
│   └── *.log
│
└── docs/                        # 문서
    ├── DB_ARCHITECTURE.md
    ├── branch_convention.md
    └── commit_convention.md
```

---

## ETL 스크립트 개요

### 핵심 위치 데이터

**1. load_admin_regions.py** - 행정구역 경계
```bash
python scripts/load_admin_regions.py
```
- **입력**: `data/administrative_regions/emd_5174.shp`
- **출력**: `location_admin` (5,259개 지역)
- **시간**: ~2분
- **기능**: PostGIS 지오메트리 변환 (EPSG:5174)

**2. load_population.py** - 인구 예측
```bash
python scripts/load_population.py
```
- **입력**: `data/population/population_projections.xlsx`
- **출력**: `location_admin.population_2020`, `population_2050` 업데이트
- **시간**: ~1분

### 기후 데이터

**3. load_sea_level_netcdf.py** - 해수면 상승
```bash
python scripts/load_sea_level_netcdf.py
```
- **입력**: `data/climate/sea_level/*.nc` (4개 SSP 시나리오)
- **출력**: `sea_level_grid` (80개 지점), `sea_level_data` (~1,720행)
- **시간**: ~5분
- **형식**: Wide format (year, grid_id, ssp1, ssp2, ssp3, ssp5)

**4. load_sgg261_data.py** - TAMAX/TAMIN 일별 데이터
```bash
python scripts/load_sgg261_data.py
```
- **입력**: `data/climate/sgg261/*.asc` (tar.gz 압축)
- **출력**: `tamax_data`, `tamin_data` (각 ~7.63M 행)
- **시간**: ~30-60분
- **형식**: Wide format (time, admin_id, ssp1, ssp2, ssp3, ssp5)
- **특별**: 누락된 시군구 코드 자동 생성

**5. load_monthly_grid_data.py** - 월별 기후 변수
```bash
python scripts/load_monthly_grid_data.py
```
- **입력**: `data/climate/monthly_grid/*.nc`
- **출력**: `ta_data`, `rn_data`, `ws_data`, `rhm_data`, `si_data`, `spei12_data`
- **행**: 테이블당 ~433M (451,351 격자 × 960개월) - Wide Format
- **시간**: ~2-3시간
- **형식**: Wide format (observation_date, grid_id, ssp1, ssp2, ssp3, ssp5)

**6. load_yearly_grid_data.py** - 연별 기후 극값
```bash
python scripts/load_yearly_grid_data.py
```
- **입력**: `data/climate/yearly_grid/*.nc`
- **출력**: `csdi_data`, `wsdi_data`, `rx1day_data`, `rx5day_data`, `cdd_data`, `rain80_data`, `sdii_data`, `ta_yearly_data`
- **행**: 테이블당 ~36M (451,351 격자 × 80년) - Wide Format
- **시간**: ~1-2시간
- **형식**: Wide format (year, grid_id, ssp1, ssp2, ssp3, ssp5)

### 래스터 데이터

> **⚠️ 중요**: 래스터 테이블(`raw_dem`, `raw_drought`, `raw_landcover`)은 `raster2pgsql` 표준 스키마를 사용합니다.
> - 컬럼: `rid` (래스터 타일 ID), `rast` (래스터 데이터), `filename` (원본 파일명)
> - `raster2pgsql`이 자동으로 테이블을 생성하고 공간 인덱스를 추가합니다.

**7. load_landcover.py** - 토지피복 분류
```bash
python scripts/load_landcover.py
```
- **입력**: `data/raster/landcover/*.tif` (240개 파일)
- **출력**: `raw_landcover` (raster2pgsql 표준 스키마)
- **시간**: ~2-3시간
- **도구**: GDAL `raster2pgsql`

**8. load_dem.py** - 디지털 고도 모델
```bash
python scripts/load_dem.py
```
- **입력**: `data/raster/dem/*.asc` (44개 파일)
- **출력**: `raw_dem` (raster2pgsql 표준 스키마)
- **시간**: ~30분
- **도구**: GDAL `gdal_translate` + `raster2pgsql`

**9. load_drought.py** - 가뭄 지수
```bash
python scripts/load_drought.py
```
- **입력**: `data/raster/drought/*.h5` (MODIS/SMAP)
- **출력**: `raw_drought` (raster2pgsql 표준 스키마)
- **시간**: ~1시간
- **도구**: GDAL `gdal_translate` + `raster2pgsql`

### 참조 데이터 (Reference Data)

**10. load_weather_stations.py** - 기상 관측소
```bash
python scripts/load_weather_stations.py
```
- **입력**: `data/stations_with_coordinates.json`
- **출력**: `weather_stations` (~1,086개 관측소)
- **시간**: ~5초
- **형식**: 관측소 코드, 이름, 좌표 (위경도), 유역 정보
- **특징**: PostGIS geometry 자동 생성, 좌표 없는 관측소 자동 스킵

**11. load_grid_station_mappings.py** - 격자-관측소 매핑
```bash
python scripts/load_grid_station_mappings.py
```
- **입력**: `data/grid_to_nearest_stations.json`
- **출력**: `grid_station_mappings` (~292,131개 매핑)
- **시간**: ~30초
- **형식**: 격자 좌표 → 최근접 관측소 3개 (거리, 순위 포함)
- **특징**: AI 모델 학습용 격자-관측소 매핑 데이터

**12. load_water_stress_rankings.py** - WRI Aqueduct 물 스트레스
```bash
python scripts/load_water_stress_rankings.py
```
- **입력**: `data/Aqueduct40_rankings_download_Y2023M07D05.xlsx`
- **출력**: `water_stress_rankings` (~161,731개 순위)
- **시간**: ~1분
- **형식**: 국가/지역별 물 스트레스 지수 (WRI Aqueduct 4.0)
- **특징**: 12개 물 리스크 지표, 미래 시나리오 포함

### 사이트 에너지 데이터

**13. load_site_dc_power_simple.py** - 판교DC 전력 사용량
```bash
export PANGYO_DC_SITE_ID="your-site-uuid"
python scripts/load_site_dc_power_simple.py
```
- **입력**: `data/site_energy/판교DC 전력 사용량_2301-2510.xlsx`
- **출력**: `site_dc_power_usage` (~24,792개 시간별 레코드)
- **시간**: ~10초
- **기간**: 2023-01-01 ~ 2025-10-29 (약 2년 10개월)
- **형식**: IT전력, 냉방전력, 일반전력, 합계 (kWh)
- **특징**: 시간별 데이터 저장, forward fill로 누락 날짜 보완, 중복 자동 제거

**14. load_site_campus_energy_simple.py** - 판교캠퍼스 에너지 사용량
```bash
export PANGYO_CAMPUS_SITE_ID="your-site-uuid"
python scripts/load_site_campus_energy_simple.py --year 2024
```
- **입력**: `data/site_energy/판교캠퍼스 에너지 사용량.xlsx`
- **출력**: `site_campus_energy_usage` (12개 월별 레코드)
- **시간**: ~5초
- **형식**: 수도(ton), 지역난방(Gcal→kWh), 전력(kWh)
- **특징**: 월별 컬럼을 행으로 변환, Gcal을 kWh로 자동 변환 (1 Gcal = 1,163 kWh)

---

## 데이터 로딩 모드

### 샘플 모드 (테스트)

테스트용으로 데이터 유형별 10개 샘플만 로드:

```bash
export SAMPLE_LIMIT=10
export PYTHONPATH=.

python scripts/load_admin_regions.py
python scripts/load_sea_level_netcdf.py
python scripts/load_sgg261_data.py
python scripts/load_monthly_grid_data.py

# 또는 테스트 스크립트 사용
./test_sample_load.sh
```

**예상 결과:**
- `location_admin`: 271행 (10개 읍면동 + 261개 자동 생성 시군구)
- `location_grid`: 10행
- `sea_level_grid`: 10행
- `ta_data`, `rn_data` 등: 각 10행 (Wide Format: 4 SSP 컬럼)
- `tamax_data`, `tamin_data`: 각 10행 (Wide Format: 4 SSP 컬럼)

### 전체 로드 모드 (프로덕션)

모든 데이터 로드 (SAMPLE_LIMIT 없음):

```bash
unset SAMPLE_LIMIT  # 또는 export를 완전히 생략
export PYTHONPATH=.

# 모든 스크립트를 순차적으로 실행
python scripts/load_admin_regions.py
python scripts/load_population.py
python scripts/load_sea_level_netcdf.py
python scripts/load_sgg261_data.py
python scripts/load_monthly_grid_data.py
python scripts/load_yearly_grid_data.py
python scripts/load_landcover.py
python scripts/load_dem.py
python scripts/load_drought.py
```

**예상 로드 시간:**

| 스크립트 | 로드된 행 | 시간 | 크기 |
|--------|-------------|------|------|
| 행정구역 | 5,259 | 2분 | ~50 MB |
| 인구 | 17 | 1분 | <1 MB |
| 해수면 | 6,880 | 5분 | ~10 MB |
| TAMAX/TAMIN (Wide) | 각 7.63M | 30분 | ~500 MB |
| 월별 격자 (6개 테이블, Wide) | 각 433M | 3시간 | ~50 GB |
| 연별 격자 (8개 테이블, Wide) | 각 36M | 2시간 | ~10 GB |
| 토지피복 | 240개 파일 | 3시간 | ~500 GB |
| DEM | 44개 파일 | 30분 | ~10 GB |
| 가뭄 | 2개 파일 | 1시간 | ~5 GB |
| **전체** | **~3B 행** | **~12-15시간** | **~2-3 TB** |

---

## 데이터 형식 패턴

### Wide Format (일별 행정구역)

사용처: `tamax_data`, `tamin_data`

```sql
CREATE TABLE tamax_data (
    time DATE NOT NULL,
    admin_id INTEGER NOT NULL,
    ssp1 REAL,  -- SSP1-2.6 값
    ssp2 REAL,  -- SSP2-4.5 값
    ssp3 REAL,  -- SSP3-7.0 값
    ssp5 REAL,  -- SSP5-8.5 값
    PRIMARY KEY (time, admin_id)
);
```

**Python 로드 예시:**
```python
cursor.execute("""
    INSERT INTO tamax_data (time, admin_id, ssp1, ssp2, ssp3, ssp5)
    VALUES (%s, %s, %s, %s, %s, %s)
""", (date, admin_id, ssp1_val, ssp2_val, ssp3_val, ssp5_val))
```

### Wide Format (월별/연별 격자)

사용처: 17개 기후 테이블 (일별 2개 + 월별 6개 + 연별 8개 + 해수면 1개)

```sql
CREATE TABLE ta_data (
    observation_date DATE NOT NULL,
    grid_id INTEGER NOT NULL,
    ssp1 REAL,  -- SSP1-2.6
    ssp2 REAL,  -- SSP2-4.5
    ssp3 REAL,  -- SSP3-7.0
    ssp5 REAL,  -- SSP5-8.5
    PRIMARY KEY (observation_date, grid_id)
);
```

**Python 로드 예시:**
```python
cursor.execute("""
    INSERT INTO ta_data (observation_date, grid_id, ssp1, ssp2, ssp3, ssp5)
    VALUES (%s, %s, %s, %s, %s, %s)
""", (date, grid_id, ssp1_val, ssp2_val, ssp3_val, ssp5_val))
```

**왜 Wide Format?**
- **75% 저장 공간 절감** (4개 행 → 1개 행으로 통합)
- **쿼리 성능 향상** (scenario_id JOIN 제거)
- **고정된 4개 시나리오** (SSP1-2.6, SSP2-4.5, SSP3-7.0, SSP5-8.5)
- **시나리오 간 비교 쿼리 단순화**

---

## 주요 기능

### 1. 트랜잭션 안전성

모든 스크립트는 적절한 트랜잭션 관리 사용:

```python
try:
    conn.rollback()  # 깨끗한 상태 보장
    cursor.execute("INSERT INTO ...")
    conn.commit()
except Exception as e:
    logger.error(f"오류: {e}")
    conn.rollback()
    raise
```

### 2. 자동 지오메트리 처리

PostGIS 지오메트리 변환:

```python
# WGS84 (EPSG:4326) → Korea 2000 (EPSG:5174)
cursor.execute("""
    INSERT INTO location_admin (geom, centroid)
    VALUES (
        ST_Transform(ST_GeomFromText(%s, 4326), 5174),
        ST_Transform(ST_Centroid(ST_GeomFromText(%s, 4326)), 5174)
    )
""", (wkt_geom, wkt_geom))
```

### 3. 누락 코드 자동 생성

`load_sgg261_data.py`가 누락된 시군구 코드를 자동 생성:

```python
if not admin_exists:
    cursor.execute("""
        INSERT INTO location_admin (admin_code, admin_name, level, sido_code, sigungu_code, geom, centroid)
        VALUES (%s, %s, 2, %s, %s,
                ST_Multi(ST_GeomFromText('POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))', 5174)),
                ST_SetSRID(ST_MakePoint(0.5, 0.5), 5174))
    """, (admin_code, admin_name, sido_code, sigungu_code))
```

### 4. 압축 파일 지원

tar.gz 아카이브 처리:

```python
with gzip.open(csv_path, 'rb') as gz_file:
    with tarfile.open(fileobj=gz_file, mode='r') as tar:
        csv_member = tar.extractfile('data.txt')
        reader = csv.reader(csv_member.decode('utf-8'))
```

### 5. 진행 추적

진행 표시기가 있는 상세 로깅:

```
2025-01-22 14:30:15 - INFO - 📊 TA (평균기온) 처리 중
2025-01-22 14:30:16 - INFO -   ✅ SSP1-2.6: 10행 삽입됨
2025-01-22 14:30:17 - INFO -   ✅ SSP2-4.5: 10행 삽입됨
2025-01-22 14:30:18 - INFO -   ✅ SSP3-7.0: 10행 삽입됨
2025-01-22 14:30:19 - INFO -   ✅ SSP5-8.5: 10행 삽입됨
2025-01-22 14:30:20 - INFO - ✅ TA 완료 (총: 40행)
```

---

## 설정

### 환경 변수

`.env` 파일에 필수:

```bash
# Datawarehouse 연결
DW_DB_HOST=localhost
DW_DB_PORT=5433
DW_DB_NAME=skala_datawarehouse
DW_DB_USER=skala_dw_user
DW_DB_PASSWORD=안전한_비밀번호

# 데이터 디렉토리
DATA_DIR=../data
LOGS_DIR=../logs

# 로깅
LOG_LEVEL=INFO

# 선택사항: 샘플 모드
SAMPLE_LIMIT=10  # 전체 로드 시 생략
```

---

## 문제 해결

### 문제 1: 연결 오류

```bash
psycopg2.OperationalError: could not connect to server
```

**해결 방법:**
```bash
# Datawarehouse 실행 확인
docker ps | grep skala_datawarehouse

# 연결 테스트
psql -h localhost -p 5433 -U skala_dw_user -d skala_datawarehouse
```

### 문제 2: 메모리 오류

```bash
MemoryError: Unable to allocate array
```

**해결 방법:**
- 스크립트에서 배치 크기 줄이기
- Docker 메모리 증가 (설정 → 리소스 → 메모리: 8GB 이상)
- 테스트에 샘플 모드 사용

### 문제 3: 트랜잭션 오류

```bash
InFailedSqlTransaction: current transaction is aborted
```

**해결 방법:**
```python
# 모든 스크립트에 자동 롤백 포함됨
conn.rollback()  # 트랜잭션 상태 재설정
```

---

## 모범 사례

### 성능 최적화

1. **대량 로드 전 인덱스 삭제:**
```sql
DROP INDEX IF EXISTS idx_ta_data_date;
-- 데이터 로드
CREATE INDEX idx_ta_data_date ON ta_data(observation_date);
```

2. **배치 삽입 사용:**
```python
cursor.executemany("INSERT INTO ...", batch_data)
```

3. **로드 중 자동 커밋 비활성화:**
```python
conn.autocommit = False
# 데이터 로드
conn.commit()
```

### 데이터 검증

로드된 데이터 항상 검증:

```sql
-- 행 개수 확인
SELECT COUNT(*) FROM ta_data;

-- NULL 확인
SELECT COUNT(*) FROM ta_data WHERE value IS NULL;

-- 날짜 범위 확인
SELECT MIN(observation_date), MAX(observation_date) FROM ta_data;
```

---

## 관련 저장소

- **Database Schemas**: [skala-database](https://github.com/your-org/skala-database) - PostgreSQL 스키마
- **FastAPI Backend**: [skala-fastapi](https://github.com/your-org/skala-fastapi) - AI 에이전트 서비스
- **Spring Boot Backend**: [skala-spring](https://github.com/your-org/skala-spring) - 애플리케이션 서비스

---

## 문서

- [SETUP.md](SETUP.md) - 상세 설치 및 구성
- [USAGE.md](USAGE.md) - 일반 사용 사례 및 예시
- [DB Architecture](docs/DB_ARCHITECTURE.md) - 데이터베이스 설계 결정

---

## 기여하기

기여 가이드라인은 [docs/commit_convention.md](docs/commit_convention.md) 및 [docs/branch_convention.md](docs/branch_convention.md)를 참조하세요.

---

## 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 LICENSE 파일을 참조하세요.

---

## 지원

질문이나 문제가 있는 경우:
- 이 저장소에 이슈를 등록하세요
- 설치 도움말은 [SETUP.md](SETUP.md) 확인
- SKALA Physical Risk AI 팀에 문의하세요

---

**SKALA Physical Risk AI Team이 만들었습니다**
