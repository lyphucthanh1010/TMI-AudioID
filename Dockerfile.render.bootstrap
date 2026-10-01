FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libchromaprint1 curl unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN curl -fsSL "https://tmi-artifacts.floot.app/_cdn/static/04a20022-9c67-4e6c-8ecb-10df44b8b6fc-tmi_render_base.zip" -o /tmp/tmi-base.zip \
    && unzip -q /tmp/tmi-base.zip -d /tmp/tmi-base \
    && cp -a /tmp/tmi-base/tmi_render_ready/. /app/ \
    && curl -fsSL "https://tmi-artifacts.floot.app/_cdn/static/5383c5fa-4d0d-4852-ae52-d80f1435fe8c-tmi_overlay_complete_v2.zip" -o /tmp/tmi-overlay.zip \
    && unzip -qo /tmp/tmi-overlay.zip -d /tmp/tmi-overlay \
    && cp -a /tmp/tmi-overlay/. /app/ \
    && rm -rf /tmp/tmi-base /tmp/tmi-base.zip /tmp/tmi-overlay /tmp/tmi-overlay.zip

WORKDIR /app/backend
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "." "psycopg[binary]>=3.2" \
    && mkdir -p /app/pretrained_runtime \
    && cp -a /app/backend/runtime/. /app/pretrained_runtime/ \
    && chmod +x /app/backend/scripts/start_render.sh \
    && useradd --create-home --uid 10001 audioid \
    && mkdir -p /runtime \
    && chown -R audioid:audioid /runtime /app

USER audioid

ENV AUDIOID_RUNTIME_DIR=/runtime \
    AUDIOID_DATABASE_URL=sqlite+pysqlite:////runtime/audioid.db \
    AUDIOID_ARTIFACT_DIR=/runtime/models \
    AUDIOID_UPLOAD_DIR=/runtime/uploads \
    AUDIOID_AUTO_CREATE_SCHEMA=1

EXPOSE 10000

CMD ["/app/backend/scripts/start_render.sh"]
