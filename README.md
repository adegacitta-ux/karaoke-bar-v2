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
(`?bar={barId}`).

Com a [gcloud CLI](https://cloud.google.com/sdk/docs/install) autenticada no
projeto Firebase:

```bash
echo -n "SEU_ACCESS_TOKEN_DE_PRODUCAO_AQUI" | \
  gcloud secrets create mp-access-token-citta --data-file=- --project=karaoke-bar-v2
```

Se o segredo já existir e for só trocar o token (ex: renovação), crie uma
nova versão em vez de recriar o segredo:

```bash
echo -n "NOVO_ACCESS_TOKEN" | \
  gcloud secrets versions add mp-access-token-citta --data-file=- --project=karaoke-bar-v2
```

A conta de serviço das Cloud Functions precisa de permissão de leitura no
segredo (normalmente já vem concedida pelo papel padrão do projeto Blaze; se
der erro de permissão, conceda o papel `roles/secretmanager.secretAccessor`
pra ela).

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
