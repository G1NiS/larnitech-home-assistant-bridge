FROM ghcr.io/home-assistant/base:latest

WORKDIR /app

RUN apk add --no-cache python3 py3-pip

COPY pyproject.toml ./
COPY larnitech_ha_bridge ./larnitech_ha_bridge

RUN pip3 install . --break-system-packages --no-cache-dir

COPY addon/run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
