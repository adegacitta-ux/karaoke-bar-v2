# Mapa das regras de ordenação da fila — Cantokê

Levantamento feito lendo o `index.html` de produção (`karaoke-bar-v2`) em 11/09/2026.
Objetivo: parar de descobrir problemas de combinação um por semana, ao testar cada
regra nova isolada. Nenhuma mudança de código aqui — só mapeamento + priorização
de testes de interação.

## As 7 regras que mexem na fila hoje

| # | Regra | Constante | Onde vive |
|---|---|---|---|
| 1 | Fairness base (quem cantou menos vezes primeiro; empate por ordem de chegada) | — | `ordenarFila()` |
| 2 | Anti-sequência (não deixa a mesma pessoa consecutiva, nem contra quem acabou de sair do palco) | `LIMITE_TROCA_ANTI_SEQUENCIA = 1` | `desfazerSequenciasConsecutivas()` + `ultimoCantorKey` |
| 3 | Teto de créditos por dispositivo | `LIMITE_PEDIDOS_ATIVOS_POR_DEVICE = 4`, `MINUTOS_RECARGA_CREDITO = 50` | `podeAdicionarPedido()` |
| 4 | Bypass de fila curta (ignora o teto de créditos se tiver pouca gente esperando) | `LIMIAR_FILA_CURTA = 3` | `podeAdicionarPedido()` |
| 5 | Ausência (some da ordenação ativa, vai pro fim, prazo pra voltar) | `MINUTOS_MAX_AUSENTE = 60` | `acaoMarcarAusente/acaoNaoApareceu/acaoVoltouAusencia/verificarTimeoutAusentes` |
| 6 | "Não apareceu" desfaz o incremento de `vezesCantadas` da chamada | — | `acaoNaoApareceu()` |

## Ordem de aplicação (precedência)

1. `fila.sort()` por `vezesCantadas` e, em empate, por `timestampFila || timestamp`; ausentes sempre por último
2. `desfazerSequenciasConsecutivas()` (regra 2) mexe na posição 0 e nos pares consecutivos
3. `podeAdicionarPedido()` (regras 3+4) só decide se um pedido NOVO entra — não reordena o que já está na fila
4. Ausência (regra 5) tira o pedido da partição ativa até `acaoVoltouAusencia`, ajustando `timestampFila` pra compensar o tempo fora
5. `acaoNaoApareceu()` (regra 6) desfaz `vezesCantadas` e reinsere como ausente

## Proteções verificadas

`podeAdicionarPedido()` já exclui pedidos com `ausenteDesde` ao contar as outras
pessoas na fila para o bypass de fila curta. Assim, quem está ausente não bloqueia
indevidamente o envio de um novo pedido quando quase ninguém está esperando.

## Combinações de risco — ainda sem teste de interação

Ordenado por probabilidade de acontecer numa noite normal:

1. **"Não apareceu" + anti-sequência**: confirmado que `ultimoCantorKey` continua apontando pra essa pessoa depois do "não apareceu" (não é resetado) — isso é intencional e correto (evita chamá-la nervosamente de novo), mas não tem teste explícito confirmando esse comportamento. Vale um teste que documente a intenção.
2. **Ausência expirando (`MINUTOS_MAX_AUSENTE`) sem painel do DJ aberto**: `verificarTimeoutAusentes()` só roda `if (isAdminAuthenticated())` — se o DJ fechar a aba admin, esse timeout nunca dispara em lugar nenhum. Não é bug, é dependência operacional não documentada: alguém precisa manter a aba do DJ aberta a noite toda pra essa rede de segurança funcionar.
3. ~~**Dois pedidos "não apareceu" seguidos da mesma pessoa**~~ — **INVESTIGADO.** Em um só cliente (o único cenário que `test_karaoke.py` consegue testar, ver seu próprio docstring), a suspeita é falsa: só existe uma `apresentacaoAtual` por vez, e cada incremento/decremento de `contagemCantores` ressincroniza todos os pedidos daquela pessoa ainda na fila — ver `test_suspeita_nao_apareceu_duas_vezes_seguidas_mantem_contagem_consistente`. O bug REAL só aparecia com **múltiplas abas/dispositivos de admin simultâneos contra o Firebase de verdade**: `acaoProximo`/`acaoNaoApareceu` (e as outras ações do admin) liam `fila`/`contagemCantores`/`apresentacaoAtual` da cópia LOCAL e gravavam tudo de uma vez com `salvarNoFirebase()` (`.update()` sem transação) — a última escrita a chegar no servidor vencia e apagava silenciosamente o que a outra aba tinha acabado de mudar, não só em `contagemCantores` mas em `fila`/`apresentacaoAtual` também. **CORRIGIDO**: cada ação do admin agora grava seu path (`fila`, `contagem`, `apresentacaoAtual`, `dispositivosBloqueados`, `manualFechada`) via `db.ref(...).transaction()` (mesmo padrão já usado em `cancelarMeuPedido`/`adicionarPedido`), calculando o próximo valor a partir do dado ATUAL do servidor, não da cópia local. `acaoProximo`/`acaoNaoApareceu` encadeiam 3 transações (apresentacaoAtual → contagem → fila) nessa ordem específica pra que a reivindicação de `apresentacaoAtual` sirva de mutex real entre abas. Esse caminho (Firebase de verdade) continua fora do alcance da suíte automatizada — só o modo local é coberto por teste, igual já era o caso pra `cancelarMeuPedido`. `handleResetNoiteSubmit` continua usando a gravação em bloco de propósito (resetar a noite é pra sobrescrever tudo mesmo); o array `historico` (diferente de `historicoPermanente`, que já usa `push()`) ainda é sobrescrito inteiro em `acaoFinalizarApresentacao` e pode perder uma entrada em caso de duas finalizações quase simultâneas em abas diferentes — risco pré-existente, fora do escopo deste fix.
4. **Fura-fila PIX (sandbox) + qualquer uma das regras acima**: o sandbox tem prioridade absoluta pro fura-fila — nenhum teste hoje combina isso com ausência ou anti-sequência. Só relevante quando o PIX for pra produção.

## Próximo passo sugerido

Não é reescrever nada. É escrever 4-6 testes novos em `test_karaoke.py` que montam
cenários combinando 2-3 regras ao mesmo tempo (não uma de cada vez), começando
pelo item 1 da lista acima — são os que têm chance real de já estar
acontecendo na Città sem ninguém ter reportado ainda.
