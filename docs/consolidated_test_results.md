# 통합 테스트 결과 보고서 (Consolidated Test Results Report)

이 문서는 이전에 요청된 모든 테스트 시나리오의 실행 결과를 종합하여 정리한 리포트입니다.

---

## 1. 시나리오: TS_BE_ScoringLogic_17 (리스크 산출 로직 검증)

- **테스트 파일**: `TS_BE_ScoringLogic_17/test_scoring_logic.py`
- **종합 결과**: **7개 테스트 케이스 모두 통과 (7 passed)**

| ID | 테스트 케이스명 | 예상 결과 | 실제 결과 (로그 요약) |
|:---|:---|:---:|:---|
| **TC_001** | AAL 산출식 정확도 | **PASS** | `INFO:__main__:[TC_001] 기댓값: 4000000000.0, 계산값: 4000000000.0` |
| **TC_002** | 스코어 정규화 (0-100) | **PASS** | `INFO:__main__:[TC_002] 정규화 결과: [Decimal('0'), Decimal('50'), ...]` |
| **TC_003** | 제로 리스크 처리 | **PASS** | `INFO:__main__:[TC_003] 제로 리스크 계산 결과: 0` |
| **TC_004** | 필수 데이터 누락 대응 | **PASS** | `INFO:__main__:[TC_004] 예외 발생 확인: ValueError, 'Asset Value is required'` |
| **TC_005** | 민감도 분석 검증 | **PASS** | `INFO:__main__:[TC_005] ... 변화율: 1.2` (기대치와 일치) |
| **TC_006** | 공식 주입 공격 차단 | **PASS** | `INFO:__main__:[TC_006] 인젝션 시도에 대한 응답: {'status': 400, 'error': 'Bad Request'}` |
| **TC_007** | 연산 정밀도(Precision) | **PASS** | `INFO:__main__:[TC_007] DB 저장값: 0.1082, 기댓값: 0.1082` |

---

## 2. 시나리오: TS_BE_TimeSeries_18 (시계열 리스크 트렌드 분석)

- **테스트 파일**: `TS_BE_TimeSeries_18/test_timeseries_analysis.py`
- **종합 결과**: **6개 테스트 케이스 모두 통과 (6 passed)**

| ID | 테스트 케이스명 | 예상 결과 | 실제 결과 (로그 요약) |
|:---|:---|:---:|:---|
| **TC_001** | 응답 데이터 구조 검증 | **PASS** | `INFO:__main__:[TC_001] 응답 데이터 구조 및 타입 검증 완료.` |
| **TC_002** | 변곡점 식별 정확성 | **PASS** | `INFO:__main__:[TC_002] ... 결과: {'inflection_points': [2040]}` |
| **TC_003** | 변곡점 미발생 케이스 | **PASS** | `INFO:__main__:[TC_003] ... 결과: {'inflection_points': []}` |
| **TC_004** | 예측 기간(Horizon) 검증 | **PASS** | `INFO:__main__:[TC_004] 마지막 예측 연도: 2045, 최소 기대 연도: 2045` |
| **TC_005** | 데이터 부족 상황 대응 | **PASS** | `INFO:__main__:[TC_005] 데이터 부족 시 응답 생성 확인 ...` |
| **TC_006** | 데이터 무결성 (0-100) | **PASS** | `INFO:__main__:[TC_006] 모든 스코어(0-100) 유효성 검증 결과: True` |

---

## 3. 시나리오: TS_CICD_Backend_RDB_66 (DB 스키마 마이그레이션 자동화)

- **관련 파일**: `TS_CICD_Backend_RDB_66/`
- **종합 결과**: **4개 시나리오 모두 개념 증명 및 예상 결과 달성**

| ID | 테스트 케이스명 | 예상 결과 | 실제 결과 (시뮬레이션 로그 요약) |
|:---|:---|:---:|:---|
| **TC_001** | 신규 컬럼 추가 검증 | **PASS** | `INFO:__main__:--- TC_001 검증 성공 ---` |
| **TC_002** | 데이터 유실 차단 | **PASS** | `[FATAL] ABORTING MIGRATION! ... table 'users' which contains data.` (위험 감지 후 파이프라인 중단 성공) |
| **TC_003** | 스키마 롤백(Rollback) | **PASS** | `INFO:__main__:--- TC_003 검증 성공 ---` |
| **TC_004** | 민감 정보 노출 방지 | **PASS** | `Running migration command (e.g., flyway migrate -user=test_user -password=***)...` (비밀번호가 `***`로 마스킹됨) |
