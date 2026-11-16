#!/bin/sh
#
# common.sh – Shared utilities and environment detection for Ravi AI
#
# Pure POSIX sh – works under dash, BusyBox ash and WSL.
#

# Prefer SCRIPT_DIR if the caller already set it (main ravi does this)
if [ -n "${SCRIPT_DIR:-}" ] && [ -d "$SCRIPT_DIR/lib" ]; then
    LIB_DIR="$SCRIPT_DIR/lib"
else
    _caller="$0"
    if [ -L "$_caller" ]; then
        if command -v readlink >/dev/null 2>&1; then
            _caller=$(readlink -f "$_caller" 2>/dev/null || readlink "$_caller")
        fi
    fi
    LIB_DIR="$(cd "$(dirname "$_caller")/lib" 2>/dev/null && pwd)"
    if [ -z "$LIB_DIR" ] || [ ! -d "$LIB_DIR" ]; then
        LIB_DIR="$(pwd)/lib"
    fi
fi

# ------------------------------------------------------------------
# Detect development vs installed mode
#
# Only treat as "source tree" when we can see the real project markers
# (tools/ravi + local/ next to each other).  A plain /usr/local directory
# must NOT be mistaken for the project.
# ------------------------------------------------------------------
PROJECT_ROOT=""
LOCAL_DIR="/usr/share/ravi"

# From lib/ go up to potential project root: lib -> ravi -> tools -> root
_candidate="$(cd "$LIB_DIR/../../.." 2>/dev/null && pwd)"
if [ -n "$_candidate" ] \
   && [ -d "$_candidate/tools/ravi" ] \
   && [ -d "$_candidate/local" ] \
   && [ -f "$_candidate/tools/ravi/ravi" ]; then
    PROJECT_ROOT="$_candidate"
    LOCAL_DIR="$PROJECT_ROOT/local"
fi

OFFLINE_IMAGE_PATH="/usr/share/ravi/ollama-cpu.tar.gz"

# Suppress Docker Desktop "What's next" / CLI hint adverts
export DOCKER_CLI_HINTS=false

# ------------------------------------------------------------------
# Docker command detection (Linux docker or Windows docker.exe under WSL)
# ------------------------------------------------------------------
detect_docker() {
    if [ -n "${DOCKER_CMD:-}" ]; then
        return 0
    fi

    # Prefer docker.exe first on WSL – native "docker" often hangs or is a stub
    # when only Docker Desktop is installed.
    is_wsl=0
    if [ -f /proc/version ] && grep -qi microsoft /proc/version 2>/dev/null; then
        is_wsl=1
    fi

    try_cmd() {
        # $1 = command path or name
        # Quick check: does it answer "info" within a reasonable time?
        if [ -x "$1" ] || command -v "$1" >/dev/null 2>&1; then
            if "$1" info >/dev/null 2>&1; then
                DOCKER_CMD="$1"
                return 0
            fi
        fi
        return 1
    }

    if [ "$is_wsl" -eq 1 ]; then
        # WSL: try docker.exe first
        try_cmd docker.exe && return 0

        for candidate in \
            /mnt/c/Users/*/AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe \
            /mnt/c/Users/*/AppData/Local/Docker/bin/docker.exe \
            "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" \
            "/mnt/c/Program Files/Docker/Docker/resources/docker.exe"
        do
            try_cmd "$candidate" && return 0
        done

        # then native docker
        try_cmd docker && return 0
    else
        # Normal Linux: native first
        try_cmd docker && return 0
        try_cmd docker.exe && return 0
    fi

    # Fallback name for error messages
    if command -v docker >/dev/null 2>&1; then
        DOCKER_CMD="docker"
    elif command -v docker.exe >/dev/null 2>&1; then
        DOCKER_CMD="docker.exe"
    else
        DOCKER_CMD="docker"
    fi
}

# ------------------------------------------------------------------
# check_docker
# ------------------------------------------------------------------
check_docker() {
    detect_docker

    if [ ! -x "$DOCKER_CMD" ] && ! command -v "$DOCKER_CMD" >/dev/null 2>&1; then
        echo "Error: Docker command not found (tried docker and docker.exe)." >&2
        echo "  On WSL install Docker Desktop and make sure it is running." >&2
        exit 1
    fi

    if ! "$DOCKER_CMD" info >/dev/null 2>&1; then
        echo "Error: Docker daemon is not running or accessible." >&2
        echo "  Tried command: $DOCKER_CMD" >&2
        echo "  On WSL make sure Docker Desktop is started." >&2
        exit 1
    fi
}

# Convenience wrapper – suppress Docker Desktop "What's next" CLI hints
docker() {
    detect_docker
    export DOCKER_CLI_HINTS=false
    # Pass the variable explicitly for docker.exe under WSL
    env DOCKER_CLI_HINTS=false "$DOCKER_CMD" "$@"
}
