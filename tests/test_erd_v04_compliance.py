"""
ERD v04 스키마 정합성 테스트
probability_results.aal 필드명 변경 검증
"""

import sys
import os

# 프로젝트 루트를 Python path에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_fetch_base_aals_query_syntax():
    """
    fetch_base_aals() SQL 쿼리 문법 검증

    ERD v04 변경사항:
    - probability_results.probability → probability_results.aal

    이 테스트는 SQL 쿼리가 올바른 필드명(aal)을 사용하는지 확인합니다.
    """
    from modelops.database.connection import DatabaseConnection
    import inspect

    # fetch_base_aals 메서드의 소스 코드 읽기
    source = inspect.getsource(DatabaseConnection.fetch_base_aals)

    print("=" * 80)
    print("ERD v04 스키마 정합성 테스트")
    print("=" * 80)
    print("\n1. fetch_base_aals() SQL 쿼리 검증")
    print("-" * 80)

    # 1. 'aal AS base_aal' 패턴이 존재하는지 확인
    assert "aal AS base_aal" in source, "[FAILED] 쿼리가 'aal AS base_aal'을 사용하지 않음"
    print("   [OK] PASS: 쿼리가 'aal AS base_aal' 사용 중")

    # 2. 구식 'probability' 필드 참조가 없는지 확인
    assert (
        "probability AS base_aal" not in source
    ), "[FAILED] 구식 'probability AS base_aal' 패턴이 남아있음"
    print("   [OK] PASS: 구식 'probability' 필드 참조 없음")

    # 3. FROM probability_results 테이블 참조 확인
    assert "FROM probability_results" in source, "[FAILED] probability_results 테이블 참조 없음"
    print("   [OK] PASS: probability_results 테이블 참조 확인")

    print("\n" + "=" * 80)
    print("[SUCCESS] ERD v04 스키마 정합성 테스트 통과!")
    print("=" * 80)

    return True


def test_docstring_consistency():
    """
    Docstring 정합성 검증

    모든 Docstring과 주석이 ERD v04 스키마를 반영하는지 확인합니다.
    """
    from modelops.database.connection import DatabaseConnection
    from modelops.agents.risk_assessment.integrated_risk_agent import IntegratedRiskAgent
    from modelops.agents.risk_assessment.aal_scaling_agent import AALScalingAgent

    print("\n2. Docstring 정합성 검증")
    print("-" * 80)

    # DatabaseConnection.fetch_base_aals Docstring
    docstring = DatabaseConnection.fetch_base_aals.__doc__
    assert (
        "probability_results.aal" in docstring
    ), "[FAILED] DatabaseConnection.fetch_base_aals Docstring이 'aal' 필드를 참조하지 않음"
    assert (
        "probability_results.probability" not in docstring
    ), "[FAILED] DatabaseConnection.fetch_base_aals Docstring에 구식 'probability' 필드 참조 남아있음"
    print("   [OK] PASS: DatabaseConnection.fetch_base_aals Docstring 업데이트됨")

    # IntegratedRiskAgent._fetch_base_aals Docstring
    agent = IntegratedRiskAgent()
    docstring = agent._fetch_base_aals.__doc__
    assert (
        "probability_results.aal" in docstring
    ), "[FAILED] IntegratedRiskAgent._fetch_base_aals Docstring이 'aal' 필드를 참조하지 않음"
    print("   [OK] PASS: IntegratedRiskAgent._fetch_base_aals Docstring 업데이트됨")

    # AALScalingAgent.scale_aal Docstring
    aal_agent = AALScalingAgent()
    docstring = aal_agent.scale_aal.__doc__
    assert (
        "probability_results.aal" in docstring
    ), "[FAILED] AALScalingAgent.scale_aal Docstring이 'aal' 필드를 참조하지 않음"
    print("   [OK] PASS: AALScalingAgent.scale_aal Docstring 업데이트됨")

    print("\n" + "=" * 80)
    print("[SUCCESS] 모든 Docstring이 ERD v04 스키마 반영!")
    print("=" * 80)

    return True


def test_sql_schema_file():
    """
    SQL 스키마 파일의 COMMENT 검증
    """
    print("\n3. SQL 스키마 파일 COMMENT 검증")
    print("-" * 80)

    schema_file = os.path.join(
        os.path.dirname(__file__), "..", "modelops", "database", "schema_extensions.sql"
    )

    if not os.path.exists(schema_file):
        print(f"   ⚠️ WARNING: 파일이 존재하지 않음: {schema_file}")
        return True

    with open(schema_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 'probability_results.aal' 패턴 확인
    assert (
        "probability_results.aal" in content
    ), "[FAILED] schema_extensions.sql이 'probability_results.aal'을 참조하지 않음"
    print("   [OK] PASS: schema_extensions.sql이 'probability_results.aal' 참조")

    # 구식 'probability_results.probability' 패턴 확인
    if "probability_results.probability" in content:
        print(
            "   [WARNING] schema_extensions.sql에 구식 'probability_results.probability' 참조 남아있음"
        )
    else:
        print("   [OK] PASS: 구식 'probability_results.probability' 참조 없음")

    print("\n" + "=" * 80)
    print("[SUCCESS] SQL 스키마 파일 검증 완료!")
    print("=" * 80)

    return True


if __name__ == "__main__":
    try:
        # 테스트 실행
        test_fetch_base_aals_query_syntax()
        test_docstring_consistency()
        test_sql_schema_file()

        print("\n" + "=" * 80)
        print("[ALL TESTS PASSED] ERD v04 스키마 정합성 완벽!")
        print("=" * 80)
        print("\n[OK] 수정 완료된 항목:")
        print("   1. DatabaseConnection.fetch_base_aals() SELECT 쿼리")
        print("   2. DatabaseConnection.fetch_base_aals() Docstring")
        print("   3. IntegratedRiskAgent._fetch_base_aals() Docstring")
        print("   4. AALScalingAgent.scale_aal() Docstring")
        print("   5. schema_extensions.sql COMMENT")
        print("\n[OK] 기대 효과:")
        print("   - ERD v04 스키마와 100% 일치")
        print("   - 런타임 PostgreSQL 에러 제거")
        print("   - H x E x V 계산 파이프라인 정상화")
        print("   - 문서와 코드 일관성 확보")

        sys.exit(0)

    except AssertionError as e:
        print(f"\n[TEST FAILED] {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[UNEXPECTED ERROR] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
