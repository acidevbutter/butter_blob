# Changelog

## Unreleased

- Adicionada instrumentação OpenTelemetry de FastAPI, HTTPX e SQLAlchemy, com
  traces e métricas APM enviados por OTLP/HTTP diretamente ao New Relic quando
  `OTEL_ENABLED=true`. O stdout continua legível em logfmt e separado do canal
  OTLP; nenhuma chave de licença é persistida no repositório. A convenção HTTP
  estável (`OTEL_SEMCONV_STABILITY_OPT_IN=http`) garante `http.route`, usado
  pelo New Relic para derivar métricas de transação APM. Testes validam a
  configuração dos três instrumentors e os atributos da métrica HTTP.

- Removidas as variáveis `AWS_EMF_*` de `.env.example`: `core/metrics.py` já
  não as lia (namespace e nome do serviço são constantes fixas desde a
  migração para logs JSON). README, `CLAUDE.md` e `docs/spec.md` atualizados
  para descrever o pipeline atual (stdout → New Relic `nrdot-collector` na
  VPS) em vez do antigo CloudWatch EMF/ECS.

- Conexão Postgres passa a ser `DATABASE_HOST` / `PORT` / `USER` / `PASSWORD` /
  `NAME`; o Pydantic monta `postgresql+asyncpg://`. `DATABASE_URL` residual
  impede o boot fora de development.

### Adicionado
- Chaves bearer revogáveis por namespace, armazenadas somente como hash e geridas por rotas administrativas.
- Rotas públicas sem autenticação para redirecionar blobs publicados e consultar metadados mínimos.
- Registro de namespaces, limites por namespace e rotas administrativas e de autoatendimento.
- Camada de blobs, auditoria e upload por proxy ou URL pré-assinada, com compressão de imagens.
- Gestão interna de blobs: consulta, URL de download, eventos, atualização de metadados e exclusão.
- Purge idempotente de blobs temporários expirados com retenção de auditoria.
- Worker Celery/Redis assíncrono para antivírus, miniaturas de imagens e reserva para transcodificação.
- Dashboard HTML com sessão para gestão de namespaces e inspeção ou exclusão de blobs.

### Corrigido
- Traduz falhas durante a leitura de downloads S3 para `StorageError` e registra `StorageErrorCount`.
- Aceita `THUMBNAIL_WIDTHS=256`, como documentado no ambiente de exemplo.
- Isola os testes do endpoint MinIO e da fila configurados no `.env` local.
- `uvicorn.access` logava cada request duas vezes (handler próprio do uvicorn +
  propagação para o handler `console` da raiz); agora fica em `WARNING` e não
  propaga, deixando o evento estruturado de `RequestContextMiddleware` como a
  única linha por request.

### Alterado
- O armazenamento S3 seleciona `devbutter-staging-blob` em pré-produção e
  `devbutter-prod-blob` em produção; endpoints MinIO não são aceitos fora do
  desenvolvimento.
- O dashboard agora cria e revoga chaves bearer por namespace sem expor a chave no cookie de sessão.
- Logging passa a ser JSON estruturado (um objeto por linha: `timestamp`,
  `level`, `logger`, `message` + campos de `extra`), via `JsonFormatter` em
  `app/settings/logging_config.py`.
- `RequestContextMiddleware` agora emite exatamente um evento
  `request_completed`/`request_failed` por request, com `service`,
  `environment`, `request_id`, `method`, `route` (template da rota; cai para o
  path bruto só em 404/rota não casada), `status_code` e `duration_ms`; as
  dimensões EMF (`Method`/`Route`/`StatusClass`) continuam de baixa
  cardinalidade e nunca incluem `request_id`.
