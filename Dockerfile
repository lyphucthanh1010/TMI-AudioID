FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ffmpeg libchromaprint1 curl unzip ca-certificates gnupg git \
       build-essential pkg-config libcairo2-dev libpango1.0-dev \
       libjpeg-dev libgif-dev librsvg2-dev \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch 2.0.0 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil \
    && cd /opt/bgutil/server \
    && npm ci --no-audit --no-fund \
    && npx tsc \
    && npm prune --omit=dev \
    && rm -rf /root/.npm

WORKDIR /app
COPY bootstrap/seed_test_account.py /app/bootstrap/seed_test_account.py
COPY bootstrap/start_render_seeded.sh /app/bootstrap/start_render_seeded.sh
RUN curl -fsSL "https://tmi-artifacts.floot.app/_cdn/static/04a20022-9c67-4e6c-8ecb-10df44b8b6fc-tmi_render_base.zip" -o /tmp/tmi-base.zip \
    && unzip -q /tmp/tmi-base.zip -d /tmp/tmi-base \
    && cp -a /tmp/tmi-base/tmi_render_ready/. /app/ \
    && curl -fsSL "https://tmi-artifacts.floot.app/_cdn/static/75ce2ec7-5457-4f1f-8cd7-baa2d6248279-tmi_overlay_private_batch_v3.zip" -o /tmp/tmi-overlay.zip \
    && unzip -qo /tmp/tmi-overlay.zip -d /tmp/tmi-overlay \
    && cp -a /tmp/tmi-overlay/. /app/ \
    && curl -fsSL "https://tmi-artifacts.floot.app/_cdn/static/b4e7b655-6dcc-4d62-ab6b-86527c996c13-tmi_youtube_pot_patch_v6.zip" -o /tmp/tmi-pot-patch.zip \
    && unzip -qo /tmp/tmi-pot-patch.zip -d /app \
    && curl -fsSL "https://tmi-artifacts.floot.app/_cdn/static/04a784ab-948c-4315-b33e-81ec25868f0f-tmi_backend_auth_patch_v7.zip" -o /tmp/tmi-auth-patch.zip \
    && unzip -qo /tmp/tmi-auth-patch.zip -d /app \
    && rm -rf /tmp/tmi-base /tmp/tmi-base.zip /tmp/tmi-overlay /tmp/tmi-overlay.zip /tmp/tmi-pot-patch.zip /tmp/tmi-auth-patch.zip

WORKDIR /app/backend
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "." "psycopg[binary]>=3.2" "bgutil-ytdlp-pot-provider==2.0.0" \
    && mkdir -p /app/pretrained_runtime \
    && cp -a /app/backend/runtime/. /app/pretrained_runtime/ \
    && chmod +x /app/backend/scripts/start_render.sh /app/bootstrap/start_render_seeded.sh \
    && useradd --create-home --uid 10001 audioid \
    && mkdir -p /runtime \
    && chown -R audioid:audioid /runtime /app /opt/bgutil

USER audioid

ENV AUDIOID_RUNTIME_DIR=/runtime \
    AUDIOID_DATABASE_URL=sqlite+pysqlite:////runtime/audioid.db \
    AUDIOID_ARTIFACT_DIR=/runtime/models \
    AUDIOID_UPLOAD_DIR=/runtime/uploads \
    AUDIOID_AUTO_CREATE_SCHEMA=1 \
    TMI_YOUTUBE_POT_PROVIDER_URL=http://127.0.0.1:4416

EXPOSE 10000

CMD ["/app/bootstrap/start_render_seeded.sh"]
