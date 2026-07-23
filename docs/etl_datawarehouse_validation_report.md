# ETL-Datawarehouse-README 정합성 검증 보고서

## 검증 개요

**검증 일자**: 2025-12-08
**검증 대상**: ETL 파이프라인 구현과 Datawarehouse 스키마 및 README 문서 간의 정합성
**검증 목적**: README.md에 작성된 ETL 파이프라인 설명이 실제 구현과 일치하는지, 그리고 Datawarehouse.dbml 스키마와 정합하는지 검증

---

## 핵심 발견사항

### ❌ **심각한 불일치 발견**: ModelOps가 의존하는 핵심 기후 지표 데이터가 ETL에서 로드되지 않음

---

## 1. 스크립트 이름 불일치

### README vs 실제 파일

| README 언급 | 실제 파일 | 상태 |
|-------------|----------|------|
| `load_admin_regions.py` | `01_load_admin_regions.py` | ✅ 존재 (이름만 다름) |
| `load_monthly_grid_data.py` | ❌ 없음 | **불일치** |
| `load_yearly_grid_data.py` | ❌ 없음 | **불일치** |
| `load_sea_level_netcdf.py` | `09_load_sea_level.py` | ✅ 존재 (이름만 다름) |

**실제 구조**:
- `08_load_climate_grid.py` - 월별 + 연간 데이터 통합 로더
- 그러나 **극한기후지수(WSDI, CSDI 등)는 로드하지 않음**

---

## 2. Datawarehouse 테이블 vs ETL 로드 정합성

### 2.1 월별 기후 데이터 (Monthly)

| 테이블 | DBML 정의 | ETL 로드 여부 | 상태 |
|--------|-----------|--------------|------|
| `ta_data` (기온) | ~108M rows | ✅ | 정합 |
| `rn_data` (강수량) | ~108M rows | ✅ | 정합 |
| `ws_data` (풍속) | ~108M rows | ✅ | 정합 |
| `rhm_data` (상대습도) | ~108M rows | ✅ | 정합 |
| `si_data` (일사량) | ~108M rows | ❌ | **누락** |
| `spei12_data` (SPEI-12 가뭄지수) | ~108M rows | ❌ | **누락** |

**영향**:
- 산불 위험도 계산: 일사량(si_data) 필요 → ❌ 불가능
- 가뭄 위험도 계산: SPEI-12 필요 → ❌ 불가능

### 2.2 연간 기후 지표 (Yearly) - **치명적 누락**

| 테이블 | DBML 정의 | ETL 로드 여부 | README Hazard Agent 의존성 |
|--------|-----------|--------------|---------------------------|
| `ta_yearly_data` | ~9M rows | ✅ | - |
| `wsdi_data` (폭염지수) | ~9M rows | ❌ | **ExtremeHeatHScoreAgent** |
| `csdi_data` (한파지수) | ~9M rows | ❌ | **ExtremeColdHScoreAgent** |
| `rx1day_data` (1일 최다강수) | ~9M rows | ❌ | **UrbanFloodHScoreAgent** |
| `rx5day_data` (5일 최다강수) | ~9M rows | ❌ | **RiverFloodHScoreAgent** |
| `cdd_data` (연속무강수일) | ~9M rows | ❌ | **DroughtHScoreAgent** |
| `rain80_data` (80mm↑ 강수일) | ~9M rows | ❌ | **FloodHScoreAgent** |
| `sdii_data` (강수강도) | ~9M rows | ❌ | **FloodHScoreAgent** |

**08_load_climate_grid.py 코드 분석**:

```python
# 157-162줄: 월별 데이터만 매핑
table_var_map = {
    'ta_data': ['ta', 'TA'],
    'rn_data': ['rn', 'RN'],
    'rhm_data': ['rhm', 'RHM'],
    'ws_data': ['ws', 'WS'],
}
# ❌ WSDI, CSDI, RX1DAY 등 극한지수 없음
# ❌ SI (일사량), SPEI12 (가뭄지수) 없음

# 273-335줄: 연간 데이터 - ta_yearly_data만 로드
for table_name in yearly_tables:
    if table_name != 'ta_yearly_data':
        continue  # ❌ 다른 연간 지표 스킵
```

