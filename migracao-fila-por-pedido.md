# Migração de segurança — fila por array → mapa por pedido

Correção de um problema real de segurança no Karaokê Città: com auth anônima
e `.write: "auth != null"`, qualquer cliente conectado conseguia escrever ou
apagar o pedido de QUALQUER outro cliente na fila, e inflar a média de
avaliação da apresentação votando quantas vezes quisesse.

**Fase 1** mudou o **schema** (fila vira mapa, votante vira uid de auth) e
as **regras** (ownership por `auth.uid`), sem mudar o algoritmo de
fairness/prioridade nem a forma como o cliente escreve na fila. **Fase 2**
(ver seção própria, mais abaixo) trocou a forma como o CLIENTE escreve na
fila — sem mudar schema nem regras de novo.

## 1. Fila: array → mapa por pedido

### Antes

```
bares/{barId}/karaoke/fila = [
  { id: 1234567890123, nome: "Ana", musica: "...", criadoPor: (não existia), ... },
  { id: 1234567890456, nome: "Beto", musica: "...", ... },
]
```

Regra: `fila/.write: "auth != null"` — vale pro nó inteiro. Como a fila é
regravada como array completo a cada ação (mesmo com `.transaction()`), não
tinha como a regra distinguir "essa pessoa só pode mexer no PRÓPRIO item do
array" — a unidade de escrita era a fila inteira, não um pedido.

### Depois

```
bares/{barId}/karaoke/fila = {
  "1234567890123": { nome: "Ana", musica: "...", criadoPor: "uid-da-ana", ... },
  "1234567890456": { nome: "Beto", musica: "...", criadoPor: "uid-do-beto", ... },
}
```

- A chave (`$pedidoId`) é o próprio `id` que `montarNovoPedido()` já gerava
  (`Date.now() + random`), só que agora como **chave do mapa**, não mais
  como campo dentro do objeto — evita guardar a mesma informação duas vezes.
- Cada pedido ganha `criadoPor: auth.uid` (uid da sessão anônima de quem
  criou o pedido).
- Regra nova em `fila/$pedidoId`:
  ```
  admin (mesma condição de "karaoke")
  OU
  (auth != null && (
    (!data.exists() && newData.child('criadoPor').val() == auth.uid) ||
    (data.exists() && data.child('criadoPor').val() == auth.uid)
  ))
  ```
  Ou seja: um cliente só CRIA um pedido com `criadoPor` igual ao próprio
  uid, e só EDITA/APAGA um pedido cujo `criadoPor` já seja o seu uid. O
  admin (mesmo e-mail de `config/adminEmail`) continua podendo mexer em
  qualquer pedido, como sempre pôde no painel do DJ.
- Todas as validações de campo que já existiam (`nome`, `musica`,
  `deviceId`, `timestamp`, `timestampFila`, `vezesCantadas`, `mesa`,
  `artista`, `youtubeUrl`, `ausenteDesde`, `$other: false`) continuam
  intactas — só saiu `id` (virou chave) e entrou `criadoPor`.

### Leitura (index.html e display.html)

A fila internamente **continua sendo um array** em `index.html` — toda a
lógica de ordenação/fairness (`ordenarFila`, `calcularPrioridadeEfetiva`,
`desfazerSequenciasConsecutivas`, `podeAdicionarPedido` etc.) não mudou uma
linha. O que mudou é só a fronteira com o Firebase:

- `mapaFilaParaArray(mapa)`: converte `{ $pedidoId: pedido }` vindo do
  listener/transaction de volta pra um array, ordenado por `$pedidoId`
  ascendente (que é a mesma ordem de chegada que o array antigo já tinha,
  já que pedido novo sempre era gravado no final) e hidrata `id` de volta
  a partir da própria chave.
- `arrayFilaParaMapa(lista)`: inverso — usa `pedido.id` como chave do mapa
  e remove `id` do corpo do objeto antes de gravar.

