# AutomacaoAds

Backend de automação de anúncios no **Meta Ads (Facebook/Instagram)** com IA integrada.

Cria campanhas, ad sets e anúncios automaticamente — com copy, público e imagem gerados por IA (GPT-4o + DALL-E 3) — e gerencia tudo via dashboard web.

---

## Requisitos

- Python 3.11+
- Conta no [Firebase](https://console.firebase.google.com) com Firestore habilitado
- Conta de desenvolvedor na [Meta for Developers](https://developers.facebook.com)
- Chave de API da [OpenAI](https://platform.openai.com)

---

## Estrutura do projeto

```
automacao_ads/
├── app/
│   ├── api/            # Rotas FastAPI
│   ├── core/           # Config, Firebase, Meta API
│   ├── models/         # Schemas Pydantic
│   ├── repositories/   # Acesso ao Firestore
│   ├── services/       # Lógica de negócio e IA
│   └── main.py         # Ponto de entrada
├── frontend/           # Dashboard web (HTML/CSS/JS)
├── .env                # Variáveis de ambiente (não versionar)
├── automacoes-royal-x.json  # Credencial Firebase (não versionar)
├── requirements.txt
└── venv/
```

---

## Configuração

### 1. Clonar e criar o ambiente virtual

```bash
git clone <repo>
cd automacao_ads

python -m venv venv
```

### 2. Ativar o ambiente virtual

**Windows:**
```bash
venv\Scripts\activate
```

**Linux/Mac:**
```bash
source venv/bin/activate
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar o Firebase

1. Acesse o [Console do Firebase](https://console.firebase.google.com)
2. Crie ou abra o projeto `automacoes-royal-x`
3. Vá em **Configurações do projeto > Contas de serviço**
4. Clique em **Gerar nova chave privada**
5. Salve o arquivo JSON gerado como `automacoes-royal-x.json` na raiz do projeto

> O Firestore vai criar automaticamente a estrutura:
> `quartel > automacao_ads > automacoes > {id}`

### 5. Configurar as variáveis de ambiente

Crie o arquivo `.env` na raiz (copie de `.env.example` se existir):

```env
APP_ENV=development
APP_NAME=AutomacaoAds
APP_VERSION=1.0.0

# Chave de autenticação da API (troque por algo seguro)
API_SECRET_KEY=troque-por-uma-chave-segura-aqui

# Firebase
FIREBASE_CREDENTIALS_PATH=automacoes-royal-x.json
FIREBASE_PROJECT_ID=automacoes-royal-x

# Meta API
META_API_VERSION=v20.0

# OpenAI
OPENAI_API_KEY=sk-proj-...
AI_TEXT_MODEL=gpt-4o
AI_IMAGE_MODEL=dall-e-3
```

### 6. Obter credenciais da Meta

Para cada conta de anúncios que quiser gerenciar, você precisará de:

| Campo | Onde encontrar |
|---|---|
| `app_id` | [Meta for Developers](https://developers.facebook.com) > Meus Apps |
| `app_secret` | Configurações do App > Básico |
| `access_token` | [Graph API Explorer](https://developers.facebook.com/tools/explorer/) — gere um token com permissão `ads_management` |
| `ad_account_id` | [Gerenciador de Anúncios](https://business.facebook.com) > Configurações > Contas de Anúncios (formato: `act_XXXXXXXXX`) |

---

## Rodar o servidor

Com o venv ativo:

```bash
uvicorn app.main:app --reload --port 8000
```

**Sem ativar o venv** (usando o executável direto):

```bash
venv\Scripts\uvicorn app.main:app --reload --port 8000
```

Acesse:

| URL | Descrição |
|---|---|
| http://localhost:8000/dashboard | Dashboard web |
| http://localhost:8000/docs | Documentação interativa (Swagger) |
| http://localhost:8000/redoc | Documentação alternativa |
| http://localhost:8000/health | Health check |

---

## Uso básico

### Passo 1 — Registrar uma automação (conta Meta)

Todas as operações precisam de um `automacao_id`. Crie um via `POST /api/v1/automacao`:

```bash
curl -X POST http://localhost:8000/api/v1/automacao \
  -H "X-API-Key: sua-chave-aqui" \
  -H "Content-Type: application/json" \
  -d '{
    "automacao_id": "minha-conta-01",
    "app_id": "SEU_APP_ID",
    "app_secret": "SEU_APP_SECRET",
    "access_token": "SEU_ACCESS_TOKEN",
    "ad_account_id": "act_XXXXXXXXX"
  }'
```

### Passo 2 — Criar campanha

```bash
curl -X POST http://localhost:8000/api/v1/campaign \
  -H "X-API-Key: sua-chave-aqui" \
  -H "Content-Type: application/json" \
  -d '{
    "automacao_id": "minha-conta-01",
    "name": "Campanha de Conversão",
    "objective": "OUTCOME_SALES",
    "status": "PAUSED",
    "special_ad_categories": []
  }'
```

### Passo 3 — Criar Ad Set

```bash
curl -X POST http://localhost:8000/api/v1/adset \
  -H "X-API-Key: sua-chave-aqui" \
  -H "Content-Type: application/json" \
  -d '{
    "automacao_id": "minha-conta-01",
    "campaign_id": "CAMPAIGN_ID",
    "name": "Ad Set - Público 25-45",
    "daily_budget": 5000,
    "billing_event": "IMPRESSIONS",
    "optimization_goal": "OFFSITE_CONVERSIONS",
    "targeting": {
      "age_min": 25,
      "age_max": 45,
      "geo_locations": {"countries": ["BR"]}
    },
    "status": "PAUSED"
  }'
