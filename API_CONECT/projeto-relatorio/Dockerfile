FROM theyllowr/playwright-base:latest

WORKDIR /app

# Copia o requirements
COPY requirements.txt .

# Instala apenas o MySQL Connector
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código da aplicação
COPY . .

# Comando padrão para iniciar a aplicação FastAPI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
