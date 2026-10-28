FROM python:3.12-slim

WORKDIR /app
COPY server.py ./server.py
COPY leitor/__init__.py leitor/sync_server.py ./leitor/

VOLUME ["/data"]
EXPOSE 8765
CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8765", "--data-dir", "/data"]
