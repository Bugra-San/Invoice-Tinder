# Rechnungs-Tinder als Server-Container
#   docker compose up -d        (siehe docs/SERVER.md)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Europe/Berlin \
    RT_SERVER=1 \
    RT_PORT=8765 \
    RT_ORDNER=/rechnungen \
    RT_EINSTELLUNGEN=/daten/einstellungen.json \
    HOME=/daten

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY rechnungs_tinder ./rechnungs_tinder

# /daten: Einstellungen (PIN, Schlüssel, zuletzt verwendete Ordner)
# /rechnungen: der Rechnungsordner (z. B. die NAS-Freigabe)
# Beide beschreibbar für jede Benutzer-ID, da diese per "user:" in der compose-Datei
# an die Rechte der NAS-Freigabe angepasst wird.
RUN mkdir -p /daten /rechnungen && chmod 0777 /daten /rechnungen
VOLUME ["/daten"]

USER 1000:1000
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/v1/info' % os.environ.get('RT_PORT', '8765'), timeout=4)"

CMD ["python", "-m", "rechnungs_tinder"]
