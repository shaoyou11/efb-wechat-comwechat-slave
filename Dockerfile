FROM python:alpine AS venv

COPY . /src

RUN set -ex; \
    apk --update upgrade; \
    apk --update add --no-cache python3-dev py3-pillow py3-ruamel.yaml libmagic ffmpeg git gcc zlib-dev jpeg-dev musl-dev libffi-dev openssl-dev libwebp-dev
RUN python -m venv --copies /app/venv; \
    . /app/venv/bin/activate; \
    pip3 install git+https://github.com/shaoyou11/efb-telegram-master.git@1cd2f62d3b308e9f8848cfb0be36036de28134cf; \
    pip3 install ehforwarderbot python-telegram-bot; \
    pip3 install git+https://github.com/shaoyou11/python-comwechatrobot-http.git@65c4833b32ae33e63d59a1ad710a910d842d66c9; \
    pip3 install /src; \
    pip3 install git+https://github.com/QQ-War/efb-keyword-reply.git; \
    pip3 install git+https://github.com/QQ-War/efb_message_merge.git; \
    pip3 install urllib3==1.26.20; \
    pip3 install --no-deps --force-reinstall Pillow; \
    pip3 install --ignore-installed PyYAML TgCrypto
    
FROM python:alpine AS prod

LABEL org.opencontainers.image.source=https://github.com/shaoyou11/efb-wechat-comwechat-slave

ENV LANG C.UTF-8
ENV TZ Asia/Shanghai

COPY --from=venv /app/venv /app/venv/
ENV PATH /app/venv/bin:$PATH

COPY config-example.yaml /root/.ehforwarderbot/profiles/default/config.yaml

RUN set -ex; \
    apk --update upgrade; \
    apk --update add --no-cache tzdata libmagic ffmpeg; \
    ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime; \
    echo "Asia/Shanghai" > /etc/timezone; \
    mkdir -p /root/.ehforwarderbot/profiles/default/blueset.telegram /root/.ehforwarderbot/modules/

VOLUME /root/.ehforwarderbot/profiles/default/blueset.telegram

ENTRYPOINT ["ehforwarderbot"]
