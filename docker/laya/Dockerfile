FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    USE_TF=0

RUN python -m pip install --no-cache-dir "laya[serve]==0.4.1"

EXPOSE 8000

CMD ["laya-serve"]
