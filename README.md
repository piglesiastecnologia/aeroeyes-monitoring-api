# AeroEyes Monitoring API

[Português](README.md) · [English](README.en.md)

Backend REST do **AeroEyes Monitoring System**. A API mantém sessões e contexto
de voo, recebe transições semânticas de atenção, oferece modelos de leitura para
o Web e integra dados METAR da AviationWeather.gov.

## Papel no MVP da PUC-Rio

O projeto segue o **cenário 1.1** da Sprint 3:

```text
AeroEyes Web → Monitoring API → AviationWeather Data API
                            ↘ PostgreSQL
```

Este repositório é o backend desenvolvido e um dos dois repositórios públicos
da entrega. O Attention Core é uma extensão opcional: ele pode publicar eventos
na API, mas não é necessário para provar o fluxo Web → API → API externa.

O diagrama canônico e a matriz completa de evidências ficam no repositório
[`aeroeyes-web`](https://github.com/piglesiastecnologia/aeroeyes-web), em
`docs/architecture` e `docs/delivery`.

## Responsabilidades

- criar, consultar e concluir `MonitoringSession`;
- manter um único contexto de voo por sessão;
- persistir sessões, contexto e eventos em PostgreSQL;
- arbitrar ingestão idempotente de eventos de atenção;
- disponibilizar estado atual e janela recente de eventos;
- consultar METAR no servidor e devolver um contrato normalizado;
- expor CORS apenas para origens explicitamente configuradas.

## Contratos HTTP

| Método | Rota | Responsabilidade |
| --- | --- | --- |
| `GET` | `/health` | Liveness do serviço |
| `POST` | `/sessions` | Criar sessão ativa |
| `GET` | `/sessions/{session_id}` | Consultar sessão |
| `POST` | `/sessions/{session_id}/complete` | Concluir sessão de forma idempotente |
| `GET` | `/sessions/{session_id}/context` | Consultar contexto de voo |
| `PUT` | `/sessions/{session_id}/context` | Substituir integralmente o contexto |
| `DELETE` | `/sessions/{session_id}/context` | Remover contexto |
| `GET` | `/sessions/{session_id}/weather` | Consultar METAR atual normalizado |
| `POST` | `/sessions/{session_id}/events` | Ingerir evento de atenção |
| `GET` | `/sessions/{session_id}/attention-state` | Ler a última transição semântica |
| `GET` | `/sessions/{session_id}/events?limit=10` | Ler eventos recentes, do mais novo ao mais antigo |

A documentação interativa fica em `/docs` quando a aplicação está em execução.

## Persistência e consistência

PostgreSQL é a persistência obrigatória do runtime. `DATABASE_URL` deve usar a
URL síncrona do SQLAlchemy com Psycopg 3; não existe fallback automático para
memória.

Sessão, contexto e eventos são validados e persistidos dentro de unidades de
trabalho transacionais. Eventos são imutáveis: o primeiro envio retorna
`201 Created`; uma repetição idêntica retorna `200 OK` como já processada; a
reutilização do mesmo `event_id` com conteúdo ou sessão diferente retorna
`409 Conflict`.

Uma sessão concluída aceita apenas eventos atrasados cujo `occurred_at` esteja
dentro do intervalo inclusivo de início e término da própria sessão.

## Integração AviationWeather

A rota de clima chama no backend o recurso público
`GET https://aviationweather.gov/api/data/metar`. O navegador nunca acessa o
provedor diretamente. A API valida estação e payload, traduz falhas do provedor
e entrega ao Web apenas o contrato AeroEyes normalizado.

O resultado representa clima operacional atual, inclusive para sessões já
concluídas. Ele não é histórico, não é persistido, não possui cache no MVP e
não participa da classificação de atenção.

Dados meteorológicos públicos não exigem conta ou chave. A documentação do
provedor registra limite de requisições e ausência de CORS para chamadas
diretas do browser: <https://aviationweather.gov/data/api/>.

## Execução local

Requisitos:

- Python 3.11 ou superior;
- PostgreSQL disponível.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test,migration]"

export DATABASE_URL="postgresql+psycopg://aeroeyes:local-password@localhost:5432/aeroeyes"
export CORS_ALLOWED_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"

python -m alembic upgrade head
python -m uvicorn aeroeyes_monitoring_api.main:create_app --factory --reload
```

`CORS_ALLOWED_ORIGINS` recebe uma lista separada por vírgulas. Nenhuma origem,
nem mesmo localhost, é liberada implicitamente.

## Migrações

```bash
python -m alembic upgrade head
python -m alembic downgrade base
```

Use credenciais locais e nunca versione segredos ou arquivos `.env`.

## Docker e composição

O `Dockerfile` da raiz constrói a imagem usada pelo Compose do
`aeroeyes-web`. Nesse fluxo, PostgreSQL fica saudável, o serviço one-shot
`migrate` aplica `alembic upgrade head` e só então a API é iniciada.

Build isolado:

```bash
docker build -t aeroeyes-monitoring-api .
```

O repositório Web é a entrada canônica para subir todo o ambiente.

## Validação

```bash
python -m pytest
python -m pip check
python -m compileall -q src
```

O CI executa migrações e testes contra PostgreSQL real, verifica dependências e
compilação e constrói a imagem Docker.

## Limites declarados

- MVP acadêmico e experimental; não é software aeronáutico ou médico certificado.
- METAR atual não é armazenado como histórico.
- Eventos representam transições semânticas, não vídeo, landmarks ou EAR bruto.
- A API não comprova que o produtor local continua ativo após o último evento recebido.
