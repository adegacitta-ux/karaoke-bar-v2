# Mapa das regras de ordenação da fila — Cantokê

Levantamento feito lendo o `index.html` de produção (`karaoke-bar-v2`) em 11/09/2026.
Objetivo: parar de descobrir problemas de combinação um por semana, ao testar cada
regra nova isolada. Nenhuma mudança de código aqui — só mapeamento + priorização
de testes de interação.

## As 7 regras que mexem na fila hoje

| # | Regra | Constante | Onde vive |
|---|---|---|---|
| 1 | Fairness base (quem cantou menos vezes primeiro, com desconto por tempo de espera) | `MINUTOS_PARA_PERDOAR_UMA_VEZ_CANTADA = 25` | `calcularPrioridadeEfetiva()` |
| 2 | Espera máxima (fura tudo depois de X min) | `MINUTOS_ESPERA_MAXIMA = 40` | `calcularPrioridadeEfetiva()` |
| 3 | Anti-sequência (não deixa a mesma pessoa consecutiva, nem contra quem acabou de sair do palco) | `LIMITE_TROCA_ANTI_SEQUENCIA = 1` | `desfazerSequenciasConsecutivas()` + `ultimoCantorKey` |
| 4 | Teto de créditos por dispositivo | `LIMITE_PEDIDOS_ATIVOS_POR_DEVICE = 4`, `MINUTOS_RECARGA_CREDITO = 50` | `podeAdicionarPedido()` |
| 5 | Bypass de fila curta (ignora o teto de créditos se tiver pouca gente esperando) | `LIMIAR_FILA_CURTA = 3` | `podeAdicionarPedido()` |
| 6 | Ausência (some da ordenação ativa, vai pro fim, prazo pra voltar) | `MINUTOS_MAX_AUSENTE = 60` | `acaoMarcarAusente/acaoNaoApareceu/acaoVoltouAusencia/verificarTimeoutAusentes` |
| 7 | "Não apareceu" desfaz o incremento de `vezesCantadas` da chamada | — | `acaoNaoApareceu()` |

## Ordem de aplicação (precedência)

1. `fila.sort()` por `calcularPrioridadeEfetiva` (regras 1+2), ausentes sempre por último
2. `desfazerSequenciasConsecutivas()` (regra 3) mexe na posição 0 e nos pares consecutivos
3. `podeAdicionarPedido()` (regras 4+5) só decide se um pedido NOVO entra — não reordena o que já está na fila
4. Ausência (regra 6) tira o pedido da partição ativa até `acaoVoltouAusencia`, ajustando `timestampFila` pra compensar o tempo fora
5. `acaoNaoApareceu()` (regra 7) desfaz `vezesCantadas` e reinsere como ausente

## 🔴 Bug real encontrado agora, lendo o código (ainda não reportado por ninguém)

**`outrasPessoasNaFila` (linha ~2683, dentro de `podeAdicionarPedido`) conta pedidos
ausentes como "gente esperando".**

```js
const outrasPessoasNaFila = lista.filter(p => p.deviceId !== deviceId).length;
```

Esse filtro não exclui `p.ausenteDesde`. Cenário: 3 pessoas marcadas como ausentes
(saíram pra fumar, foram no banheiro) ficam contando pro `LIMIAR_FILA_CURTA = 3` —
a fila "parece" ter gente suficiente esperando e o bypass de crédito não libera,
mesmo quena prática só tenha 1 pessoa realmente esperando a vez. Efeito: alguém
pode ficar bloqueado de pedir mais música por causa de gente que nem está lá.

**Sugestão de fix (pra quando for mexer nisso):** `lista.filter(p => p.deviceId !== deviceId && !p.ausenteDesde).length`.

## Combinações de risco — ainda sem teste de interação

Ordenado por probabilidade de acontecer numa noite normal:

1. **Ausente + teto de crédito** (bug acima) — pessoa ausente bloqueando bypass de fila curta pra outra pessoa.
2. **"Não apareceu" + anti-sequência**: confirmado que `ultimoCantorKey` continua apontando pra essa pessoa depois do "não apareceu" (não é resetado) — isso é intencional e correto (evita chamá-la nervosamente de novo), mas não tem teste explícito confirmando esse comportamento. Vale um teste que documente a intenção.
3. **Espera máxima + anti-sequência**: alguém que furou tudo por `MINUTOS_ESPERA_MAXIMA` (prioridade `-Infinity`) e é a mesma pessoa que `ultimoCantorKey` — o desconto de anti-sequência (`LIMITE_TROCA_ANTI_SEQUENCIA = 1`) provavelmente não segura, já que a diferença de prioridade vira `-Infinity`. Ou seja, furar por espera máxima pode ANULAR a proteção anti-sequência. Não testado.
4. **Ausência expirando (`MINUTOS_MAX_AUSENTE`) sem painel do DJ aberto**: `verificarTimeoutAusentes()` só roda `if (isAdminAuthenticated())` — se o DJ fechar a aba admin, esse timeout nunca dispara em lugar nenhum. Não é bug, é dependência operacional não documentada: alguém precisa manter a aba do DJ aberta a noite toda pra essa rede de segurança funcionar.
5. **Dois pedidos "não apareceu" seguidos da mesma pessoa**: `contagemCantores[key]` sendo decrementado duas vezes — confirmar que não fica negativo nem desalinha `vezesCantadas` de outros pedidos dela na fila.
6. **Fura-fila PIX (sandbox) + qualquer uma das regras acima**: o sandbox tem prioridade absoluta pro fura-fila — nenhum teste hoje combina isso com ausência ou anti-sequência. Só relevante quando o PIX for pra produção.

## Próximo passo sugerido

Não é reescrever nada. É escrever 4-6 testes novos em `test_karaoke.py` que montam
cenários combinando 2-3 regras ao mesmo tempo (não uma de cada vez), começando
pelos itens 1 e 3 da lista acima — são os que têm chance real de já estar
acontecendo na Città sem ninguém ter reportado ainda.
