#!/bin/sh
#
# install.sh – Install the Ravi AI CLI, ensure the Ollama image is ready,
#              and start the managed container.
#
# What it does:
#   1. Copies the CLI and libraries to /usr/lib/ravi and creates /usr/bin/ravi
#   2. Prepares /usr/share/ravi for offline image packages
#   3. If the image "ravi-ollama:cpu" is missing, tries to load or build it
#   4. Starts the Ollama container (same as "ravi install")
#

set -e

INSTALL_LIB="/usr/lib/ravi"
SHARE_DIR="/usr/share/ravi"
BIN_PATH="/usr/bin/ravi"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IMAGE_NAME="ravi-ollama:cpu"
DOCKERFILE="$SCRIPT_DIR/docker/Dockerfile.ollama-cpu"
BASE_IMAGE="ubuntu:26.04"
BASE_TAR="$SCRIPT_DIR/local/debian/ubuntu-26.04.tar"

info()  { echo "[*] $*"; }
warn()  { echo "[!] $*" >&2; }
error() { echo "[ERROR] $*" >&2; exit 1; }
step()  { echo; echo "==> $*"; }

# ------------------------------------------------------------------
# 1. Install CLI
# ------------------------------------------------------------------
step "Installing Ravi CLI"

mkdir -p "$INSTALL_LIB/lib"
mkdir -p "$SHARE_DIR"

cp "$SCRIPT_DIR/tools/ravi/ravi" "$INSTALL_LIB/ravi"
cp "$SCRIPT_DIR/tools/ravi/lib/"*.sh "$INSTALL_LIB/lib/"

chmod +x "$INSTALL_LIB/ravi"
ln -sf "$INSTALL_LIB/ravi" "$BIN_PATH"

# Copy any real (non-empty) image packages from local/ into the system share dir
if [ -d "$SCRIPT_DIR/local" ]; then
    for f in "$SCRIPT_DIR/local"/*.tar "$SCRIPT_DIR/local"/*.tar.gz; do
        [ -e "$f" ] || continue
        if [ -s "$f" ]; then
            info "Copying $(basename "$f") → $SHARE_DIR/"
            cp "$f" "$SHARE_DIR/"
        fi
    done
fi

info "CLI installed:"
info "  Binary : $BIN_PATH"
info "  Share  : $SHARE_DIR"

# ------------------------------------------------------------------
# 2. Ensure Docker is available
# ------------------------------------------------------------------
find_docker() {
    if command -v docker >/dev/null 2>&1; then
        if docker info >/dev/null 2>&1; then
            echo "docker"
            return 0
        fi
    fi

    if command -v docker.exe >/dev/null 2>&1; then
        if docker.exe info >/dev/null 2>&1; then
            echo "docker.exe"
            return 0
        fi
    fi

    for candidate in \
        "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" \
        "/mnt/c/Program Files/Docker/Docker/resources/docker.exe" \
        "/usr/bin/docker.exe" \
        "/usr/local/bin/docker.exe"
    do
        if [ -x "$candidate" ]; then
            if "$candidate" info >/dev/null 2>&1; then
                echo "$candidate"
                return 0
            fi
        fi
    done

    for candidate in \
        /mnt/c/Users/*/AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe \
        /mnt/c/Users/*/AppData/Local/Docker/bin/docker.exe
    do
        if [ -x "$candidate" ]; then
            if "$candidate" info >/dev/null 2>&1; then
                echo "$candidate"
                return 0
            fi
        fi
    done

    if command -v docker >/dev/null 2>&1; then
        echo "docker"
        return 0
    fi
    if command -v docker.exe >/dev/null 2>&1; then
        echo "docker.exe"
        return 0
    fi
    return 1
}

DOCKER_CMD=$(find_docker || true)

if [ -z "$DOCKER_CMD" ]; then
    warn "Docker not found – CLI is installed, but the service was not started."
    warn "Install Docker Desktop (WSL) or Docker, then run: ravi install"
    exit 0
fi

if ! "$DOCKER_CMD" info >/dev/null 2>&1; then
    warn "Docker daemon not reachable via $DOCKER_CMD – service not started."
    warn "Start Docker Desktop, then run: ravi install"
    exit 0
fi

info "Using Docker command: $DOCKER_CMD"
docker() { DOCKER_CLI_HINTS=false command "$DOCKER_CMD" "$@"; }

# ------------------------------------------------------------------
# 3. Ensure image exists (load or build if needed)
# ------------------------------------------------------------------
if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    step "Image $IMAGE_NAME not found – trying to prepare it"

    for img in "$SHARE_DIR"/*.tar "$SHARE_DIR"/*.tar.gz \
               "$SCRIPT_DIR/local"/*.tar "$SCRIPT_DIR/local"/*.tar.gz; do
        [ -e "$img" ] || continue
        [ -s "$img" ] || continue
        case "$(basename "$img")" in
            ubuntu-*.tar|debian*.tar) continue ;;
        esac
        info "Loading $(basename "$img") ..."
        docker load -i "$img" || true
        if docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
            break
        fi
    done

    if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
        if ! docker image inspect "$BASE_IMAGE" >/dev/null 2>&1; then
            if [ -f "$BASE_TAR" ] && [ -s "$BASE_TAR" ]; then
                info "Loading base image from $BASE_TAR ..."
                docker load -i "$BASE_TAR" || warn "Failed to load base image tarball"
            fi
        fi

        DEBS_OK=0
        [ -n "$(ls -A "$SCRIPT_DIR/local/debs/"*.deb 2>/dev/null)" ] && DEBS_OK=1
        TARBALL=$(ls "$SCRIPT_DIR/local/ollama/ollama-cpu-build"*.tar.gz \
                     "$SCRIPT_DIR/local/ollama/ollama-cpu-build"*.tgz 2>/dev/null | head -n1 || true)

        if [ "$DEBS_OK" -eq 1 ] && [ -n "$TARBALL" ] && [ -f "$DOCKERFILE" ]; then
            info "Required assets found – building $IMAGE_NAME ..."
            docker build -t "$IMAGE_NAME" -f "$DOCKERFILE" "$SCRIPT_DIR"
        else
            warn "Cannot build the image automatically (missing assets)."
            warn "Run: ./scripts/build-image.sh"
            warn "Then: ravi install"
            exit 0
        fi
    fi
fi

if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    warn "Image $IMAGE_NAME is still missing – service not started."
    warn "Build it with: ./scripts/build-image.sh"
    exit 0
fi

info "Image $IMAGE_NAME is available."

# ------------------------------------------------------------------
# 4. Start the service (same as "ravi install")
# ------------------------------------------------------------------
step "Starting Ollama service"

if [ -x "$BIN_PATH" ]; then
    # Prefer the just-installed CLI so behaviour stays consistent
    "$BIN_PATH" install
else
    warn "ravi binary not found at $BIN_PATH – start manually with: ravi install"
    exit 0
fi

echo
info "Setup complete."
info "You can now run:  ravi"
echo
