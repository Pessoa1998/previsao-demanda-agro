FROM python:3.13-slim

WORKDIR /app
ENV PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLCONFIGDIR=/tmp/matplotlib

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# testes + pipeline completo; monte ./reports como volume para levar os resultados
CMD ["sh", "-c", "python -m pytest -q && python -m demanda.pipeline"]
