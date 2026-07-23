# New ETL Pipeline 계획

## 개요
기존 etl/local과 etl/api 스크립트들을 통합하고, 울산/SK 사업장 특화 데이터 수집 파이프라인 구성

---

## 파일 구조

```
new_etl/
├── todo.md                         # 이 문서
├── utils.py                        # 공통 유틸리티 (기존 utils 통합)
├── 01_run_all_etl.py              # 기본 전체 ETL 실행
├── 02_load_climate_geocode.py     # 울산 격자 기후 + 역지오코딩
└── 03_load_buildings.py           # 건축물대장 (사용자 입력 기반)
```

---

## 1. 01_run_all_etl.py

### 목적
- Local + API 데이터를 한번에 전체 적재
- 제외 항목:
  - load_climate_grid (02번으로 이동)
  - load_vworld_geocode (02번으로 이동)
  - load_buildings (03번으로 이동)

### 포함 스크립트

#### Local 데이터 (파일 기반)
| # | 스크립트 | 설명 | 테이블 |
|---|---------|------|--------|
| 1 | load_admin_regions | 행정구역 경계 | location_admin |
| 2 | load_weather_stations | 기상관측소 | weather_stations |
| 3 | load_grid_station_mappings | 그리드-관측소 매핑 | grid_station_mappings |
| 4 | load_population | 인구 전망 | location_admin (UPDATE) |
| 5 | load_landcover | 토지피복 | raw_landcover |
| 6 | load_dem | 수치표고모델 | raw_dem |
| 7 | load_drought | 가뭄 지수 | raw_drought |
| ~~8~~ | ~~load_climate_grid~~ | ~~기후 그리드~~ | ~~제외 - 02번으로 이동~~ |
| 9 | load_sea_level | 해수면 상승 | sea_level_data |
| 10 | load_water_stress | 수자원 스트레스 | water_stress_rankings |
| 11 | load_site_data | 사이트 추가 데이터 | site_additional_data |

#### API 데이터 (실시간 호출)
| # | 스크립트 | 설명 | 테이블 |
|---|---------|------|--------|
| 1 | load_river_info | 하천정보 | api_river_info |
| 2 | load_emergency_messages | 재난문자 | api_emergency_messages |
| ~~3~~ | ~~load_vworld_geocode~~ | ~~역지오코딩~~ | ~~제외 - 02번으로 이동~~ |
| 4 | load_typhoon | 태풍 정보 | api_typhoon_* |
| 5 | load_wamis | WAMIS 용수이용량 | api_wamis, api_wamis_stations |
| ~~6~~ | ~~load_buildings~~ | ~~건축물대장~~ | ~~제외 - 03번으로 이동~~ |
| 15 | load_disaster_yearbook | 재해연보 | api_disaster_yearbook |
| 16 | load_typhoon_besttrack | 태풍 베스트트랙 | api_typhoon_besttrack |

### 실행 방법
```bash
python 01_run_all_etl.py              # 전체 실행
python 01_run_all_etl.py --local-only # Local만 실행
python 01_run_all_etl.py --api-only   # API만 실행
python 01_run_all_etl.py --only 1,2,3 # 특정 단계만
```

---

## 2. 02_load_climate_geocode.py

### 목적
- 울산 지역 1km 격자 중 1,000개 선별 + SK 사업장 위치
- 기후 데이터 적재 + VWorld 역지오코딩

### 처리 로직
1. 울산 행정경계 내 1km 격자 생성
2. 격자 중 1,000개 균등 샘플링 또는 주요 지점 선택
3. SK 사업장 좌표 추가 (고정 또는 입력)
4. KMA SSP 시나리오별 기후 데이터 적재
5. 각 격자/사업장 좌표에 대해 VWorld 역지오코딩 수행

### SK 사업장 좌표 (예시)
```python
SK_SITES = [
    {"name": "SK에너지 울산CLX", "lat": 35.5019, "lon": 129.3714},
    {"name": "SK지오센트릭", "lat": 35.5045, "lon": 129.3821},
    {"name": "SK인천석유화학", "lat": 37.4857, "lon": 126.6214},
]
```

### 대상 테이블
- location_grid (울산 격자)
- ta_data, rn_data (월별 기온/강수)
- ta_yearly_data (연간 기온)
- api_vworld_geocode (역지오코딩 결과)

### 실행 방법
```bash
python 02_load_climate_geocode.py                   # 기본 실행 (울산 1000격자 + SK사업장)
python 02_load_climate_geocode.py --grid-count 500  # 격자 수 조절
python 02_load_climate_geocode.py --sk-sites-only   # SK 사업장만
python 02_load_climate_geocode.py --skip-geocode    # 역지오코딩 생략
```

---

## 3. 03_load_buildings.py

### 목적
- 사용자 입력 변수에 따라 건축물대장 조회
- 온디맨드 방식으로 필요한 위치만 API 호출
- 02번에서 생성된 역지오코딩 결과 활용 가능

### 입력 방식
1. 좌표 입력: 위도/경도 (02번 역지오코딩 결과 참조)
2. 시군구코드/법정동코드 직접 입력
3. CSV 파일: 여러 위치 일괄 처리
4. SK 사업장: 미리 정의된 사업장 목록

### 처리 플로우
```
[입력] 좌표 또는 시군구코드/법정동코드
    |
[DB 조회] api_vworld_geocode에서 코드 확인
    |
[건축물대장 API] 표제부 조회
    |
[DB 저장] building_aggregate_cache
```

### 대상 테이블
- building_aggregate_cache (건축물 집계 캐시)

### 실행 방법
```bash
python 03_load_buildings.py --lat 35.5019 --lon 129.3714  # 좌표 기반 (geocode DB 참조)
python 03_load_buildings.py --sigungu 31110 --bjdong 10100  # 코드 직접 입력
python 03_load_buildings.py --csv locations.csv  # CSV 일괄
python 03_load_buildings.py --sk-sites  # SK 사업장 전체
```

---

## 환경 변수

```bash
# 데이터베이스
DW_DB_HOST=localhost
DW_DB_PORT=5555
DW_DB_NAME=datawarehouse
DW_DB_USER=skala
DW_DB_PASSWORD=skala1234

# 데이터 디렉토리
DATA_DIR=./data

# API 키
RIVER_API_KEY=xxxx
EMERGENCYMESSAGE_API_KEY=xxxx
TYPHOON_API_KEY=xxxx
VWORLD_API_KEY=xxxx
PUBLICDATA_API_KEY=xxxx

# 샘플 제한 (테스트용)
SAMPLE_LIMIT=5
```

---

## 구현 순서

- [ ] 1. utils.py - 공통 유틸리티 통합
- [ ] 2. 01_run_all_etl.py - 기본 전체 ETL
- [ ] 3. 02_load_climate_geocode.py - 울산 격자 기후 + 역지오코딩
- [ ] 4. 03_load_buildings.py - 건축물대장 (온디맨드)

---

## 참고
- 기존 스크립트 위치: etl/local/scripts/, etl/api/scripts/after_commit/
- 스키마: schema.sql 참조
