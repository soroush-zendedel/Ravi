#!/bin/sh
#
# build-image.sh – One-command offline build of the Ravi Ollama CPU image
#
# What it does:
#   1. (Optional) Loads local/debian/ubuntu-26.04.tar if the base
#      image is not already present in Docker.
#   2. Checks that local/debs/ and local/ollama/ contain the required assets.
#   3. Runs: docker build -t ravi-ollama:cpu -f docker/Dockerfile.ollama-cpu .
#
# Usage:
#   ./scripts/build-image.sh
#   ./scripts/build-image.sh --force          # rebuild even if image exists
#   ./scripts/build-image.sh --no-load        # skip base-image load step
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

IMAGE_NAME="ravi-ollama:cpu"
DOCKERFILE="docker/Dockerfile.ollama-cpu"
BASE_TAR="local/debian/ubuntu-26.04.tar"
BASE_IMAGE="ubuntu:26.04"

FORCE=0
NO_LOAD=0

info()  { echo "[*] $*"; }
warn()  { echo "[!] $*" >&2; }
error() { echo "[ERROR] $*" >&2; exit 1; }
step()  { echo; echo "==> $*"; }

usage() {
    cat << USAGE
Usage: $(basename "$0") [OPTIONS]

Build the offline CPU-only Ollama image used by Ravi.

Options:
  --force       Rebuild even if the image already exists
  --no-load     Do not attempt to load the base image tarball
  -h, --help    Show this help
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        --force)   FORCE=1; shift ;;
        --no-load) NO_LOAD=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) error "Unknown option: $1" ;;
    esac
done

# Detect docker or docker.exe (WSL / Docker Desktop)
DOCKER_CMD=""
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER_CMD="docker"
elif command -v docker.exe >/dev/null 2>&1 && docker.exe info >/dev/null 2>&1; then
    DOCKER_CMD="docker.exe"
elif command -v docker >/dev/null 2>&1; then
    DOCKER_CMD="docker"
elif command -v docker.exe >/dev/null 2>&1; then
    DOCKER_CMD="docker.exe"
else
    error "docker not found (tried docker and docker.exe)"
fi
docker() { DOCKER_CLI_HINTS=false command "$DOCKER_CMD" "$@"; }
info "Using Docker command: $DOCKER_CMD"

# ------------------------------------------------------------------
# 1. Load base image if needed
# ------------------------------------------------------------------
if [ "$NO_LOAD" -eq 0 ]; then
    if docker image inspect "$BASE_IMAGE" >/dev/null 2>&1; then
        info "Base image $BASE_IMAGE is already present."
    else
        if [ -f "$BASE_TAR" ] && [ -s "$BASE_TAR" ]; then
            step "Loading base image from $BASE_TAR"
            docker load -i "$BASE_TAR"
        else
            warn "Base image $BASE_IMAGE is missing and $BASE_TAR was not found."
            warn "If you have internet you can pull it: docker pull $BASE_IMAGE"
            warn "Or place a saved tarball at $BASE_TAR"
        fi
    fi
fi

# ------------------------------------------------------------------
# 2. Sanity checks for required assets
# ------------------------------------------------------------------
step "Checking build assets"

if [ -z "$(ls -A local/debs/*.deb 2>/dev/null)" ]; then
    error "No .deb files in local/debs/.
Run first:
  ./scripts/fetch-debs.sh --mirror http://archive.ubuntu.com/ubuntu --suite resolute --no-security"
fi
info "Found $(ls local/debs/*.deb | wc -l) packages in local/debs/"

TARBALL=$(ls local/ollama/ollama-cpu-build*.tar.gz local/ollama/ollama-cpu-build*.tgz 2>/dev/null | head -n1 || true)
if [ -z "$TARBALL" ]; then
    error "No ollama-cpu-build*.tar.gz found in local/ollama/.
Place the pre-built CPU tarball there."
fi
info "Using Ollama package: $(basename "$TARBALL")"

# ------------------------------------------------------------------
# 3. Build
# ------------------------------------------------------------------
if [ "$FORCE" -eq 0 ] && docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    info "Image $IMAGE_NAME already exists. Use --force to rebuild."
    docker images "$IMAGE_NAME"
    exit 0
fi

step "Building $IMAGE_NAME"
docker build -t "$IMAGE_NAME" -f "$DOCKERFILE" .

echo
echo "============================================================"
info "Build finished successfully."
echo
info "Image : $IMAGE_NAME"
docker images "$IMAGE_NAME"
echo
info "You can now run:"
echo "  sudo ./install.sh"
echo "  ravi install"
echo "============================================================"
echo
