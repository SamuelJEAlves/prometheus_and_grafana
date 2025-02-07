from fastapi import FastAPI, HTTPException
from prometheus_client import (
    Counter, 
    Gauge, 
    Summary, 
    Histogram, 
    generate_latest, 
    CONTENT_TYPE_LATEST
)
from fastapi.responses import Response
import random
import time

app = FastAPI()

# Counter -> Conta eventos, só pode ser incrementado (contador de requisições ao endpoint, etc)
TOTAL_REQUESTS = Counter(
    "total_requests",
    "Total de requisições feitas na aplicação",
    ["method", "endpoint"]
)

# Gauge -> Mede um valor que pode ser aumentar ou diminuir (usuários logados, temperatura da cpu, etc)
USERS_ONLINE = Gauge(
    "users_online",
    "Número de usuários online no sistema"
)

# Summary -> Mede a duração de eventos, calculando a média, a soma e a contagem de eventos (tempo de resposta de uma requisição, etc)
REQUEST_TIME = Summary(
    "request_processing",
    "Tempo de processamento de requisições"
)

# Histogram -> Mesma coisa que o Summary, mas com a possibilidade de definir buckets (faixas de valores) para os eventos
# Buckets = Acumular eventos. Exemplo: Ver as chamadas das últimas 24 horas, agrupadas por hora.

# Endpoint raiz
@app.get("/")
async def root():
    # Incrementa o contador de requisições
    TOTAL_REQUESTS.labels("GET", "/").inc()
    
    return {"message": "Bem-vindo ao sistema de métricas com FastAPI e Prometheus!"}

# Endpoint para simular a quantidade de usuários online
@app.get("/users/online", include_in_schema=True)
async def get_users_online():
    # Incrementa o contador de requests
    TOTAL_REQUESTS.labels(method='GET', endpoint='/users/online').inc()
    
    # Simula número de usuários online (variando entre 0 e 100)
    users_online = random.randint(0, 100)
    
    # Atualiza a métrica Gauge
    USERS_ONLINE.set(users_online)
    
    return {"users_online": users_online}

# Endpoint para simular medição de tempo de processamento
@app.get("/process_time")
async def get_process_time():
    # Incrementa o contador de requests
    TOTAL_REQUESTS.labels(method='GET', endpoint='/process_time').inc()
    
    # Inicia o timer
    start_time = time.time()
    
    # Simula um processamento
    time.sleep(random.uniform(0.1, 1.0))
    
    # Finaliza o timer
    end_time = time.time()
    
    # Calcula o tempo de processamento
    process_time = end_time - start_time
    
    # Atualiza a métrica Summary
    REQUEST_TIME.observe(process_time)
    
    return {"process_time": process_time}

# Endpoint para simular um erro

# Endpoint para expor as métricas no formato Prometheus
@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)