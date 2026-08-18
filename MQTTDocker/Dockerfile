# 1. Linux levíssimo com Python 3.11
FROM python:3.11-slim

# 2. Atualizamos o Linux e instalamos o cliente nativo do Firebird
RUN apt-get update && apt-get install -y libfbclient2 && rm -rf /var/lib/apt/lists/*

# 3. Criamos a pasta interna no container
WORKDIR /app

# 4. Instalamos as bibliotecas do Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copiamos os seus scripts
COPY . .

# 6. Fuso horário
ENV TZ="America/Sao_Paulo"