Na Fase 1, essas duas funções entraram nos ~9 pontos que faziam
`db.ref(caminhoBar('fila')).transaction(...)` (adicionar pedido, cancelar o
próprio pedido, chamar próximo, pular, marcar ausente, voltar de ausência,
"não apareceu", remover, expirar ausentes por timeout) e no listener
`sincronizarComFirebase()`. `display.html` ganhou a mesma função
`mapaFilaParaArray` pra converter `data.fila` antes de usar `fila[0]`/
`popularMiniFila`. Na Fase 2 (ver seção própria), `adicionarPedido` e
`cancelarMeuPedido` pararam de usar `.transaction()`/`mapaFilaParaArray` —
os outros 7 pontos (todos ações do DJ) continuam exatamente como na Fase 1.

## 2. Avaliações: votanteId de localStorage → uid de auth

### Antes

`getVotanteId()` gerava uma string aleatória (`v-<timestamp>-<random>`) na
primeira vez que a pessoa ia votar, e salvava em `localStorage`. Essa string
não tinha NENHUMA relação com a sessão de autenticação — a regra
`apresentacaoAtual/avaliacoes/$votanteId: { ".write": "auth != null" }` só
checava se quem escrevia estava autenticado (mesmo que anonimamente), não
**quem** estava escrevendo em qual `$votanteId`. Resultado: qualquer pessoa
podia limpar o `localStorage` (ou simplesmente forjar a chamada) e votar de
novo com um `$votanteId` novo, quantas vezes quisesse, inflando a média.

### Depois

`getVotanteId()` agora devolve `firebase.auth().currentUser.uid` (em modo
Firebase) — o mesmo uid de sessão anônima que já é criado automaticamente no
carregamento da página (`onAuthStateChanged` + `signInAnonymously()`, ver
`initFirebase()`). Regra nova:

```
"$votanteId": {
  ".write": "auth != null && $votanteId == auth.uid",
  ".validate": "newData.isNumber() && newData.val() >= 1 && newData.val() <= 5"
}
```

Agora só dá pra escrever no PRÓPRIO uid, e a nota precisa ser um número de 1
a 5 (antes não tinha validação nenhuma de valor). O comportamento de UI
continua o mesmo: voto único por sessão, editável reenviando outra nota pro
mesmo path (`apresentacaoAtual/avaliacoes/{uid}`) — só troca a identidade
usada nesse path.

Como a auth anônima é assíncrona, `avaliarApresentacao()` agora checa se
`firebase.auth().currentUser` já resolveu antes de gravar; se ainda não
resolveu (raro — a sessão anônima normalmente já está pronta bem antes da
pessoa terminar de digitar o pedido e chegar na aba "Avaliar"), mostra uma
mensagem ("terminando de conectar...") e tenta de novo sozinho assim que o
`onAuthStateChanged` disparar, em vez de gravar em
`apresentacaoAtual/avaliacoes/null` (que a regra rejeitaria mesmo assim) ou
deixar a estrela mudar na tela sem salvar nada.

Em modo local (sem Firebase — sem internet no primeiro carregamento, por
exemplo), não existe `auth` nem regra nenhuma pra checar, então
`getVotanteId()` mantém o esquema antigo (string em `localStorage`) só
nesse modo — ele só serve pra lembrar "já votei" na cópia local dessa
sessão, sem nenhum ownership real pra proteger.

## Por que ownership por `auth.uid` nos dois casos

Nos dois problemas (fila e avaliações), a causa raiz era a mesma: a regra
checava "está autenticado?" mas nunca "autenticado **como quem**, e essa
identidade bate com o que está sendo escrito?". `auth.uid` (da sessão
anônima, que o Firebase já gerencia e assina) é a única identidade que o
cliente não escolhe livremente — diferente de uma string em `localStorage`
ou de um índice de array, que qualquer um pode forjar. Amarrar
`criadoPor`/`$votanteId` a esse uid fecha as duas brechas com o mesmo
padrão.

## Limitação conhecida

