#!/bin/sh
#
# container.sh – Ollama container lifecycle management
#
# Responsible for:
#   • Loading offline / local image packages
#   • Ensuring the required Docker image is present
#   • Starting, stopping and removing the managed container
#   • Health-checking the Ollama API
#   • Providing status information
#
# Pure POSIX sh – works under dash and BusyBox ash.
#

# Shared settings (LOCAL_DIR, OFFLINE_IMAGE_PATH, check_docker, …)
# are expected to be already sourced via common.sh

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
CONTAINER_NAME="ravi-ollama"
VOLUME_NAME="models"
OLLAMA_IMAGE="${OLLAMA_IMAGE:-ravi-ollama:cpu}"

# ------------------------------------------------------------------
# load_local_images
# ------------------------------------------------------------------
load_local_images() {
    # 1) Search the detected LOCAL_DIR
    if [ -d "$LOCAL_DIR" ]; then
        echo "[*] Checking local image directory: $LOCAL_DIR"

        for img_file in "$LOCAL_DIR"/*.tar "$LOCAL_DIR"/*.tar.gz; do
            [ -e "$img_file" ] || continue

            if [ ! -s "$img_file" ]; then
                echo "[*] Skipping empty placeholder: $(basename "$img_file")"
                continue
            fi

            echo "[*] Found local image package: $(basename "$img_file")"
            echo "[*] Loading into Docker..."
            if docker load -i "$img_file"; then
                :
            else
                echo "Warning: failed to load $(basename "$img_file")" >&2
            fi
        done
    else
        echo "[*] Local directory not found at $LOCAL_DIR, skipping."
    fi

    # 2) Classic offline path
    if [ -n "$OFFLINE_IMAGE_PATH" ] && [ -f "$OFFLINE_IMAGE_PATH" ] && [ -s "$OFFLINE_IMAGE_PATH" ]; then
        offline_real=$(realpath "$OFFLINE_IMAGE_PATH" 2>/dev/null || echo "$OFFLINE_IMAGE_PATH")
        local_candidate=$(realpath "$LOCAL_DIR/$(basename "$OFFLINE_IMAGE_PATH")" 2>/dev/null || echo "")

        if [ "$offline_real" != "$local_candidate" ]; then
            echo "[*] Loading offline image from $OFFLINE_IMAGE_PATH..."
            docker load -i "$OFFLINE_IMAGE_PATH" || true
        fi
    fi

    return 0
}

# ------------------------------------------------------------------
# is_container_running
# ------------------------------------------------------------------
is_container_running() {
    [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null)" = "true" ]
}

# ------------------------------------------------------------------
# ensure_ollama_image
# ------------------------------------------------------------------
ensure_ollama_image() {
    if docker image inspect "$OLLAMA_IMAGE" >/dev/null 2>&1; then
        return 0
    fi

    echo "[*] Image '$OLLAMA_IMAGE' not found locally. Trying to load from packages..."
    load_local_images

    if docker image inspect "$OLLAMA_IMAGE" >/dev/null 2>&1; then
        echo "[*] Image '$OLLAMA_IMAGE' is now available."
        return 0
    fi

    echo "[*] Attempting to pull '$OLLAMA_IMAGE'..."
    if docker pull "$OLLAMA_IMAGE"; then
        return 0
    fi

    echo "Error: Could not obtain image '$OLLAMA_IMAGE'." >&2
    echo "  • Place a valid ollama-cpu.tar.gz under $LOCAL_DIR (or /usr/share/ravi)" >&2
    echo "  • Or build it yourself:" >&2
    echo "      docker build -t ravi-ollama:cpu -f docker/Dockerfile.ollama-cpu ." >&2
    echo "      docker save ravi-ollama:cpu | gzip > /usr/share/ravi/ollama-cpu.tar.gz" >&2
    return 1
}

# ------------------------------------------------------------------
# wait_for_ollama_ready
# ------------------------------------------------------------------
wait_for_ollama_ready() {
    echo "Waiting for Ollama service to become ready..."
    i=0
    while [ "$i" -lt 30 ]; do
        if docker exec "$CONTAINER_NAME" ollama list >/dev/null 2>&1; then
            echo "Ollama service is ready!"
            return 0
        fi
        sleep 1
        i=$((i + 1))
    done
    echo "Warning: Ollama container started, but API took longer than expected to respond." >&2
    return 1
}

# ------------------------------------------------------------------
# start_ollama_container
# ------------------------------------------------------------------
start_ollama_container() {
    ensure_models_volume || return 1
    ensure_ollama_image  || return 1

    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        if is_container_running; then
            echo "Ollama service is already running."
            return 0
        else
            echo "Starting existing Ollama container..."
            docker start "$CONTAINER_NAME" >/dev/null
            wait_for_ollama_ready
        fi
    else
        echo "Creating and starting Ollama container..."
        docker run -d \
            --name "$CONTAINER_NAME" \
            --restart unless-stopped \
            -v "${VOLUME_NAME}:/models" \
            -e "OLLAMA_MODELS=/models" \
            -p "127.0.0.1:11434:11434" \
            --label "com.ravios.managed=true" \
            --label "com.ravios.component=ai" \
            "$OLLAMA_IMAGE" >/dev/null
        wait_for_ollama_ready
    fi
}

# ------------------------------------------------------------------
# stop_ollama_container
# ------------------------------------------------------------------
stop_ollama_container() {
    if is_container_running; then
        echo "Stopping Ollama service..."
        docker stop "$CONTAINER_NAME" >/dev/null
        echo "Ollama stopped."
    else
        echo "Ollama service is not running."
    fi
}

# ------------------------------------------------------------------
# uninstall_ollama
# ------------------------------------------------------------------
uninstall_ollama() {
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "Removing Ollama container (persistent volume '$VOLUME_NAME' is preserved)..."
        docker rm -f "$CONTAINER_NAME" >/dev/null
        echo "Container removed."
    else
        echo "Ollama container is not installed."
    fi
}

# ------------------------------------------------------------------
# show_status
# ------------------------------------------------------------------
show_status() {
    echo "Ravi AI Status:"
    echo "----------------------------------------"
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        STATUS=$(docker inspect -f '{{.State.Status}}' "$CONTAINER_NAME")
        IMAGE=$(docker inspect -f '{{.Config.Image}}' "$CONTAINER_NAME")
        echo "Container:      $CONTAINER_NAME ($STATUS)"
        echo "Image:          $IMAGE"
    else
        echo "Container:      Not Installed"
    fi

    if docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1; then
        VOL_PATH=$(docker volume inspect -f '{{.Mountpoint}}' "$VOLUME_NAME")
        VOL_SIZE=$(du -sh "$VOL_PATH" 2>/dev/null | awk '{print $1}')
        echo "Models Volume:  $VOLUME_NAME (Persistent)"
        echo "Host Path:      $VOL_PATH"
        echo "Disk Usage:     ${VOL_SIZE:-Unknown}"
    else
        echo "Models Volume:  Not Created"
    fi

    echo "Local images dir: $LOCAL_DIR"
    if docker image inspect "$OLLAMA_IMAGE" >/dev/null 2>&1; then
        echo "Expected image:   $OLLAMA_IMAGE (present)"
    else
        echo "Expected image:   $OLLAMA_IMAGE (missing)"
    fi
    echo "----------------------------------------"
}

# ------------------------------------------------------------------
# run_ollama_cmd
# ------------------------------------------------------------------
run_ollama_cmd() {
    if ! is_container_running; then
        start_ollama_container || return 1
    fi
    docker exec -it "$CONTAINER_NAME" ollama "$@"
}
