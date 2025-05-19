import os
import secrets
import random
import time
import logging
from typing import Callable, Optional
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import asyncio

from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from prometheus_client import (
    Counter,
    Gauge,
    Summary,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry
)
from pydantic import BaseModel

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Modelos Pydantic para validação
class UserOnlineResponse(BaseModel):
    users_online: int

class ProcessTimeResponse(BaseModel):
    process_time: float

class HealthResponse(BaseModel):
    status: str
    timestamp: float

load_dotenv()  # Carrega variáveis de ambiente do arquivo .env

# Configurações via variáveis de ambiente
USERNAME = os.getenv("API_USERNAME")
PASSWORD = os.getenv("API_PASSWORD")

if not USERNAME or not PASSWORD:
    raise RuntimeError("Credenciais de API não configuradas corretamente nas variáveis de ambiente.")

# Registry personalizado para métricas (permite reset em testes)
metrics_registry = CollectorRegistry()

# Métricas Prometheus com registry personalizado
TOTAL_REQUESTS = Counter(
    "http_requests_total",
    "Numero total de HTTP requests",
    ["method", "endpoint", "status_code"],
    registry=metrics_registry
)

USERS_ONLINE = Gauge(
    "users_online_current",
    "Numero de usuários online no sistema",
    registry=metrics_registry
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "Duração das requisições HTTP em segundos",
    ["method", "endpoint"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=metrics_registry
)

ACTIVE_CONNECTIONS = Gauge(
    "active_connections_current",
    "Numero de conexões ativas no sistema",
    registry=metrics_registry
)

# Context manager para lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Iniciando a aplicação FastAPI")
    yield
    # Shutdown
    logger.info("Encerrando a aplicação FastAPI")

# Configuração do FastAPI
app = FastAPI(
    title="API de Métricas com FastAPI e Prometheus",
    description="API para coleta de métricas com autenticação básica",
    version="1.0.0",
    lifespan=lifespan
)

# Configuração de CORS (opcional caso haja frontend separado futuramente)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # Configure adequadamente em produção
#     allow_credentials=True,
#     allow_methods=["GET", "POST"],
#     allow_headers=["*"],
# )

# Autenticação
security = HTTPBasic()

def authenticate(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """
    Autentica as credenciais do usuário usando comparação segura (evita timing attack).
    
    Args:
        credentials: Credenciais HTTP Basic
        
    Returns:
        Username se autenticado
        
    Raises:
        HTTPException: Se as credenciais forem inválidas
    """
    is_correct_username = secrets.compare_digest(credentials.username, USERNAME)
    is_correct_password = secrets.compare_digest(credentials.password, PASSWORD)
    
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# Middleware exclusivo para métricas
@app.middleware("http")
async def metrics_middleware(request: Request, call_next: Callable) -> Response:
    """
    Middleware dedicado exclusivamente à coleta de métricas.
    
    Este middleware:
    - Registra métricas de duração e contagem para todas as requisições
    - É independente da autenticação (gerenciada nos endpoints)
    """
    start_time = time.time()
    
    # Incrementa conexões ativas
    ACTIVE_CONNECTIONS.inc()
    
    try:
        # Processa requisição
        response = await call_next(request)
        
        # Calcula tempo de processamento
        process_time = time.time() - start_time
        
        # Registra métricas de duração
        REQUEST_DURATION.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(process_time)
        
        # Registra contagem de requisições com status
        TOTAL_REQUESTS.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=str(response.status_code)
        ).inc()
        
        return response
        
    except Exception as e:
        # Registra erro
        TOTAL_REQUESTS.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code="500"
        ).inc()
        logger.error(f"Erro ao processar requisição {request.method} {request.url.path}: {e}")
        raise
    finally:
        # Decrementa conexões ativas
        ACTIVE_CONNECTIONS.dec()

# Endpoints

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Endpoint de health check - não requer autenticação.
    """
    return HealthResponse(
        status="Saudável",
        timestamp=time.time()
    )

@app.get("/", tags=["Root"])
async def root(username: str = Depends(authenticate)):
    """
    Endpoint raiz com autenticação obrigatória.
    
    Args:
        username: Username autenticado (injetado pelo dependency)
    """
    return {
        "message": "Bem-vindo à API de Métricas!",
        "authenticated_user": username
    }

@app.get("/users/online", response_model=UserOnlineResponse, tags=["Users"])
async def get_users_online(username: str = Depends(authenticate)):
    """
    Simula e retorna o número de usuários online.
    Requer autenticação.
    
    Args:
        username: Username autenticado
    """
    users_online = random.randint(0, 100)
    USERS_ONLINE.set(users_online)
    
    logger.info(f"Usuários online: {users_online} pelo usuário: {username}")
    return UserOnlineResponse(users_online=users_online)

@app.get("/process_time", response_model=ProcessTimeResponse, tags=["Metrics"])
async def simulate_processing_time(username: str = Depends(authenticate)):
    """
    Simula processamento com tempo variável para demonstrar métricas.
    Requer autenticação.
    
    Args:
        username: Username autenticado
        
    Returns:
        Tempo de processamento simulado
    """
    start_time = time.time()
    
    # Simula processamento com tempo variável
    processing_delay = random.uniform(0.1, 1.0)
    await asyncio.sleep(processing_delay)
    
    actual_process_time = time.time() - start_time
    
    logger.info(f"Processamento concluído em {actual_process_time:.3f}s pelo usuário: {username}")
    return ProcessTimeResponse(process_time=actual_process_time)

@app.get("/metrics", tags=["Metrics"])
async def get_metrics(username: str = Depends(authenticate)):
    """
    Endpoint para Prometheus scraping.
    
    Args:
        username: Username autenticado
        
    Returns:
        Métricas no formato Prometheus
    """
    logger.info(f"Métricas acessadas pelo usuário: {username}")
    return Response(
        generate_latest(metrics_registry),
        media_type=CONTENT_TYPE_LATEST
    )

# Simular diferentes status codes (erros)
@app.get("/simulate_error", tags=["Testing"])
async def simulate_error(
    error_code: Optional[int] = 500,
    username: str = Depends(authenticate)
):
    """
    Simula diferentes tipos de erro para testes de métricas.
    Requer autenticação.
    
    Args:
        error_code: Código de erro HTTP a ser simulado
        username: Username autenticado
    """
    error_messages = {
        400: "Bad Request - Invalid parameters",
        404: "Not Found - Resource not found",
        500: "Internal Server Error - Something went wrong",
        503: "Service Unavailable - Service temporarily unavailable"
    }
    
    if error_code in error_messages:
        raise HTTPException(
            status_code=error_code,
            detail=error_messages[error_code]
        )
    
    return {"message": "Nenhum erro simulado", "requested_code": error_code}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )