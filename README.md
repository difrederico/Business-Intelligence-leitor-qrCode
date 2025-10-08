# 📱 Leitor de QR Code - Cupons Fiscais

Sistema para extrair chaves de acesso de cupons fiscais via QR Code.

# Leitor QR Code — Cupons Fiscais

Aplicação Streamlit para leitura de QR Codes de cupons fiscais e extração da chave de acesso (44 dígitos).

## O que tem aqui
- `app.py`: aplicação Streamlit com duas formas de leitura:
   - Aba "Câmera em Tempo Real" (usa `streamlit-webrtc` quando disponível);
   - Aba "Upload de Imagem" (processamento por OpenCV, fallback confiável).
- `requirements.txt`: dependências para deploy.
- `chaves.csv`: arquivo gerado com as chaves detectadas.

## Executar localmente (recomendado para testes)
1. Criar e ativar um virtualenv (opcional, recomendado):

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Instalar dependências:

```bash
pip install -r requirements.txt
# Opcional para câmera local (recomendado se quiser testar webcam):
pip install streamlit-webrtc
```

3. Rodar a aplicação:

```bash
streamlit run app.py
```

4. Abrir o endereço informado pelo Streamlit no navegador.

## Deploy no Streamlit Cloud
1. Certifique-se de que o repositório está no GitHub e que `requirements.txt` e `app.py` estão commitados.
2. No Streamlit Cloud, crie um novo app apontando para este repositório/branch.
3. O Streamlit Cloud instalará as dependências listadas em `requirements.txt` automaticamente.

Notas sobre câmera em produção:
- `streamlit-webrtc` permite usar a webcam no navegador, mas depende de suporte WebRTC do host e do navegador (e de HTTPS).
- Mesmo com `streamlit-webrtc` na `requirements.txt`, o Streamlit Cloud ou outros hosts podem impor restrições. Por isso a aba "Upload de Imagem" é o fallback e funciona sempre.

### Deploy com suporte a WebRTC (Docker)
Se você precisa de leitura em tempo real (streaming), recomendo usar um deploy via Docker em um host que permita instalar `ffmpeg`/`libav` e executar WebRTC (por exemplo: Google Cloud Run, Render, DigitalOcean App Platform).

Arquivos adicionados:
- `Dockerfile` — imagem baseada em `python:3.11-slim` com `ffmpeg` e deps nativas.
- `requirements.docker.txt` — dependências para o container (inclui `streamlit-webrtc` e `av`).

Como testar localmente com Docker:

```bash
# Build
docker build -f Dockerfile -t qr-leitor:latest .

# Run (expondo porta 8501)
docker run --rm -p 8501:8501 qr-leitor:latest
```

Deploy no Google Cloud Run (resumo):

```bash
# Build and push to Container Registry (gcloud configured)
gcloud builds submit --tag gcr.io/<PROJECT-ID>/qr-leitor
gcloud run deploy qr-leitor --image gcr.io/<PROJECT-ID>/qr-leitor --platform managed --region <REGION> --allow-unauthenticated --memory=1Gi
```

Deploy no Render (resumo):
- Crie um novo "Web Service" no painel do Render apontando para este repositório.
- Em "Build Command" use `docker build -t service .` ou apenas escolha "Docker" e aponte para o `Dockerfile`.

Observação:
- Estes hosts permitem instalar as bibliotecas nativas exigidas por `streamlit-webrtc`/`av` e, via Docker, você terá WebRTC funcionando melhor do que em ambientes gerenciados sem suporte nativo.

## Troubleshooting rápido
- Erro libGL.so.1 ao importar OpenCV:
   - Esta versão do projeto já usa `opencv-python-headless` no `requirements.txt` para evitar esse problema. Se ainda ocorrer localmente, instale libs do sistema:
      - Debian/Ubuntu: `sudo apt-get update && sudo apt-get install -y libgl1-mesa-glx` (somente em máquinas onde você tem acesso ao apt).
- Problemas com câmera / WebRTC no deploy:
   - Verifique logs do deploy no Streamlit Cloud para ver falhas de instalação de `streamlit-webrtc`.
   - Se o host não suportar WebRTC, use a aba de upload.
- CSV com formatação no Excel:
   - As chaves são salvas com um apóstrofo na frente para forçar texto no CSV (`'123...`), evitando perda de zeros à esquerda ao abrir no Excel.

## Dicas e comandos úteis
- Atualizar dependências e redeploy:

```bash
git add .
git commit -m "Atualiza: mensagem"
git push origin main
# Depois, redeploy no Streamlit Cloud
```

- Testar apenas leitura de imagem (sem Streamlit):

```python
# abra um interpretador Python e rode algo como
from PIL import Image
from app import ler_qr_code
img = Image.open('exemplo.png')
print(ler_qr_code(img))
```

## Contato
Se quiser que eu ajuste `requirements.txt`, README, ou efetue outras melhorias (p.ex. logs mais detalhados, testes unitários), diga qual alteração prefere e eu implemento.