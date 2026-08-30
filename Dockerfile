FROM ollama/ollama:latest

RUN apt-get update && \
    apt-get install -y python3 python3-pip python3-venv curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . /app

RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PATH="/opt/venv/bin:$PATH"
ENV OLLAMA_HOST="127.0.0.1:11434"
ENV AI_URL="http://127.0.0.1:11434/api/chat"

ENTRYPOINT ["/entrypoint.sh"]