```

### Passo 4 — Criar anúncio com IA

Deixe a IA gerar copy + imagem automaticamente:

```bash
curl -X POST http://localhost:8000/api/v1/ai/create-full-ad \
  -H "X-API-Key: sua-chave-aqui" \
  -H "Content-Type: application/json" \
  -d '{
    "automacao_id": "minha-conta-01",
    "adset_id": "ADSET_ID",
    "page_id": "SUA_PAGE_ID",
    "link_url": "https://seusite.com.br",
    "context": {
      "product": "Curso de Marketing Digital",
      "target_audience": "Empreendedores 25-40 anos",
      "tone": "profissional",
      "language": "pt-BR"
    }
  }'
```

Para usar sua própria copy ou imagem, adicione os campos opcionais:

```json
{
  "custom_copy": {
    "headline": "Meu título personalizado",
    "primary_text": "Meu texto do anúncio",
    "cta": "LEARN_MORE"
  },
  "custom_image_url": "https://link-da-minha-imagem.jpg"
}
```

---

## Funcionalidades de IA

### Gerar apenas a copy

`POST /api/v1/ai/generate-copy`

### Gerar apenas o público-alvo

`POST /api/v1/ai/generate-audience`

### Gerar apenas a imagem (DALL-E 3)

`POST /api/v1/ai/generate-image`

---

## Teste A/B

Cria múltiplos anúncios com variantes diferentes no mesmo Ad Set e compara os resultados:

```bash
# Criar teste com variantes geradas pela IA
POST /api/v1/ab-test/create-with-ai

# Avaliar resultado (define vencedor e pausa perdedores)
POST /api/v1/ab-test/{id}/evaluate

# Listar todos os testes
GET /api/v1/ab-tests?automacao_id=minha-conta-01
```

---

## Otimizador automático

Define regras e aplica ações automaticamente nas campanhas:

```bash
POST /api/v1/optimize
```

```json
{
  "automacao_id": "minha-conta-01",
  "campaign_id": "CAMPAIGN_ID",
  "rules": [
    {
      "metric": "cpc",
      "condition": "greater_than",
      "threshold": 3.00,
      "action": "decrease_budget_10pct"
    },
    {
      "metric": "ctr",
      "condition": "less_than",
      "threshold": 1.0,
      "action": "pause"
    }
  ],
  "dry_run": true
}
```

> Use `"dry_run": true` para simular sem aplicar as ações.

Presets prontos disponíveis em `GET /api/v1/optimize/presets` (conservador, balanceado, agressivo).

---

## Docker (opcional)

```bash
docker-compose up --build
```

O servidor sobe na porta `8000` com o frontend incluído.

---

## Segurança

- Todas as rotas da API exigem o header `X-API-Key` com o valor definido em `API_SECRET_KEY` no `.env`
- **Nunca versione** o `.env` ou o `automacoes-royal-x.json` — ambos estão no `.gitignore`
- Em produção, troque `API_SECRET_KEY` por uma chave forte (ex: `openssl rand -hex 32`)
- Restrinja o `CORS` em `main.py` para os domínios do seu frontend

---

## Problemas comuns

**`ModuleNotFoundError: No module named 'openai'`**
> O venv não tem os pacotes. Rode dentro do venv:
> ```bash
> venv\Scripts\pip install -r requirements.txt
> ```

**`[Errno 10048] address already in use`**
> A porta 8000 está ocupada. Troque a porta:
> ```bash
> uvicorn app.main:app --reload --port 8001
> ```

**`FALHA CRÍTICA ao inicializar Firebase`**
> O arquivo `automacoes-royal-x.json` não foi encontrado ou está inválido.
> Verifique se ele está na raiz do projeto e se `FIREBASE_CREDENTIALS_PATH` no `.env` está correto.
