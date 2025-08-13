FROM python:3.13-slim

WORKDIR /app
COPY ncdot_locations_coordinates_only.json requirements.txt scrapedmv.py /app/

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl firefox-esr && \
    pip3 install --break-system-packages --no-cache-dir -r /app/requirements.txt && \
    curl -sL https://github.com/mozilla/geckodriver/releases/download/v0.36.0/geckodriver-v0.36.0-linux-aarch64.tar.gz >    chmod +x /usr/local/bin/geckodriver && \
    apt-get purge -y curl && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV GECKODRIVER_PATH=/usr/local/bin/geckodriver
CMD ["python", "/app/scrapedmv.py"]




