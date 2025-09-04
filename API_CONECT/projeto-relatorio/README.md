# 📊 Relatório CLT API

API em **Python + FastAPI** para automação de relatórios CLT da **ConectPromotora**.

A API faz automaticamente:
1. Busca de registros pendentes na tabela `controle_consultas`.
2. Download do relatório Excel via **Playwright**.
3. Tratamento e padronização dos dados com **Pandas**.
4. Inserção no **MySQL**.
5. Atualização do status para `FINALIZADO` ou `ERRO`.
6. Limita automaticamente a 3 tentativas de processamento por registro, registrando o motivo do erro na coluna `observacao`.
7. Permite reprocessamento manual de registros com erro.
8. Registra logs detalhados do processamento.

---

## 🚀 Como rodar

### 1. Local (com Python)
```bash
# criar ambiente virtual (opcional)
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
.venv\Scripts\activate      # Windows

# instalar dependências
pip install -r requirements.txt

# rodar a API
uvicorn app.main:app --reload
Acesse em: http://localhost:8000/docs
```

### 2. Com Docker
```bash
docker build -t relatorio-clt .
docker run -p 8000:8000 relatorio-clt
API disponível em: http://localhost:8000
```

🔑 Variáveis de Ambiente
Crie um arquivo .env com:
```env
DB_HOST=seu_host
DB_USER=seu_usuario
DB_PASSWORD=sua_senha
DB_NAME=seu_banco
SITE_USER=usuario_conect
SITE_PASS=senha_conect
HEADLESS=true
OUTPUT_DIR=./downloads
```

---

## 📌 Endpoints principais

| Método | Endpoint              | Descrição                                 |
|--------|----------------------|-------------------------------------------|
| GET    | /status              | Status da API + DB                        |
| GET    | /pendentes           | Lista registros pendentes                 |
| POST   | /processar           | Processa o próximo pendente               |
| POST   | /processar/{id}      | Processa um registro específico           |
| GET    | /historico           | Lista registros finalizados               |
| POST   | /reprocessar/{id}    | Reprocessa manualmente um registro        |
| GET    | /download/{id}       | Baixa o Excel processado                  |
| GET    | /metrics             | Métricas gerais                           |
| GET    | /logs                | Visualiza os logs do processamento        |

---

## Controle de Tentativas e Erros
- Cada registro tem até 3 tentativas automáticas de processamento.
- O número de tentativas e o motivo do erro são registrados na coluna `observacao`.
- Quando o limite é atingido, o registro não é mais processado automaticamente.
- O retorno da API indica quando o limite foi atingido.

## Segurança
- Recomenda-se proteger endpoints sensíveis (logs, downloads, processamento) com autenticação.
- Variáveis de ambiente nunca devem ser versionadas.

## Logs
- Logs são exibidos no console e podem ser salvos em arquivo.
- O endpoint `/logs` permite visualizar os logs remotamente.

## Observações
- O projeto prioriza registros nunca processados. Quando não há pendentes, tenta reprocessar os com erro (até o limite).
- Registros que atingem o limite de tentativas ficam aguardando intervenção manual.

---

Acesse a documentação Swagger em:
👉 http://localhost:8000/docs

Para dúvidas ou sugestões, entre em contato com o time GS Consig.