**영향**: README에 명시된 9개 Hazard Agent 중 **6개 에이전트가 작동 불가능**
- ExtremeHeatHScoreAgent (WSDI 필요)
- ExtremeColdHScoreAgent (CSDI 필요)
- RiverFloodHScoreAgent (RX5DAY 필요)
- UrbanFloodHScoreAgent (RX1DAY 필요)
- DroughtHScoreAgent (CDD 필요)
- WildfireHScoreAgent (SI 일부 필요)

### 2.3 격자 데이터 해상도 오류

| 항목 | DBML/README 기대값 | 실제 ETL 구현 | 비고 |
|------|-------------------|--------------|------|
| **해상도** | 0.01° | 0.05° | **5배 차이** |
| **격자 수** | 451,351개 (601×751) | ~18,000개 (추정) | **25배 적음** |

**08_load_climate_grid.py 139줄**:
```python
for lat_px in range(lat_start, lat_end, 5):  # ❌ 5 픽셀 간격
    for lon_px in range(lon_start, lon_end, 5):
```

**영향**:
- 고해상도 격자 분석 불가
- README 명시 "451,351개 격자"는 현재 불가능
- 공간 분석 정밀도 1/25 수준

---

## 3. 데이터베이스 포트 기본값 불일치

| 위치 | 포트 값 | 상태 |
|------|---------|------|
| README.md | 5433 | ✅ |
| .env.example | 5433 | ✅ |
| `ETL/local/scripts/utils.py` | 5434 (default) | ❌ 불일치 |

**utils.py 75줄**:
```python
port=os.getenv("DW_DB_PORT", "5434"),  # ❌ 기본값 5434
```

**영향**: 환경변수 미설정 시 DB 연결 실패

---

## 4. 행 수 불일치

| 테이블 | DBML | README | 비율 |
|--------|------|--------|------|
| `ta_data` | ~108M | 433M | 4배 차이 |
| `rn_data` | ~108M | 433M | 4배 차이 |
| `wsdi_data` | ~9M | 36M | 4배 차이 |
| `sea_level_data` | ~1,720 | 6,880 | 4배 차이 |

**원인 추정**: README는 4개 시나리오(SSP1/2/3/5) 합산 기준 작성
**정확한 기준**: DBML이 정확 (시나리오별 컬럼으로 저장, 행은 격자×연도만큼 생성)

---

## 5. 심각도 분석

### P0 (긴급) - 시스템 동작 불가

#### 1. 극한기후지수 미구현 (WSDI, CSDI, RX1DAY, RX5DAY, CDD, RAIN80, SDII)
- **영향**: 9개 Hazard Agent 중 6개 작동 불가
- **원인**: `08_load_climate_grid.py`가 월별 데이터(ta, rn, ws, rhm)만 로드
- **조치**: 연간 극한지수 로더 추가 또는 기존 스크립트 확장 필요

#### 2. 격자 해상도 오류 (0.01° → 0.05°)
- **영향**: 451,351개 예상 → ~18,000개만 생성 (25배 부족)
- **원인**: `08_load_climate_grid.py:139` 샘플링 로직
- **조치**: 샘플링 제거 또는 README 수정

### P1 (높음) - 부분 기능 손상

#### 3. 산불/가뭄 지표 누락 (si_data, spei12_data)
- **영향**: WildfireHScoreAgent, DroughtHScoreAgent 일부 지표 미활용
- **조치**: si, spei12 변수 매핑 추가

#### 4. DB 포트 기본값 불일치
- **영향**: 환경변수 미설정 시 연결 실패
- **조치**: `utils.py` 기본값 5434 → 5433 수정

### P2 (중) - 문서 신뢰성

#### 5. 행 수 불일치
- **영향**: 문서와 실제 데이터 규모 혼란
- **조치**: DBML 기준으로 README 수정

