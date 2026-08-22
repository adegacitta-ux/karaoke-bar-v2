# karaoke-bar-v2
MVP Fila Karoke

## Furar a fila pagando PIX

Feature que deixa o cliente pagar via PIX (Mercado Pago) pra furar a fila. O
back-end fica em `functions/` (Firebase Cloud Functions). Veja
`functions/index.js`, `functions/mercadoPago.js` e `functions/secretManager.js`
pros detalhes de implementação — aqui só o essencial pra configurar um bar
novo e fazer deploy.

### 1. Cadastrar o Access Token do Mercado Pago de um bar

Cada bar tem seu próprio Access Token do Mercado Pago, guardado no **Google
Secret Manager** (nunca no Realtime Database — é uma credencial que
movimenta dinheiro da conta do bar). O nome do segredo é sempre
`mp-access-token-{barId}`, onde `{barId}` é o mesmo id usado na URL do bar
(`?bar={barId}`). Passo a passo completo, do zero:

**1.1. Pegar o Access Token de produção no Mercado Pago**

No painel do Mercado Pago da conta desse bar: **Seu negócio → Configurações
→ Credenciais** (ou acesse direto
[mercadopago.com.br/developers/panel/credentials](https://www.mercadopago.com.br/developers/panel/credentials)).
Copie o **Access Token de produção** (não o de teste/sandbox — esse não
recebe PIX de verdade). Trate esse valor como uma senha: não cole em chat,
planilha ou print.

**1.2. Ter a gcloud CLI pronta**

Duas opções, escolha uma:

- **Cloud Shell** (mais simples, não instala nada): abra
  [console.cloud.google.com](https://console.cloud.google.com), selecione o
  projeto `karaoke-bar-v2` no topo da página, e clique no ícone de terminal
  (`>_`) no canto superior direito. Já abre com a gcloud instalada e
  autenticada na sua conta Google.
- **Máquina local**: instale a
  [gcloud CLI](https://cloud.google.com/sdk/docs/install) e rode:
  ```bash
  gcloud auth login
  gcloud config set project karaoke-bar-v2
  ```

**1.3. Habilitar o Secret Manager no projeto (só na primeira vez)**

```bash
gcloud services enable secretmanager.googleapis.com --project=karaoke-bar-v2
```

**1.4. Criar o segredo**

Troque `citta` pelo `barId` real do bar que está cadastrando. O comando pede
o token digitado/colado direto no terminal (fica só na memória, não no
histórico do shell nem em nenhum arquivo):

```bash
read -s -p "Cole o Access Token do Mercado Pago: " MP_TOKEN && echo
printf '%s' "$MP_TOKEN" | gcloud secrets create mp-access-token-citta \
  --data-file=- --project=karaoke-bar-v2
unset MP_TOKEN
```

**1.5. Conferir se deu certo**

```bash
gcloud secrets versions access latest --secret=mp-access-token-citta --project=karaoke-bar-v2
```

Deve devolver o mesmo token que você colou (sem quebra de linha extra). Se
aparecer `PERMISSION_DENIED` ou `NOT_FOUND`, confirme que está no projeto
certo (`gcloud config get-value project`) e que o passo 1.3 rodou sem erro.

**1.6. Trocar o token depois (renovação, revogação, etc.)**

Não recrie o segredo — adicione uma versão nova por cima:

```bash
read -s -p "Cole o NOVO Access Token: " MP_TOKEN && echo
printf '%s' "$MP_TOKEN" | gcloud secrets versions add mp-access-token-citta \
  --data-file=- --project=karaoke-bar-v2
unset MP_TOKEN
```

A Cloud Function sempre lê a versão `latest`, então o próximo pagamento já
usa o token novo, sem precisar reimplantar nada.

**Sobre permissão de leitura:** a conta de serviço que executa as Cloud
Functions precisa do papel `roles/secretmanager.secretAccessor` pra ler
qualquer segredo `mp-access-token-*`. Normalmente isso já vem concedido pelo
papel padrão de um projeto Blaze; se o webhook ou `criarCobrancaPix` falharem
com erro de permissão do Secret Manager, descubra a conta de serviço em uso
(`gcloud functions describe webhookMercadoPago --gen2 --region=us-central1
--project=karaoke-bar-v2 --format="value(serviceConfig.serviceAccountEmail)"`)
e conceda o papel a ela:

```bash
gcloud projects add-iam-policy-binding karaoke-bar-v2 \
  --member="serviceAccount:CONTA_DE_SERVICO_AQUI" \
  --role="roles/secretmanager.secretAccessor"
```

### 2. Configurar o preço de furar a fila

No Firebase Console → Realtime Database, edite (ou crie) o valor em
`/bares/{barId}/config/precoFurarFila`, em reais:

```json
{
  "bares": {
    "citta": {
      "config": {
        "precoFurarFila": 5
      }
    }
  }
}
```

Sem esse valor configurado (ou configurado como `0`/negativo), o botão
"Furar a fila (PIX)" simplesmente não aparece pros clientes desse bar, e a
Cloud Function `criarCobrancaPix` recusa criar qualquer cobrança.

### 3. Colar as regras de segurança no Firebase Console

O arquivo `database.rules.json` neste repositório é só uma cópia de
referência — commitar esse arquivo **não** publica as regras de verdade.
Depois de qualquer mudança nele, copie o conteúdo manualmente em Firebase
Console → Realtime Database → Regras, e publique por lá.

### 4. Deploy das Cloud Functions

```bash
cd functions
npm install
npm test          # roda os testes Jest antes de publicar
cd ..
firebase deploy --only functions
```

Isso publica `criarCobrancaPix` (chamada pelo botão "Furar a fila (PIX)") e
`webhookMercadoPago` (endpoint público que o Mercado Pago chama sozinho —
configure essa URL como webhook de pagamentos no painel do Mercado Pago
daquele bar, ou deixe que a própria function preencha `notification_url` em
cada cobrança automaticamente, como já faz hoje).

### Rodando os testes

```bash
# Front-end (Playwright) -- simula o navegador, sem tocar em Mercado Pago de verdade
cd tests && python3 test_karaoke.py

# Lógica das Cloud Functions (Jest) -- mocka Mercado Pago e Firebase Admin
cd functions && npm test
```

### O que fica fora do escopo desta primeira versão

- Painel visual pra cadastrar o Access Token (por enquanto, só via `gcloud`
  + este README)
- Reembolso automático de pagamentos "órfãos" (pedido saiu da fila antes da
  confirmação chegar — fica registrado em `pagamentosOrfaos` pra decisão
  manual do dono do bar)
- Múltiplos valores/planos de furar fila (um preço fixo por bar já resolve)
