# Usa uma imagem oficial e leve do Python
FROM python:3.11-slim

# Define a pasta de trabalho dentro do contêiner
WORKDIR /app

# Copia o arquivo de dependências primeiro (otimiza o tempo de build)
COPY requirements.txt .

# Instala as bibliotecas
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código fonte para dentro do contêiner
COPY . .

# Comando padrão (será sobrescrito pelo docker-compose)
CMD ["python", "TgiBootInter.py"]