---

## 6. 원인 분석

### 왜 이런 불일치가 발생했는가?

#### 1. ETL 스크립트 통합 과정에서 누락
- 원래 `load_monthly_grid_data.py`, `load_yearly_grid_data.py` 분리 예정
- → `load_climate_grid.py`로 통합하면서 연간 극한지수 로더 누락

#### 2. README 작성 시점과 코드 작성 시점 불일치
- README는 완성된 시스템 기준 작성
- 실제 ETL은 부분 구현만 완료

#### 3. physical_risk_module_core_merge 통합 미완료
- `merge_progress.md`에 따르면 Hazard Agent는 통합 완료
- 그러나 해당 Agent가 필요로 하는 **ETL 데이터 로더는 미통합**

#### 4. 샘플링 로직 의도 불명확
- 성능 테스트용 샘플링인지, 프로덕션 로직인지 명확하지 않음
- 문서에는 전체 격자 로드가 명시되어 있음

---

## 7. 권장 조치사항

### 즉시 조치 (코드 수정)

#### 1. `08_load_climate_grid.py` 확장

**월별 데이터 매핑 추가** (157-162줄):
```python
table_var_map = {
    'ta_data': ['ta', 'TA'],
    'rn_data': ['rn', 'RN'],
    'rhm_data': ['rhm', 'RHM'],
    'ws_data': ['ws', 'WS'],
    'si_data': ['si', 'SI'],         # ✅ 추가
    'spei12_data': ['spei12', 'SPEI12'],  # ✅ 추가
}
```

**연간 데이터 로드 로직 확장** (273-335줄):
```python
yearly_tables = ['wsdi_data', 'csdi_data', 'rx1day_data', 'rx5day_data',
                 'cdd_data', 'rain80_data', 'sdii_data', 'ta_yearly_data']

# ✅ 모든 테이블에 대해 로드 로직 구현
for table_name in yearly_tables:
    # continue 문 제거
    # 각 테이블별 변수 매핑 추가
    if table_name == 'wsdi_data':
        var_names = ['wsdi', 'WSDI']
    elif table_name == 'csdi_data':
        var_names = ['csdi', 'CSDI']
    elif table_name == 'rx1day_data':
        var_names = ['rx1day', 'RX1DAY']
    # ... (나머지 테이블 매핑)
```

#### 2. 격자 샘플링 제거 (139줄)

```python
# ❌ 변경 전
for lat_px in range(lat_start, lat_end, 5):
    for lon_px in range(lon_start, lon_end, 5):

# ✅ 변경 후
for lat_px in range(lat_start, lat_end, 1):
    for lon_px in range(lon_start, lon_end, 1):
```

**주의사항**: 전체 격자 로드 시 처리 시간 및 메모리 사용량 크게 증가 예상

#### 3. DB 포트 기본값 수정

**`ETL/local/scripts/utils.py` 75줄**:
```python
# ❌ 변경 전
port=os.getenv("DW_DB_PORT", "5434"),

# ✅ 변경 후
port=os.getenv("DW_DB_PORT", "5433"),
```

### 문서 수정

#### 1. README 스크립트 이름 업데이트

```markdown
# ❌ 변경 전
python scripts/load_monthly_grid_data.py
python scripts/load_yearly_grid_data.py
python scripts/load_sea_level_netcdf.py

# ✅ 변경 후
python scripts/08_load_climate_grid.py       # 월별/연간 통합
python scripts/09_load_sea_level.py
```

#### 2. 행 수 수정 (DBML 기준)

| 테이블 | 변경 전 (README) | 변경 후 (DBML 기준) |
|--------|-----------------|-------------------|
| `ta_data` | 433M | ~108M |
| `rn_data` | 433M | ~108M |
| `wsdi_data` | 36M | ~9M |
| `sea_level_data` | 6,880 | ~1,720 |

#### 3. 격자 수 명시 명확화

