#!/bin/bash

##############################################################
# ModelOps 통합 빌드 & 배포 스크립트
# 컨테이너 존재 확인 -> 삭제 -> 빌드 -> 실행/배포
##############################################################

set -e  # 에러 발생 시 즉시 중단

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# 로그 함수
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${MAGENTA}[STEP]${NC} $1"
}

# 설정
IMAGE_NAME="polaris-modelops"
CONTAINER_NAME="polaris-modelops-container"
IMAGE_TAG="${1:-latest}"
PORT="${2:-8001}"

# 사용법 출력
usage() {
    echo "사용법: $0 [IMAGE_TAG] [PORT]"
    echo ""
    echo "인자:"
    echo "  IMAGE_TAG    Docker 이미지 태그 (기본값: latest)"
    echo "  PORT         컨테이너 포트 (기본값: 8001)"
    echo ""
    echo "예시:"
    echo "  $0                    # latest 태그, 8001 포트"
    echo "  $0 v1.0.0             # v1.0.0 태그, 8001 포트"
    echo "  $0 v1.0.0 8080        # v1.0.0 태그, 8080 포트"
    echo ""
}

# Docker 설치 확인
check_docker() {
    log_info "Docker 설치 확인 중..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker가 설치되어 있지 않습니다."
        exit 1
    fi

    if ! docker ps &> /dev/null; then
        log_error "Docker 데몬이 실행 중이지 않거나 권한이 없습니다."
        exit 1
    fi

    log_info "Docker 확인 완료 ($(docker --version))"
}

# 기존 컨테이너 확인 및 삭제
cleanup_container() {
    log_step "기존 컨테이너 확인 및 정리"

    # 실행 중인 컨테이너 확인
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_warn "기존 컨테이너 발견: $CONTAINER_NAME"

        # 실행 중이면 중지
        if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
            log_info "컨테이너 중지 중..."
            docker stop "$CONTAINER_NAME"
        fi

        # 컨테이너 삭제
        log_info "컨테이너 삭제 중..."
        docker rm "$CONTAINER_NAME"
        log_info "컨테이너 삭제 완료"
    else
        log_info "기존 컨테이너가 없습니다."
    fi
}

# 기존 이미지 정리 (선택적)
cleanup_old_images() {
    log_info "사용하지 않는 이미지 정리 중..."

    # dangling 이미지 삭제
    if docker images -f "dangling=true" -q | grep -q .; then
        docker image prune -f
        log_info "Dangling 이미지 정리 완료"
    else
        log_info "정리할 이미지가 없습니다."
    fi
}

# Docker 이미지 빌드
build_image() {
    log_step "Docker 이미지 빌드"

    local full_image_name="${IMAGE_NAME}:${IMAGE_TAG}"

    log_info "이미지 빌드 시작: $full_image_name"
    log_info "플랫폼: linux/amd64"

    docker build \
        --platform linux/amd64 \
        --tag "$full_image_name" \
        --file Dockerfile \
        .

    if [ $? -eq 0 ]; then
        log_info "Docker 이미지 빌드 성공!"

        # 이미지 크기 확인
        local image_size=$(docker images "$full_image_name" --format "{{.Size}}")
        log_info "이미지 크기: $image_size"
    else
        log_error "Docker 이미지 빌드 실패"
        exit 1
    fi
}

# 컨테이너 실행
run_container() {
    log_step "컨테이너 실행"

    local full_image_name="${IMAGE_NAME}:${IMAGE_TAG}"

    log_info "컨테이너 실행 시작..."
    log_info "컨테이너 이름: $CONTAINER_NAME"
    log_info "포트 매핑: ${PORT}:8001"

    docker run -d \
        --name "$CONTAINER_NAME" \
        --restart unless-stopped \
        -p "${PORT}:8001" \
        -e PYTHONUNBUFFERED=1 \
        "$full_image_name"

    if [ $? -eq 0 ]; then
        log_info "컨테이너 실행 성공!"
    else
        log_error "컨테이너 실행 실패"
        exit 1
    fi
}

# 컨테이너 상태 확인
check_container_status() {
    log_step "컨테이너 상태 확인"

    # 잠시 대기
    sleep 3

    # 컨테이너 실행 상태 확인
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_info "컨테이너가 정상적으로 실행 중입니다."

        # 컨테이너 상태 정보 출력
        docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"
    else
        log_error "컨테이너가 실행 중이지 않습니다."
        log_error "컨테이너 로그를 확인하세요:"
        docker logs "$CONTAINER_NAME"
        exit 1
    fi
}

# 헬스 체크
health_check() {
    log_step "헬스 체크"

    local health_url="http://localhost:${PORT}/health"
    local max_attempts=10
    local attempt=1

    log_info "헬스 체크 URL: $health_url"

    while [ $attempt -le $max_attempts ]; do
        log_info "헬스 체크 시도 ($attempt/$max_attempts)..."

        if curl -f -s -o /dev/null "$health_url"; then
            log_info "헬스 체크 성공! 서비스가 정상적으로 실행 중입니다."
            return 0
        fi

        if [ $attempt -lt $max_attempts ]; then
            log_warn "헬스 체크 실패. 5초 후 재시도..."
            sleep 5
        fi

        attempt=$((attempt + 1))
    done

    log_warn "헬스 체크 실패. 하지만 컨테이너는 실행 중입니다."
    log_warn "수동으로 확인하세요: $health_url"
    return 1
}

# 배포 정보 출력
print_deployment_info() {
    echo ""
    echo "========================================"
    echo "  배포 완료!"
    echo "========================================"
    echo ""
    echo "컨테이너 이름: $CONTAINER_NAME"
    echo "이미지: ${IMAGE_NAME}:${IMAGE_TAG}"
    echo "포트: $PORT"
    echo ""
    echo "서비스 URL:"
    echo "  http://localhost:${PORT}"
    echo ""
    echo "헬스 체크:"
    echo "  http://localhost:${PORT}/health"
    echo ""
    echo "API 문서:"
    echo "  http://localhost:${PORT}/docs"
    echo "  http://localhost:${PORT}/redoc"
    echo ""
    echo "유용한 명령어:"
    echo "  컨테이너 로그: docker logs -f $CONTAINER_NAME"
    echo "  컨테이너 중지: docker stop $CONTAINER_NAME"
    echo "  컨테이너 재시작: docker restart $CONTAINER_NAME"
    echo "  컨테이너 삭제: docker rm -f $CONTAINER_NAME"
    echo ""
    echo "========================================"
}

# 메인 실행 함수
main() {
    echo ""
    echo "========================================"
    echo "  ModelOps 통합 배포 스크립트"
    echo "========================================"
    echo ""
    log_info "이미지 태그: $IMAGE_TAG"
    log_info "포트: $PORT"
    echo ""

    # Step 1: Docker 확인
    check_docker

    # Step 2: 기존 컨테이너 정리
    cleanup_container

    # Step 3: 사용하지 않는 이미지 정리
    cleanup_old_images

    # Step 4: 이미지 빌드
    build_image

    # Step 5: 컨테이너 실행
    run_container

    # Step 6: 컨테이너 상태 확인
    check_container_status

    # Step 7: 헬스 체크
    if command -v curl &> /dev/null; then
        health_check || true  # 헬스 체크 실패해도 계속 진행
    else
        log_warn "curl이 설치되어 있지 않아 헬스 체크를 건너뜁니다."
    fi

    # Step 8: 배포 정보 출력
    print_deployment_info

    log_info "모든 작업이 완료되었습니다!"
}

# 스크립트 실행
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    usage
    exit 0
fi

main
