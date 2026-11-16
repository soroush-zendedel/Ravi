#!/bin/sh
#
# volume.sh – Persistent Docker volume management for AI models
#
# Pure POSIX sh.
#

VOLUME_NAME="models"

# ------------------------------------------------------------------
# ensure_models_volume
# ------------------------------------------------------------------
ensure_models_volume() {
    if docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1; then
        return 0
    fi

    echo "Creating persistent volume '$VOLUME_NAME'..."
    docker volume create \
        --label "com.ravios.managed=true" \
        --label "com.ravios.component=ai-models" \
        "$VOLUME_NAME" >/dev/null
    echo "Persistent volume '$VOLUME_NAME' created."
}
