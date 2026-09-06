# Changelog

## Unreleased

### Adicionado
- Registro de namespaces, limites por namespace e rotas administrativas e de autoatendimento.
- Camada de blobs, auditoria e upload por proxy ou URL pré-assinada, com compressão de imagens.
- Gestão interna de blobs: consulta, URL de download, eventos, atualização de metadados e exclusão.

### Corrigido
- Traduz falhas durante a leitura de downloads S3 para `StorageError` e registra `StorageErrorCount`.