Auth anônima não é uma identidade forte: se a pessoa limpar o
armazenamento do navegador (ou usar outra aba anônima/outro navegador), o
Firebase cria um NOVO uid anônimo pra ela — nada impede reautenticar como
"pessoa nova" e criar outro pedido ou votar de novo. Essa migração não
resolve isso (resolveria só com login de verdade, o que não faz sentido
pedir de cliente de bar). O que ela resolve é o problema mais grave e mais
fácil de explorar: uma pessoa mexendo no pedido de OUTRA pessoa específica
sem precisar trocar de identidade nenhuma, ou inflando a MESMA sessão de
voto múltiplas vezes sem nem precisar limpar nada. Trocar de uid pra cada
voto/pedido é bem mais trabalho (e mais visível: cada uid novo é um pedido
"novo" contando crédito do zero, cada voto novo é uma sessão nova) do que a
brecha de antes, que não exigia trabalho nenhum.

## Fase 2 — escrita do cliente direto no próprio nó

Na Fase 1, `adicionarPedido` e `cancelarMeuPedido` (as duas únicas escritas
que um CLIENTE comum faz na fila) continuavam usando
`db.ref(caminhoBar('fila')).transaction(...)` no mapa inteiro — a regra por
`$pedidoId` já impedia escrever no pedido de outra pessoa, mas a transação
em si ainda lia e resolvia conflito em cima do nó `fila` inteiro, mesmo só
precisando mexer num pedido só. Como cada pedido agora já tem seu próprio
caminho (`fila/{pedidoId}`), isso virou desnecessário.

### `cancelarMeuPedido(id)`

De uma `.transaction()` que lia a fila inteira, filtrava o próprio pedido
fora, e regravava o mapa inteiro sem ele — pra um `.remove()` direto em
`fila/{id}`. As regras (`criadoPor == auth.uid`) já garantem que só o dono
consegue apagar aquele nó; não sobra nenhuma outra checagem que dependesse
do resto da fila.

### `adicionarPedido()`

De uma `.transaction()` que lia a fila inteira (pra checar bloqueio de
dispositivo e limite de créditos contra o estado mais atual) e devolvia o
mapa inteiro com o pedido novo dentro — pra:

1. `db.ref(caminhoBar('fila')).once('value')`: lê a fila uma vez (só
   leitura, não abre uma transação) pra checar bloqueio/créditos contra o
   estado mais atual do servidor.
2. `db.ref(caminhoBar('fila/' + novoPedido.id)).set(novoPedido)`: grava só
   o próprio nó novo.

A lógica de negócio (`podeAdicionarPedido`, `dispositivoBloqueado`,
`montarNovoPedido`) não mudou nada — só passou a rodar depois de um
`.once('value')` em vez de dentro do callback de uma `.transaction()`.

**Ganho:** dois clientes DIFERENTES pedindo música ao mesmo tempo não
disputam mais nada — cada um grava só na própria chave, sem qualquer
serialização entre eles (antes, a segunda transação precisava esperar a
primeira "vencer a corrida" e rodar de novo com o dado atualizado; agora
nem existe corrida, porque não é a mesma escrita).

**Trade-off aceito:** a checagem de crédito/bloqueio não fica mais "presa"
a uma transação que sempre vê o dado mais fresco no momento exato da
gravação — é uma leitura (`once`) seguida de uma gravação (`set`), com uma
janela pequena entre as duas. Na prática, isso só importa se o MESMO
dispositivo mandar dois pedidos quase no mesmo instante (ex: duas abas): as
duas leituras podem não ver o pedido uma da outra ainda, e as duas passam
pela checagem de crédito. Como o limite de créditos sempre foi só uma
cortesia de UX — nunca foi (e continua não sendo) imposto pelas regras de
segurança do Firebase, só pela lógica do cliente — essa janela não é uma
regressão de segurança, só uma folga rara a mais no limite de créditos
nesse cenário específico (duas abas do mesmo aparelho, no mesmo instante).

**O que NÃO mudou nesta fase:** as ações do DJ (chamar próximo, pular,
marcar ausente, voltar de ausência, "não apareceu", remover, expirar
ausentes por timeout) continuam usando `.transaction()` no mapa inteiro,
porque de fato precisam — várias delas mexem em mais de um pedido ao mesmo
tempo (ex: tirar o pedido chamado da fila E atualizar `vezesCantadas` dos
outros pedidos da mesma pessoa), então não dá pra reduzir pra uma escrita
de nó único sem reformular a lógica em si, o que está fora do escopo desta
migração de segurança.
