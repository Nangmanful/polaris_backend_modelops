#!/bin/bash

# =============================================================================
# Docker Deploy Script for Backend AIops
# =============================================================================

set -e

# Configuration
IMAGE_NAME="backend-aiops"
CONTAINER_NAME="backend-aiops"
ENV_FILE=".env"

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
        log_error "Docker is not running. Please start Docker first."
        exit 1
    fi
    log_info "Docker is running"
}

# Build Docker image
build() {
    log_info "Building Docker image: ${IMAGE_NAME}..."
    docker build -t ${IMAGE_NAME}:latest .
    log_info "Build completed successfully"
}

# Stop and remove existing container
stop() {
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_info "Stopping existing container: ${CONTAINER_NAME}..."
        docker stop ${CONTAINER_NAME} 2>/dev/null || true
        docker rm ${CONTAINER_NAME} 2>/dev/null || true
        log_info "Container stopped and removed"
    else
        log_info "No existing container found"
    fi
}

# Run container
run() {
    log_info "Starting container: ${CONTAINER_NAME}..."

    # Check if .env file exists
    ENV_OPTION=""
    if [ -f "${ENV_FILE}" ]; then
        ENV_OPTION="--env-file ${ENV_FILE}"
        log_info "Using environment file: ${ENV_FILE}"
    else
        log_warn "No .env file found. Running without environment file."
    fi

    docker run -d \
        --name ${CONTAINER_NAME} \
        ${ENV_OPTION} \
        --restart unless-stopped \
        ${IMAGE_NAME}:latest

    log_info "Container started"
}

# Show logs
logs() {
    log_info "Showing logs for ${CONTAINER_NAME}..."
    docker logs -f ${CONTAINER_NAME}
}

# Show status
status() {
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_info "Container ${CONTAINER_NAME} is running"
        docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.ID}}\t{{.Status}}"
    else
        log_warn "Container ${CONTAINER_NAME} is not running"
    fi
}

# Full deploy (build + stop + run)
deploy() {
    log_info "Starting full deployment..."
    check_docker
    build
    stop
    run
    log_info "Deployment completed successfully!"
    status
}

# Show help
help() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  deploy    Full deployment (build + stop + run)"
    echo "  build     Build Docker image only"
    echo "  stop      Stop and remove container"
    echo "  run       Run container"
    echo "  logs      Show container logs"
    echo "  status    Show container status"
    echo "  help      Show this help message"
}

# Main
case "${1:-deploy}" in
    deploy)
        deploy
        ;;
    build)
        check_docker
        build
        ;;
    stop)
        check_docker
        stop
        ;;
    run)
        check_docker
        run
        ;;
    logs)
        logs
        ;;
    status)
        status
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
