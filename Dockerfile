# ============================================================
# Dockerfile — AutomacaoAds
# Build: docker build -t automacao-ads .
# Run:   docker run -p 8000:8000 --env-file .env automacao-ads
# ============================================================

# Imagem base oficial Python (slim para menor tamanho)
FROM python:3.11-slim

# Metadados
LABEL maintainer="automacao-ads"
LABEL description="Meta Ads Automation API com FastAPI + Firestore"

# Variáveis de ambiente para Python no container
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Diretório de trabalho dentro do container
WORKDIR /app

# Copia requirements primeiro para aproveitar cache de camadas Docker
# (só reinstala dependências se requirements.txt mudar)
COPY requirements.txt .

# Instala dependências
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copia o restante do código da aplicação
COPY . .

# Porta exposta pelo container
EXPOSE 8000

# Comando para iniciar a aplicação em produção
# --workers 4: múltiplos processos para melhor throughput
# --host 0.0.0.0: aceita conexões externas ao container
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
