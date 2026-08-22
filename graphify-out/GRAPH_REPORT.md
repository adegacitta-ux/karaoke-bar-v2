# Graph Report - karaoke-bar-v2  (2026-08-22)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 108 nodes · 278 edges · 25 communities (11 shown, 14 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `6c509de1`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24

## God Nodes (most connected - your core abstractions)
1. `main()` - 31 edges
2. `registrar()` - 30 edges
3. `nova_pagina()` - 28 edges
4. `main()` - 23 edges
5. `nova_pagina()` - 23 edges
6. `registrar()` - 22 edges
7. `preencher_pedido()` - 7 edges
8. `preencher_pedido()` - 7 edges
9. `aguardar_tailwind()` - 7 edges
10. `test_contraste_de_cores_no_modo_escuro()` - 7 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `servidor_http()`  [EXTRACTED]
  test_karaoke.py → test_karaoke.py  _Bridges community 0 → community 9_
- `main()` --calls--> `test_acessibilidade_basica()`  [EXTRACTED]
  test_karaoke.py → test_karaoke.py  _Bridges community 0 → community 17_
- `main()` --calls--> `test_admin_exige_login()`  [EXTRACTED]
  test_karaoke.py → test_karaoke.py  _Bridges community 0 → community 5_
- `main()` --calls--> `test_aviso_de_conexao_perdida_existe()`  [EXTRACTED]
  test_karaoke.py → test_karaoke.py  _Bridges community 0 → community 4_
- `main()` --calls--> `test_dois_pedidos_simultaneos_nao_se_perdem()`  [EXTRACTED]
  test_karaoke.py → test_karaoke.py  _Bridges community 0 → community 11_

## Import Cycles
- None detected.

## Communities (25 total, 14 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.27
Nodes (11): main(), preencher_pedido(), Este é o teste mais importante: replica o bug real de produção onde o Firebase…, Regra pedida após teste com público real: quem já cantou não pode ficar preso…, Cartão 'Seus Pedidos': mostra a posição na fila e permite cancelar (com…, test_espera_longa_faz_pessoa_furar_a_fila(), test_isolamento_entre_bares(), test_meus_pedidos_posicao_e_cancelamento() (+3 more)

### Community 1 - "Community 1"
Cohesion: 0.29
Nodes (10): preencher_pedido(), Este é o teste mais importante: replica o bug real de produção onde o Firebase…, Regra pedida após teste com público real: quem já cantou não pode ficar preso…, Cartão 'Seus Pedidos': mostra a posição na fila e permite cancelar (com…, test_espera_longa_faz_pessoa_furar_a_fila(), test_isolamento_entre_bares(), test_meus_pedidos_posicao_e_cancelamento(), test_pessoas_diferentes_mesas_diferentes_nao_se_confundem() (+2 more)

### Community 2 - "Community 2"
Cohesion: 0.25
Nodes (8): aguardar_tailwind(), O catálogo agora é uma página separada (catalogo.html), em formato de lista…, Clicar numa música no catálogo leva de volta pra tela de pedidos já com o…, Espera o Tailwind CDN carregar e gerar as classes utilitárias DE VERDADE (ele…, O indicador '🔥 Conectado ao Firebase' do telão não pode ficar fixo — precisa…, test_catalogo_escolher_musica_preenche_index(), test_catalogo_pagina_separada_lista_por_letra(), test_display_mostra_status_de_conexao_honesto()

### Community 3 - "Community 3"
Cohesion: 0.25
Nodes (8): O aviso sobre a limitação de notificação no iPhone só aparece pra quem está…, O gráfico 'Pedidos por horário' agrupa os pedidos pela hora do timestamp e…, Se um voto não conseguir salvar no Firebase, a pessoa precisa saber — senão ela…, registrar(), test_aviso_iphone_aparece_so_no_iphone(), test_bar_valido_carrega_sem_erros(), test_horario_de_pico(), test_voto_que_falha_avisa_a_pessoa()

### Community 4 - "Community 4"
Cohesion: 0.33
Nodes (7): aguardar_tailwind(), nova_pagina(), O aviso sobre a limitação de notificação no iPhone só aparece pra quem está…, O banner de 'sem conexão' existe, começa escondido, e pode ser mostrado (a…, Espera o Tailwind CDN carregar e gerar as classes utilitárias DE VERDADE (ele…, test_aviso_de_conexao_perdida_existe(), test_aviso_iphone_aparece_so_no_iphone()

### Community 5 - "Community 5"
Cohesion: 0.29
Nodes (7): Em vez de um listener só no nó inteiro do bar (que reenviava fila + histórico +…, registrar(), test_admin_exige_login(), test_bar_valido_carrega_sem_erros(), test_listeners_separados_por_pedaco(), test_media_de_avaliacoes(), test_sem_bar_mostra_erro()

### Community 6 - "Community 6"
Cohesion: 0.29
Nodes (7): main(), Nome, música e mesa digitados pelo cliente entram em vários lugares via…, O histórico completo só é baixado quando alguém realmente pede pra ver tudo…, test_admin_exige_login(), test_historico_completo_sob_demanda(), test_protecao_contra_xss(), test_youtube_preenche_musica_e_libera_artista()

### Community 7 - "Community 7"
Cohesion: 0.29
Nodes (7): nova_pagina(), O banner de 'sem conexão' existe, começa escondido, e pode ser mostrado (a…, O botão de modo escuro alterna a classe no <body>, muda o ícone (lua/sol), e a…, test_aviso_de_conexao_perdida_existe(), test_media_de_avaliacoes(), test_modo_escuro_alterna_e_persiste(), test_sem_bar_mostra_erro()

### Community 8 - "Community 8"
Cohesion: 0.33
Nodes (6): _contraste(), Calcula a taxa de contraste entre duas cores hex, seguindo a fórmula do WCAG.…, Converte 'rgb(134, 239, 172)' pra '#86efac'., Vários textos coloridos (verde, amarelo, laranja, vermelho, azul) tinham o…, _rgb_para_hex(), test_contraste_de_cores_no_modo_escuro()

### Community 9 - "Community 9"
Cohesion: 0.50
Nodes (4): _porta_livre(), Sobe um servidor HTTP local de verdade (python -m http.server) servindo a pasta…, servidor_http(), test_youtube_preenche_musica_e_libera_artista()

### Community 10 - "Community 10"
Cohesion: 0.67
Nodes (3): _porta_livre(), Sobe um servidor HTTP local de verdade (python -m http.server) servindo a pasta…, servidor_http()

## Knowledge Gaps
- **14 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `main()` connect `Community 6` to `Community 1`, `Community 2`, `Community 3`, `Community 7`, `Community 8`, `Community 10`, `Community 18`, `Community 19`, `Community 20`, `Community 21`, `Community 22`, `Community 23`, `Community 24`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Why does `registrar()` connect `Community 3` to `Community 1`, `Community 2`, `Community 6`, `Community 7`, `Community 8`, `Community 18`, `Community 19`, `Community 20`, `Community 21`, `Community 22`, `Community 23`, `Community 24`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Why does `nova_pagina()` connect `Community 7` to `Community 1`, `Community 2`, `Community 3`, `Community 6`, `Community 8`, `Community 18`, `Community 19`, `Community 20`, `Community 21`, `Community 22`, `Community 23`, `Community 24`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._