**현재**:
```markdown
- 0.01° 해상도, 451,351개 격자
```

**수정 옵션 1** (샘플링 제거 후):
```markdown
- 0.01° 해상도, 451,351개 격자 (601×751)
```

**수정 옵션 2** (샘플링 유지 시):
```markdown
- 0.05° 해상도 (샘플링), ~18,000개 격자
- 성능 테스트용 설정 (프로덕션: 0.01°, 451,351개)
```

---

## 8. 다음 단계 제안

### 1단계: 긴급 수정 (P0)
- [ ] `08_load_climate_grid.py`에 극한기후지수 로더 추가
- [ ] 격자 샘플링 제거 또는 문서 명확화
- [ ] 통합 테스트 실행 (전체 격자 로드 시간 측정)

### 2단계: 기능 보완 (P1)
- [ ] si_data, spei12_data 매핑 추가
- [ ] DB 포트 기본값 수정
- [ ] ETL 실행 후 행 수 검증

### 3단계: 문서 정비 (P2)
- [ ] README 스크립트 이름 업데이트
- [ ] 행 수 기댓값 수정 (DBML 기준)
- [ ] ETL 실행 가이드 보완

### 4단계: 시스템 검증
- [ ] 9개 Hazard Agent별 입력 데이터 검증
- [ ] Exposure/Vulnerability Agent 데이터 의존성 확인
- [ ] End-to-End 통합 테스트

---

## 9. 검증 요약

### 현재 상태
❌ **ETL 파이프라인이 Datawarehouse 스키마 및 ModelOps Agent 요구사항을 충족하지 못함**

### 핵심 문제
1. README에 명시된 Hazard 계산에 필요한 **핵심 기후지표(WSDI, CSDI 등) 7개가 ETL에서 로드되지 않음**
2. 격자 해상도가 예상의 1/5 수준 (0.05° vs 0.01°)
3. 문서와 코드 간 불일치로 인한 혼란
4. 데이터베이스 연결 설정 불일치

### 시급성
- **P0 문제 2건**: 시스템 핵심 기능 동작 불가
- **P1 문제 2건**: 부분 기능 손상
- **P2 문제 1건**: 문서 신뢰성 저하

### 권장 우선순위
1. 극한기후지수 로더 구현 (ExtremeHeat, ExtremeCold 등 6개 Agent 활성화)
2. 격자 해상도 정책 결정 (샘플링 제거 vs 문서 수정)
3. 문서 정비 및 통합 테스트

---

## 부록: 영향받는 Agent 목록

| Agent | 필요 데이터 | ETL 로드 여부 | 작동 가능 여부 |
|-------|------------|--------------|---------------|
| ExtremeHeatHScoreAgent | WSDI, ta_data | ❌ WSDI 누락 | ❌ 불가능 |
| ExtremeColdHScoreAgent | CSDI, ta_data | ❌ CSDI 누락 | ❌ 불가능 |
| DroughtHScoreAgent | CDD, SPEI-12 | ❌ 모두 누락 | ❌ 불가능 |
| RiverFloodHScoreAgent | RX5DAY, rn_data | ❌ RX5DAY 누락 | ❌ 불가능 |
| UrbanFloodHScoreAgent | RX1DAY, rn_data | ❌ RX1DAY 누락 | ❌ 불가능 |
| WildfireHScoreAgent | si_data, ta_data, rn_data | ❌ SI 누락 | ⚠️ 부분 가능 |
| TyphoonHScoreAgent | ws_data, rn_data | ✅ 모두 로드 | ✅ 가능 |
| SeaLevelRiseHScoreAgent | sea_level_data | ✅ 로드 | ✅ 가능 |
| WaterStressHScoreAgent | rn_data | ✅ 로드 | ✅ 가능 |

**작동 가능 Agent**: 3/9 (33%)
**작동 불가능 Agent**: 6/9 (67%)

---

**보고서 작성자**: Claude (AI Assistant)
**최종 업데이트**: 2025-12-08
**문서 버전**: 1.0
