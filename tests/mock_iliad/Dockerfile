FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py .
ENV MOCK_BASE_URL=http://localhost:9100 PYTHONUNBUFFERED=1
EXPOSE 9100
HEALTHCHECK --interval=10s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:9100/healthz')"
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "9100"]
