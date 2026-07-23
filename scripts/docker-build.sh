#!/bin/bash

# =============================================================================
# Docker Build Script for Backend AIops
# CI에서 이미지 빌드 및 레지스트리 Push용
# =============================================================================

set -e

# Configuration (환경변수로 오버라이드 가능)
REGISTRY="${REGISTRY:-ghcr.io}"
IMAGE_NAME="${IMAGE_NAME:-backend-aiops}"
TAG="${TAG:-latest}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker is not running"
        exit 1
    fi
    log_info "Docker is running"
}

# Login to registry
login() {
    if [ -z "${REGISTRY_USERNAME}" ] || [ -z "${REGISTRY_PASSWORD}" ]; then
        log_warn "REGISTRY_USERNAME or REGISTRY_PASSWORD not set. Skipping login."
        return 0
    fi

    log_info "Logging in to ${REGISTRY}..."
    echo "${REGISTRY_PASSWORD}" | docker login ${REGISTRY} -u "${REGISTRY_USERNAME}" --password-stdin
    log_info "Login successful"
}

# Build Docker image
build() {
    local repo_lower=$(echo "${GITHUB_REPOSITORY:-local}" | tr '[:upper:]' '[:lower:]')
    local full_image="${REGISTRY}/${repo_lower}/${IMAGE_NAME}:${TAG}"

    log_info "Building Docker image: ${full_image}"

    docker build \
        --tag "${full_image}" \
        --tag "${REGISTRY}/${repo_lower}/${IMAGE_NAME}:latest" \
        --label "org.opencontainers.image.source=https://github.com/${GITHUB_REPOSITORY:-local}" \
        --label "org.opencontainers.image.revision=${GITHUB_SHA:-unknown}" \
        .

    log_info "Build completed: ${full_image}"
}

# Push to registry
push() {
    local repo_lower=$(echo "${GITHUB_REPOSITORY:-local}" | tr '[:upper:]' '[:lower:]')
    local full_image="${REGISTRY}/${repo_lower}/${IMAGE_NAME}:${TAG}"

    log_info "Pushing image: ${full_image}"
    docker push "${full_image}"

    log_info "Pushing latest tag..."
    docker push "${REGISTRY}/${repo_lower}/${IMAGE_NAME}:latest"

    log_info "Push completed"
}

# Full CI build (login + build + push)
ci_build() {
    log_info "Starting CI build process..."
    check_docker
    login
    build
    push
    log_info "CI build completed successfully!"
}

# Local build only (no push)
local_build() {
    log_info "Starting local build..."
    check_docker

    docker build \
        --tag "${IMAGE_NAME}:${TAG}" \
        --tag "${IMAGE_NAME}:latest" \
        .

    log_info "Local build completed: ${IMAGE_NAME}:${TAG}"
}

# Show help
help() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  ci        Full CI build (login + build + push)"
    echo "  local     Local build only (no push)"
    echo "  help      Show this help message"
}

# Main
case "${1:-help}" in
    ci)
        ci_build
        ;;
    local)
        local_build
        ;;
    help|--help|-h)
        help
        ;;
    *)
        log_error "Unknown command: $1"
        help
        exit 1
        ;;
esac
