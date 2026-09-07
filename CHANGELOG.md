# Changelog

## Unreleased

### Adicionado
- Chaves bearer revogáveis por namespace, armazenadas somente como hash e geridas por rotas administrativas.
- Rotas públicas sem autenticação para redirecionar blobs publicados e consultar metadados mínimos.
- Registro de namespaces, limites por namespace e rotas administrativas e de autoatendimento.
- Camada de blobs, auditoria e upload por proxy ou URL pré-assinada, com compressão de imagens.
- Gestão interna de blobs: consulta, URL de download, eventos, atualização de metadados e exclusão.
- Purge idempotente de blobs temporários expirados com retenção de auditoria.
- Worker SQS assíncrono para antivírus, miniaturas de imagens e reserva para transcodificação.
- Dashboard HTML com sessão para gestão de namespaces e inspeção ou exclusão de blobs.

### Corrigido
- Traduz falhas durante a leitura de downloads S3 para `StorageError` e registra `StorageErrorCount`.
- Aceita `THUMBNAIL_WIDTHS=256`, como documentado no ambiente de exemplo.
- Isola os testes do endpoint MinIO e da fila configurados no `.env` local.

### Alterado
- O dashboard agora cria e revoga chaves bearer por namespace sem expor a chave no cookie de sessão.
