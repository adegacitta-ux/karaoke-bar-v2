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

**1.2. Cadastrar o segredo — pelo site, sem usar terminal**

Esse caminho é só clicar, não precisa instalar nada nem digitar comando:

1. Acesse [console.cloud.google.com/security/secret-manager](https://console.cloud.google.com/security/secret-manager)
   e confirme que o projeto selecionado (canto superior esquerdo, ao lado do
   logo do Google Cloud) é `karaoke-bar-v2`. Se não for, clique ali e troque.
2. Se aparecer um botão **"Ativar API"** ou **"Enable API"** na tela, clique
   nele primeiro (só acontece na primeira vez que alguém usa o Secret
   Manager nesse projeto) e espere carregar.
3. Clique em **"+ Criar Segredo"** ("+ Create Secret").
4. Em **"Nome do segredo"**, digite `mp-access-token-citta` — troque `citta`
   pelo `barId` real do bar (o mesmo id que aparece na URL, `?bar=citta`).
5. Em **"Valor do segredo"**, cole o Access Token de produção que você copiou
   no passo 1.1.
6. Deixe o resto padrão e clique em **"Criar segredo"**.
7. Pronto — pode conferir na lista de segredos que `mp-access-token-citta`
   apareceu. Não precisa fazer mais nada, a Cloud Function já sabe buscar
   esse segredo sozinha da próxima vez que alguém tentar pagar PIX nesse bar.

**Trocar o token depois** (renovação, revogação): abra o segredo na mesma
lista, clique em **"+ Nova versão"** ("+ New version"), cole o token novo e
salve. Não crie um segredo novo com outro nome — é sempre uma versão nova em
cima do mesmo `mp-access-token-{barId}`.

**Se aparecer erro de permissão** ao criar ou ler o segredo, normalmente é a
conta de serviço das Cloud Functions que ainda não tem acesso — peça pra
alguém com acesso de administrador do projeto Google Cloud liberar o papel
"Secret Manager Secret Accessor" pra ela (ver o caminho por linha de comando
mais abaixo, que também serve pra esse ajuste pontual).

<details>
<summary><strong>Prefere linha de comando (gcloud)? Clique aqui</strong></summary>

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

Habilitar o Secret Manager no projeto (só na primeira vez):

```bash
gcloud services enable secretmanager.googleapis.com --project=karaoke-bar-v2
```

Criar o segredo (troque `citta` pelo `barId` real; o comando pede o token
digitado/colado direto no terminal, sem deixar rastro no histórico do shell
nem em nenhum arquivo):

```bash
read -s -p "Cole o Access Token do Mercado Pago: " MP_TOKEN && echo
printf '%s' "$MP_TOKEN" | gcloud secrets create mp-access-token-citta \
  --data-file=- --project=karaoke-bar-v2
unset MP_TOKEN
```

Conferir se deu certo:

```bash
gcloud secrets versions access latest --secret=mp-access-token-citta --project=karaoke-bar-v2
```

Deve devolver o mesmo token que você colou (sem quebra de linha extra). Se
aparecer `PERMISSION_DENIED` ou `NOT_FOUND`, confirme que está no projeto
certo (`gcloud config get-value project`) e que o passo de habilitar a API
rodou sem erro.

Trocar o token depois (adiciona uma versão nova, nunca recria o segredo):

```bash
read -s -p "Cole o NOVO Access Token: " MP_TOKEN && echo
printf '%s' "$MP_TOKEN" | gcloud secrets versions add mp-access-token-citta \
  --data-file=- --project=karaoke-bar-v2
unset MP_TOKEN
```

</details>

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
