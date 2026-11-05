FROM ghcr.io/berriai/litellm:v1.106.6

COPY docker/litellm/transformation.py /opt/ravi/transformation.py
COPY docker/litellm/entrypoint.sh /opt/ravi/entrypoint.sh

ENTRYPOINT ["/bin/sh", "/opt/ravi/entrypoint.sh"]
