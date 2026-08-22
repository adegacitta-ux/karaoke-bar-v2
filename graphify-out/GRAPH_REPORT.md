# Graph Report - karaoke-bar-v2  (2026-08-22)

## Corpus Check
- Corpus is ~44,910 words - fits in a single context window. You may not need a graph.

## Summary
- 175 nodes · 351 edges · 26 communities (14 shown, 12 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 10 edges (avg confidence: 0.82)
- Token cost: 199,616 input · 0 output

## Community Hubs (Navigation)
- Paginas do App e Config Hardcoded
- Skill Graphify e Historico Permanente
- Testes: Admin e Conectividade (tests/)
- Estado da Fila e Sync Firebase
- Testes: Prioridade da Fila (raiz)
- Testes: Prioridade da Fila (tests/)
- Testes: Catalogo e Display (tests/)
- Testes: Relatorios e Votacao (tests/)
- Testes: Avisos de Conexao (raiz)
- Testes: Admin e Avaliacoes (raiz)
- Estrutura Multi-Tenant (barId)
- Testes: Contraste Modo Escuro
- Testes: Servidor HTTP e YouTube (raiz)
- Testes: Servidor HTTP (tests/)
- Testes: Pedidos Simultaneos (raiz)
- Testes: Historico Paginado (raiz)
- Testes: Persistencia Modo Escuro (raiz)
- Testes: Protecao XSS (raiz)
- Testes: Historico Completo (raiz)
- Testes: Validacao de Formulario (raiz)
- Testes: Acessibilidade (raiz)
- Testes: Historico Completo (tests/)
- Testes: Validacao de Formulario (tests/)
- Testes: Limite de 1 Ano no Historico (tests/)
- Toggle de Modo Escuro
- Verificacao de Posicao na Fila

## God Nodes (most connected - your core abstractions)
1. `main()` - 31 edges
2. `registrar()` - 30 edges
3. `nova_pagina()` - 28 edges
4. `nova_pagina()` - 23 edges
5. `main()` - 23 edges
6. `registrar()` - 22 edges
7. `Graphify Skill (/graphify)` - 13 edges
8. `Karaoke Manager App (index.html)` - 12 edges
9. `Refactoring Plan Overview` - 10 edges
10. `preencher_pedido()` - 7 edges

## Surprising Connections (you probably didn't know these)
- `Legacy Karaoke Manager (index (5).html)` --semantically_similar_to--> `Karaoke Manager App (index.html)`  [INFERRED] [semantically similar]
  index (5).html → index.html
- `Work Memory Self-Improving Reflect Loop` --semantically_similar_to--> `historicoPermanente (Firebase RTDB path)`  [INFERRED] [semantically similar]
  .claude/skills/graphify/references/query.md → index.html
- `switchTab() (legacy)` --semantically_similar_to--> `switchTab()`  [INFERRED] [semantically similar]
  index (5).html → index.html
- `adicionarPedido() (legacy)` --semantically_similar_to--> `adicionarPedido()`  [INFERRED] [semantically similar]
  index (5).html → index.html
- `Hardcoded ADMIN_EMAIL (legacy)` --semantically_similar_to--> `Hardcoded firebaseConfig`  [INFERRED] [semantically similar]
  index (5).html → index.html

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Multi-Tenant Bar Coordination via Firebase RTDB** — index_html_karaoke_manager_page, catalogo_html_catalog_page, display_html_display_page, index_html_bares_barid_structure [EXTRACTED 1.00]
- **Karaoke Request-to-History Lifecycle** — index_html_adicionarpedido, index_html_atualizarfilaatomica, index_html_acaoproximo, index_html_acaofinalizarapresentacao, index_html_registrarnohistoricopermanente [INFERRED 0.85]
- **Graphify Build to Update to Query Pipeline** — _claude_skills_graphify_skill_graphify, _claude_skills_graphify_references_extraction_spec_extraction_subagent_prompt, _claude_skills_graphify_references_update_incremental_update, _claude_skills_graphify_references_query_query_path_explain [EXTRACTED 1.00]

## Communities (26 total, 12 thin omitted)

### Community 0 - "Paginas do App e Config Hardcoded"
Cohesion: 0.09
Nodes (25): Song Catalog Page (catalogo.html), CATALOGO_MUSICAS fixed song list, escolherMusica(), Big-Screen Display (display.html), QR Code linking to index.html, Hardcoded ADMIN_EMAIL (legacy), Legacy Karaoke Manager (index (5).html), switchTab() (legacy) (+17 more)

### Community 1 - "Skill Graphify e Historico Permanente"
Cohesion: 0.12
Nodes (17): Graphify Skill Pointer (.claude/CLAUDE.md), /graphify add <url>, --watch (auto-rebuild watcher), Export flags (wiki/neo4j/falkordb/svg/graphml/mcp/benchmark), Extraction Subagent Prompt Spec, GitHub Clone & Cross-Repo Merge, Native CLAUDE.md Integration, Post-Commit Auto-Rebuild Hook (+9 more)

### Community 2 - "Testes: Admin e Conectividade (tests/)"
Cohesion: 0.17
Nodes (18): main(), nova_pagina(), Página do cliente mostra só as últimas 12 músicas cantadas por padrão, com…, O banner de 'sem conexão' existe, começa escondido, e pode ser mostrado (a…, O botão de modo escuro alterna a classe no <body>, muda o ícone (lua/sol), e a…, Nome, música e mesa digitados pelo cliente entram em vários lugares via…, Em vez de um listener só no nó inteiro do bar (que reenviava fila + histórico +…, O painel 'Relatórios da Noite' calcula total de músicas, pessoas diferentes,… (+10 more)

### Community 3 - "Estado da Fila e Sync Firebase"
Cohesion: 0.18
Nodes (9): atualizarDisplay() / atualizarDisplayWithData(), adicionarPedido() (legacy), adicionarPedido(), apresentacaoAtual (Firebase RTDB path), atualizarFilaAtomica() (Firebase transaction), Global state variables (fila, historico, apresentacaoAtual, contagemCantores), fila (Firebase RTDB path: bares/$barId/karaoke/fila), sincronizarComFirebase() (+1 more)

### Community 4 - "Testes: Prioridade da Fila (raiz)"
Cohesion: 0.27
Nodes (11): main(), preencher_pedido(), Este é o teste mais importante: replica o bug real de produção onde o Firebase…, Regra pedida após teste com público real: quem já cantou não pode ficar preso…, Cartão 'Seus Pedidos': mostra a posição na fila e permite cancelar (com…, test_espera_longa_faz_pessoa_furar_a_fila(), test_isolamento_entre_bares(), test_meus_pedidos_posicao_e_cancelamento() (+3 more)

### Community 5 - "Testes: Prioridade da Fila (tests/)"
Cohesion: 0.29
Nodes (10): preencher_pedido(), Este é o teste mais importante: replica o bug real de produção onde o Firebase…, Regra pedida após teste com público real: quem já cantou não pode ficar preso…, Cartão 'Seus Pedidos': mostra a posição na fila e permite cancelar (com…, test_espera_longa_faz_pessoa_furar_a_fila(), test_isolamento_entre_bares(), test_meus_pedidos_posicao_e_cancelamento(), test_pessoas_diferentes_mesas_diferentes_nao_se_confundem() (+2 more)

### Community 6 - "Testes: Catalogo e Display (tests/)"
Cohesion: 0.20
Nodes (10): aguardar_tailwind(), O aviso sobre a limitação de notificação no iPhone só aparece pra quem está…, O catálogo agora é uma página separada (catalogo.html), em formato de lista…, Clicar numa música no catálogo leva de volta pra tela de pedidos já com o…, Espera o Tailwind CDN carregar e gerar as classes utilitárias DE VERDADE (ele…, O indicador '🔥 Conectado ao Firebase' do telão não pode ficar fixo — precisa…, test_aviso_iphone_aparece_so_no_iphone(), test_catalogo_escolher_musica_preenche_index() (+2 more)

### Community 7 - "Testes: Relatorios e Votacao (tests/)"
Cohesion: 0.20
Nodes (10): Regra crítica: reproduz o bug relatado de nomes "sumindo e reaparecendo". Causa…, Labels associados aos campos (via for/id), ícones decorativos marcados como…, O gráfico 'Pedidos por horário' agrupa os pedidos pela hora do timestamp e…, Se um voto não conseguir salvar no Firebase, a pessoa precisa saber — senão ela…, registrar(), test_acessibilidade_basica(), test_bar_valido_carrega_sem_erros(), test_dois_pedidos_simultaneos_nao_se_perdem() (+2 more)

### Community 8 - "Testes: Avisos de Conexao (raiz)"
Cohesion: 0.33
Nodes (7): aguardar_tailwind(), nova_pagina(), O aviso sobre a limitação de notificação no iPhone só aparece pra quem está…, O banner de 'sem conexão' existe, começa escondido, e pode ser mostrado (a…, Espera o Tailwind CDN carregar e gerar as classes utilitárias DE VERDADE (ele…, test_aviso_de_conexao_perdida_existe(), test_aviso_iphone_aparece_so_no_iphone()

### Community 9 - "Testes: Admin e Avaliacoes (raiz)"
Cohesion: 0.29
Nodes (7): Em vez de um listener só no nó inteiro do bar (que reenviava fila + histórico +…, registrar(), test_admin_exige_login(), test_bar_valido_carrega_sem_erros(), test_listeners_separados_por_pedaco(), test_media_de_avaliacoes(), test_sem_bar_mostra_erro()

### Community 10 - "Estrutura Multi-Tenant (barId)"
Cohesion: 0.40
Nodes (6): BAR_ID (catalogo.html), BAR_ID (display.html), 'karaoke' fixed Firebase path (single-tenant, legacy), bares/$barId multi-tenant structure, BAR_ID / obterBarId(), caminhoBar() Firebase path builder

### Community 11 - "Testes: Contraste Modo Escuro"
Cohesion: 0.33
Nodes (6): _contraste(), Calcula a taxa de contraste entre duas cores hex, seguindo a fórmula do WCAG.…, Converte 'rgb(134, 239, 172)' pra '#86efac'., Vários textos coloridos (verde, amarelo, laranja, vermelho, azul) tinham o…, _rgb_para_hex(), test_contraste_de_cores_no_modo_escuro()

### Community 12 - "Testes: Servidor HTTP e YouTube (raiz)"
Cohesion: 0.50
Nodes (4): _porta_livre(), Sobe um servidor HTTP local de verdade (python -m http.server) servindo a pasta…, servidor_http(), test_youtube_preenche_musica_e_libera_artista()

### Community 13 - "Testes: Servidor HTTP (tests/)"
Cohesion: 0.67
Nodes (3): _porta_livre(), Sobe um servidor HTTP local de verdade (python -m http.server) servindo a pasta…, servidor_http()

## Knowledge Gaps
- **23 isolated node(s):** `Graphify Skill Pointer (.claude/CLAUDE.md)`, `/graphify add <url>`, `--watch (auto-rebuild watcher)`, `Export flags (wiki/neo4j/falkordb/svg/graphml/mcp/benchmark)`, `Extraction Subagent Prompt Spec` (+18 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Global state variables (fila, historico, apresentacaoAtual, contagemCantores)` connect `Estado da Fila e Sync Firebase` to `Skill Graphify e Historico Permanente`?**
  _High betweenness centrality (0.070) - this node is a cross-community bridge._
- **Why does `Refactoring Plan Overview` connect `Paginas do App e Config Hardcoded` to `Estado da Fila e Sync Firebase`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **Why does `Centralized State Management` connect `Estado da Fila e Sync Firebase` to `Paginas do App e Config Hardcoded`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **What connects `Graphify Skill Pointer (.claude/CLAUDE.md)`, `/graphify add <url>`, `--watch (auto-rebuild watcher)` to the rest of the system?**
  _23 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Paginas do App e Config Hardcoded` be split into smaller, more focused modules?**
  _Cohesion score 0.08831908831908832 - nodes in this community are weakly interconnected._
- **Should `Skill Graphify e Historico Permanente` be split into smaller, more focused modules?**
  _Cohesion score 0.11695906432748537 - nodes in this community are weakly interconnected._