# AeroEyes Monitoring API

[Português](README.md) · [English](README.en.md)

API de monitoramento da plataforma distribuída AeroEyes, responsável pelas
sessões de monitoramento, ingestão de eventos de atenção e contexto operacional.

## Requisitos

- Python 3.11 ou mais recente

## Configuração local

Crie e ative um ambiente virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Instale o pacote com as dependências de testes e migrações:

```bash
python -m pip install -e ".[test,migration]"
```

Execute a API localmente:

```bash
export DATABASE_URL="postgresql+psycopg://aeroeyes:local-password@localhost:5432/aeroeyes"
export CORS_ALLOWED_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"
python -m alembic upgrade head
python -m uvicorn aeroeyes_monitoring_api.main:create_app --factory --reload
```

`CORS_ALLOWED_ORIGINS` recebe uma lista, separada por vírgulas, de origens
explícitas permitidas no navegador. Nenhuma origem, incluindo localhost, é
habilitada implicitamente.

O endpoint simples de disponibilidade está em `GET /health`:

```json
{
  "status": "ok",
  "service": "aeroeyes-monitoring-api"
}
```

## Persistência PostgreSQL

O PostgreSQL é o armazenamento persistente utilizado em runtime. O schema
contém sessões de monitoramento, contexto de voo e eventos de atenção. A
inicialização normal exige `DATABASE_URL`; não existe fallback automático para
persistência em memória.

Defina `DATABASE_URL` ao executar as migrações, usando o formato síncrono do
SQLAlchemy com Psycopg 3:

```bash
export DATABASE_URL="postgresql+psycopg://aeroeyes:local-password@localhost:5432/aeroeyes"
```

Use credenciais locais de desenvolvimento e não versione segredos ou arquivos
`.env`. Aplique ou reverta o schema com Alembic:

```bash
python -m alembic upgrade head
python -m alembic downgrade base
```

## Sessões de monitoramento

Crie uma sessão ativa sem corpo na requisição:

```http
POST /sessions
```

A API retorna `201 Created`, um header `Location` e a nova sessão:

```json
{
  "session_id": "019...",
  "status": "ACTIVE",
  "started_at": "2026-08-27T12:00:00Z",
  "ended_at": null
}
```

Consulte ou conclua a sessão usando sua identidade UUIDv7:

```http
GET /sessions/{session_id}
POST /sessions/{session_id}/complete
```

A conclusão é idempotente. Requisições repetidas retornam a sessão já concluída
e preservam o valor original de `ended_at`.

As sessões são armazenadas no PostgreSQL e permanecem disponíveis após o
reinício da aplicação e entre múltiplas instâncias que utilizem o mesmo banco.

## Contexto de voo da sessão

Consulte, substitua ou remova o contexto operacional associado a uma sessão:

```http
GET /sessions/{session_id}/context
PUT /sessions/{session_id}/context
DELETE /sessions/{session_id}/context
```

O `PUT` substitui o contexto com número do voo e códigos ICAO de origem e
destino. O recurso pertence à sessão informada e é persistido no PostgreSQL. A
remoção retorna `204 No Content` e não conclui nem remove a sessão.

## Meteorologia atual da sessão

Consulte o contexto METAR atual dos aeroportos de origem e destino configurados
na sessão de monitoramento:

```http
GET /sessions/{session_id}/weather
```

A API consulta AviationWeather.gov no servidor e retorna somente o contrato
meteorológico normalizado do AeroEyes; o frontend não chama o provedor
diretamente. Esse recurso representa o contexto operacional atual, inclusive
para sessões concluídas. Ele não oferece histórico, não é persistido nem
mantido em cache e não participa da classificação de atenção ou fadiga.

## Ingestão de eventos de atenção

Envie um evento de atenção imutável para sua sessão de monitoramento:

```http
POST /sessions/{session_id}/events
```

O produtor define o `event_id` UUIDv7 e o instante de ocorrência. A API define
`received_at`. A primeira ingestão retorna `201 Created`; a repetição idêntica
do mesmo evento na mesma sessão retorna `200 OK`, com
`status: "already_processed"` e o evento original armazenado. Reutilizar um ID
com semântica diferente ou em outra sessão retorna `409 Conflict`.

Os eventos são somente anexados. Uma sessão concluída ainda aceita um evento
entregue com atraso quando o instante informado pelo produtor está dentro da
janela inclusiva de início e fim da sessão.

O armazenamento e a arbitragem de IDs utilizam PostgreSQL. A validação da
sessão e a aceitação do evento compartilham a transação controlada por uma
unidade de trabalho por operação. Assim, a persistência e a proteção contra
repetições não dependem de locks locais do processo.

## Modelo de leitura de atenção

Consulte a transição semântica de atenção mais recente da sessão:

```http
GET /sessions/{session_id}/attention-state
```

Consulte uma janela limitada de eventos recentes, do mais novo para o mais
antigo:

```http
GET /sessions/{session_id}/events?limit=10
```

`limit` utiliza `10` por padrão e aceita valores de `1` a `50`. Os campos
oculares de um evento descrevem a observação capturada na transição; eles não
representam telemetria contínua da câmera.

## Testes

Execute a suíte completa:

```bash
python -m pytest
```
