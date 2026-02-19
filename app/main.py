"""
Ponto de entrada principal da aplicação FastAPI.

Responsável por:
- Instanciar o app FastAPI com metadados
- Registrar middleware (CORS, etc.)
- Registrar rotas com prefixo de versão (/api/v1)
- Gerenciar ciclo de vida (startup/shutdown) via lifespan
- Handler global de exceções não tratadas

Para rodar localmente:
    uvicorn app.main:app --reload --port 8000

Para produção:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.firebase import init_firebase
from app.api.routes_ads import router as ads_router
from app.api.routes_ai import router as ai_router
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia o ciclo de vida da aplicação.

    STARTUP:
    - Inicializa Firebase Admin SDK (conexão com Firestore)
    - Registra início no log

    SHUTDOWN:
    - Registra encerramento (cleanup futuro: fechar conexões, flush de logs, etc.)
    """
    logger.info(
        f"=== Iniciando {settings.APP_NAME} v{settings.APP_VERSION} "
        f"| ambiente={settings.APP_ENV} ==="
    )

    # Inicializa Firebase no startup para detectar erros de configuração cedo
    try:
        init_firebase()
        logger.info("Firebase inicializado com sucesso no startup.")
    except Exception as exc:
        logger.error(f"FALHA CRÍTICA ao inicializar Firebase: {exc}")
        raise  # Impede o servidor de subir com Firebase quebrado

    yield  # Aplicação rodando

    logger.info(f"=== {settings.APP_NAME} encerrado. ===")


# =============================================================================
# INSTÂNCIA PRINCIPAL
# =============================================================================

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## AutomacaoAds — Meta Ads Automation API

Backend profissional para automação de criação e gerenciamento de anúncios
no **Meta Ads (Facebook/Instagram)** com persistência no **Firebase Firestore**.

### Funcionalidades
- Suporte **multi-tenant**: cada automação tem suas próprias credenciais Meta
- Criação de campanhas, ad sets e anúncios via Meta Marketing API
- Persistência automática de resultados e logs no Firestore
- Consulta de métricas (insights) com snapshot automático
- Pausar/ativar campanhas e atualizar orçamentos

### Autenticação
Todos os endpoints requerem o header **`X-API-Key`** com a chave configurada no `.env`.

### Fluxo básico
1. `POST /api/v1/automacao` — Registrar credenciais Meta
2. `POST /api/v1/campaign` — Criar campanha
3. `POST /api/v1/adset` — Criar Ad Set
4. `POST /api/v1/ad` — Criar anúncio
5. `GET /api/v1/campaign/{id}/insights` — Consultar métricas
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# =============================================================================
# MIDDLEWARES
# =============================================================================

app.add_middleware(
    CORSMiddleware,
    # Em produção, substitua "*" pelos domínios do seu frontend/sistema
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# =============================================================================
# HANDLER GLOBAL DE EXCEÇÕES
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Captura exceções não tratadas em qualquer rota.
    Retorna resposta padronizada em vez de expor stack trace ao cliente.
    Em produção, considere integrar com Sentry ou Cloud Error Reporting.
    """
    logger.error(
        f"Exceção não tratada | path={request.url.path} | "
        f"method={request.method} | error={type(exc).__name__}: {exc}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Erro interno do servidor. Tente novamente.",
            "data": None,
        },
    )

# =============================================================================
# ROTAS
# =============================================================================

app.include_router(ads_router, prefix="/api/v1")
app.include_router(ai_router,  prefix="/api/v1")

# =============================================================================
# FRONTEND ESTÁTICO
# Serve os arquivos do dashboard em /static (CSS, JS).
# A rota /dashboard entrega o index.html (SPA).
# =============================================================================

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

if os.path.isdir(FRONTEND_DIR):
    # Monta CSS e JS como arquivos estáticos acessíveis em /static/
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    logger.info(f"Frontend estatico montado em /static -> {FRONTEND_DIR}")

    @app.get("/dashboard", tags=["Frontend"], summary="Dashboard Web", include_in_schema=False)
    async def serve_dashboard():
        """Serve o dashboard frontend (SPA)."""
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# =============================================================================
# ENDPOINTS DE SISTEMA
# =============================================================================

@app.get("/health", tags=["Sistema"], summary="Health check")
async def health_check():
    """Verifica se a aplicação está rodando. Útil para load balancers e monitoramento."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
    }


@app.get("/", tags=["Sistema"], summary="Boas-vindas")
async def root():
    """Endpoint raiz com links para documentação e dashboard."""
    return {
        "message": f"Bem-vindo ao {settings.APP_NAME}",
        "dashboard": "/dashboard",
        "docs": "/docs",
        "redoc": "/redoc",
        "version": settings.APP_VERSION,
    }
