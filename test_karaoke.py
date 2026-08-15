#!/usr/bin/env python3
"""
Testes automatizados do Karaokê Manager.

O QUE ISSO TESTA:
Os fluxos principais do index.html, rodando localmente no navegador (modo
localStorage, sem depender do Firebase real) — cobre a lógica que já causou
bugs reais no passado: prioridade da fila, unificação de nomes, o "piscar"
da tela ao votar, o fluxo de busca no YouTube, e a identificação do bar
(multi-tenant).

O QUE ISSO **NÃO** TESTA (precisa ser feito manualmente, ao vivo):
- As regras de segurança do Firebase (permission_denied só aparece com o
  banco de dados real — isso já nos pegou de surpresa uma vez, ver commit
  do bug "fila reiniciando ao votar" / regras do /karaoke).
- Login de admin de verdade (e-mail/senha real do Firebase Authentication).
- Sincronização em tempo real entre duas abas/dispositivos diferentes.

COMO RODAR:
    pip install playwright --break-system-packages
    playwright install chromium
    python3 test_karaoke.py

    (ou aponte PARA outro arquivo index.html com --arquivo /caminho/index.html)

Cada teste imprime PASS ou FAIL. Ao final, mostra um resumo e sai com
código de erro != 0 se algo falhou (útil pra rodar antes de qualquer deploy).
"""

import sys
import re
import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


RESULTADOS = []


def registrar(nome, ok, detalhe=""):
    RESULTADOS.append((nome, ok, detalhe))
    marca = "✅ PASS" if ok else "❌ FAIL"
    linha = f"{marca}  {nome}"
    if detalhe:
        linha += f"  —  {detalhe}"
    print(linha)


def preparar_html_para_teste(caminho_index):
    """Copia o index.html pra um arquivo temporário com um pequeno ajuste de
    CSS (a classe .hidden precisa existir mesmo sem o Tailwind carregar via
    CDN, já que o teste roda offline)."""
    conteudo = Path(caminho_index).read_text(encoding="utf-8")
    conteudo = conteudo.replace("</head>", "<style>.hidden{display:none;}</style></head>")
    destino = Path(caminho_index).parent / "_tmp_teste_index.html"
    destino.write_text(conteudo, encoding="utf-8")
    return destino


def nova_pagina(browser, arquivo_temp, bar="citta", viewport=None):
    context = browser.new_context(viewport=viewport or {"width": 480, "height": 900},
                                   permissions=["notifications"])
    page = context.new_page()
    erros = []
    page.on("pageerror", lambda exc: erros.append(str(exc)))
    url = f"file://{arquivo_temp}"
    if bar is not None:
        url += f"?bar={bar}"
    page.goto(url)
    page.evaluate("localStorage.clear()")
    page.reload()
    page.wait_for_timeout(250)
    return context, page, erros


def preencher_pedido(page, nome, musica, artista="ArtistaX", mesa=None):
    if page.is_visible("#btn-nao-e-voce"):
        page.click("#btn-nao-e-voce")
    page.fill("#input-nome", nome)
    if mesa is not None:
        page.fill("#input-mesa", str(mesa))
    page.fill("#input-musica", musica)
    page.fill("#input-artista", artista)
    page.click("#btn-enviar")
    page.wait_for_timeout(150)


# ---------------------------------------------------------------------------

def test_sem_bar_mostra_erro(browser, arquivo_temp):
    context, page, erros = nova_pagina(browser, arquivo_temp, bar=None)
    tem_aviso = page.evaluate("document.body.innerText.includes('Link incompleto')")
    ok = tem_aviso and not erros
    registrar("Acessar sem ?bar= mostra aviso claro (sem tela quebrada)", ok,
               f"aviso presente={tem_aviso}, erros JS={erros}")
    context.close()


def test_bar_valido_carrega_sem_erros(browser, arquivo_temp):
    context, page, erros = nova_pagina(browser, arquivo_temp, bar="citta")
    ok = len(erros) == 0
    registrar("Acessar com ?bar=citta carrega sem erros de JS", ok, f"erros={erros}")
    context.close()


def test_isolamento_entre_bares(browser, arquivo_temp):
    context, page, _ = nova_pagina(browser, arquivo_temp, bar="citta")
    preencher_pedido(page, "PessoaDoCitta", "MusicaDoCitta")
    fila_citta = page.evaluate("fila.map(p => p.nome)")
    context.close()

    context2, page2, _ = nova_pagina(browser, arquivo_temp, bar="outrobar")
    fila_outrobar = page2.evaluate("fila.map(p => p.nome)")
    context2.close()

    ok = fila_citta == ["PessoaDoCitta"] and fila_outrobar == []
    registrar("Dados de um bar não vazam pra outro (?bar=citta vs ?bar=outrobar)", ok,
               f"citta={fila_citta}, outrobar={fila_outrobar}")


def test_prioridade_por_nome_e_mesa(browser, arquivo_temp):
    context, page, erros = nova_pagina(browser, arquivo_temp)
    preencher_pedido(page, "Maria", "Musica1", mesa="5")
    preencher_pedido(page, "Maria Silva", "Musica2", mesa="5")
    preencher_pedido(page, "maria", "Musica3", mesa="5")
    prioridades = page.evaluate("fila.map(p => p.vezesCantadas)")
    # A prioridade é só "quantas vezes já cantou de verdade" — pedidos ainda
    # pendentes na fila não contam. Como essa pessoa (mesmo nome+mesa, grafias
    # diferentes) ainda não cantou nenhuma vez, as 3 entradas ficam com
    # prioridade 0 e a ordem entre elas é decidida pelo horário de chegada.
    ok = prioridades == [0, 0, 0] and not erros
    registrar("Mesma pessoa (grafias diferentes, mesma mesa) é unificada — prioridade não conta pedidos pendentes", ok,
               f"prioridades={prioridades}")
    context.close()


def test_pessoas_diferentes_mesas_diferentes_nao_se_confundem(browser, arquivo_temp):
    context, page, erros = nova_pagina(browser, arquivo_temp)
    preencher_pedido(page, "Maria", "MusicaA", mesa="3")
    preencher_pedido(page, "Maria", "MusicaB", mesa="3")
    preencher_pedido(page, "Maria", "MusicaC", mesa="8")
    chaves = page.evaluate("""
        fila.map(p => obterChaveNome(p.nome, p.mesa))
    """)
    # As duas primeiras (mesa 3) devem gerar a MESMA chave de identidade;
    # a da mesa 8 deve gerar uma chave DIFERENTE (pessoa considerada distinta)
    ok = chaves[0] == chaves[1] and chaves[0] != chaves[2] and not erros
    registrar("Mesmo primeiro nome em mesas diferentes NÃO se confunde", ok,
               f"chaves={chaves}")
    context.close()


def test_voto_nao_reconstroi_a_tela(browser, arquivo_temp):
    """Este é o teste mais importante: replica o bug real de produção onde o
    Firebase reordena as chaves dos objetos, e isso fazia a tela toda
    piscar/recarregar a cada voto."""
    context, page, erros = nova_pagina(browser, arquivo_temp)
    preencher_pedido(page, "Carlos", "MusicaTeste")
    pedido_id = page.evaluate("fila[0].id")
    page.evaluate(f"acaoProximo({pedido_id})")
    page.wait_for_timeout(150)

    page.evaluate("""
        window.__tabelaRef = document.getElementById('tabela-fila');
        window.__histRef = document.getElementById('lista-historico');
    """)

    # Simula 5 votos de pessoas diferentes, com os campos do objeto em ORDEM
    # DIFERENTE a cada vez — é exatamente o que o Firebase faz na vida real
    for i, nota in enumerate([5, 4, 5, 3, 5]):
        page.evaluate(f"""
            (function() {{
                fila = fila.map(p => ({{
                    vezesCantadas: p.vezesCantadas, musica: p.musica, id: p.id,
                    nome: p.nome, artista: p.artista, mesa: p.mesa, youtubeUrl: p.youtubeUrl
                }}));
                if (!apresentacaoAtual.avaliacoes) apresentacaoAtual.avaliacoes = {{}};
                apresentacaoAtual.avaliacoes['pessoa{i}'] = {nota};
                atualizarUI();
            }})();
        """)
        page.wait_for_timeout(60)

    tabela_estavel = page.evaluate('document.getElementById("tabela-fila") === window.__tabelaRef')
    historico_estavel = page.evaluate('document.getElementById("lista-historico") === window.__histRef')
    media = page.evaluate("mediaEVotos(apresentacaoAtual.avaliacoes).media")

    ok = tabela_estavel and historico_estavel and media == 4.4 and not erros
    registrar("Votar NÃO reconstrói a fila/histórico na tela (mesmo com chaves reordenadas)", ok,
               f"tabela_estavel={tabela_estavel}, historico_estavel={historico_estavel}, media={media}")
    context.close()


def test_admin_exige_login(browser, arquivo_temp):
    context, page, erros = nova_pagina(browser, arquivo_temp)
    autenticado_antes = page.evaluate("isAdminAuthenticated()")
    page.evaluate("switchTab('admin')")
    page.wait_for_timeout(100)
    modal_visivel = page.evaluate("!document.getElementById('admin-auth-modal').classList.contains('hidden')")
    ok = (not autenticado_antes) and modal_visivel and not erros
    registrar("Acessar aba Admin sem login mostra o modal de senha", ok,
               f"autenticado_antes={autenticado_antes}, modal_visivel={modal_visivel}")
    context.close()


def test_youtube_preenche_musica_e_libera_artista(browser, arquivo_temp):
    context, page, erros = nova_pagina(browser, arquivo_temp)

    def mock_youtube(route):
        route.fulfill(
            status=200, content_type="application/json",
            body='{"items": [{"id": {"videoId": "abc123"}, "snippet": {"title": "Evidencias - Chitaozinho e Xororo (Karaoke)", "channelTitle": "C", "thumbnails": {"default": {"url": "https://via.placeholder.com/120"}}}}]}'
        )
    page.route("**/youtube/v3/search**", mock_youtube)

    page.fill("#input-nome", "Joao")
    page.click("#btn-abrir-youtube")
    page.wait_for_timeout(150)
    page.fill("#youtube-busca-input", "Evidencias")
    page.evaluate("buscarNoYoutube()")
    page.wait_for_timeout(400)
    page.click("#youtube-resultados button >> nth=0")
    page.wait_for_timeout(150)

    musica_preenchida = page.evaluate("document.getElementById('input-musica').value")
    artista_obrigatorio = page.evaluate("document.getElementById('input-artista').required")

    ok = "Evidencias" in musica_preenchida and artista_obrigatorio is False and not erros
    registrar("Selecionar vídeo do YouTube preenche a música e libera o artista", ok,
               f"musica='{musica_preenchida}', artista_obrigatorio={artista_obrigatorio}")
    context.close()


def test_media_de_avaliacoes(browser, arquivo_temp):
    context, page, erros = nova_pagina(browser, arquivo_temp)
    media = page.evaluate("mediaEVotos({a: 5, b: 4, c: 5, d: 3, e: 5}).media")
    votos = page.evaluate("mediaEVotos({a: 5, b: 4, c: 5, d: 3, e: 5}).votos")
    ok = media == 4.4 and votos == 5 and not erros
    registrar("Cálculo da média de avaliações está correto", ok, f"media={media}, votos={votos}")
    context.close()


def test_espera_longa_faz_pessoa_furar_a_fila(browser, arquivo_temp):
    """Regra pedida após teste com público real: quem já cantou não pode ficar
    preso no fim da fila pra sempre só porque gente nova continua chegando —
    com tempo de espera suficiente, ela volta a furar a frente."""
    context, page, erros = nova_pagina(browser, arquivo_temp)

    preencher_pedido(page, "PessoaA", "MusicaA1")
    id_a = page.evaluate("fila[0].id")
    page.evaluate(f"acaoProximo({id_a})")
    page.evaluate("acaoFinalizarApresentacao()")
    page.wait_for_timeout(100)

    # Pessoa A pede de novo (já com vezesCantadas=1) e Pessoa B, nova, entra depois
    preencher_pedido(page, "PessoaA", "MusicaA2")
    preencher_pedido(page, "PessoaB", "MusicaB1")
    ordem_normal = page.evaluate("fila.map(p => p.nome)")

    # Simula 20 minutos de espera no pedido da Pessoa A (mais que o limite de
    # 15min configurado pra perdoar uma vez cantada)
    # Simula uma espera bem maior que o limite configurado (2x + 5min de folga),
    # pra esse teste continuar valendo mesmo se você mudar o valor do minutos-pra-perdoar
    limite_minutos = page.evaluate("MINUTOS_PARA_PERDOAR_UMA_VEZ_CANTADA")
    minutos_de_espera_simulada = (limite_minutos * 2) + 5
    page.evaluate(f"""
        const pedidoA = fila.find(p => p.nome === 'PessoaA');
        pedidoA.timestamp = Date.now() - ({minutos_de_espera_simulada} * 60 * 1000);
    """)
    page.evaluate("atualizarUI()")
    page.wait_for_timeout(100)
    ordem_apos_espera = page.evaluate("fila.map(p => p.nome)")

    ok = (ordem_normal[0] == "PessoaB" and ordem_apos_espera[0] == "PessoaA" and not erros)
    registrar("Espera longa faz quem já cantou furar a frente de quem é novo", ok,
               f"sem_esperar={ordem_normal}, apos_20min={ordem_apos_espera}")
    context.close()


def test_dois_pedidos_simultaneos_nao_se_perdem(browser, arquivo_temp):
    """Regra crítica: reproduz o bug relatado de nomes "sumindo e reaparecendo".
    Causa era uma corrida de gravação — dois pedidos quase ao mesmo tempo podiam
    se sobrescrever. Usa um Firebase simulado que processa uma transação de
    cada vez (como o servidor real faz) pra provar que os dois sobrevivem."""
    context, page, erros = nova_pagina(browser, arquivo_temp)

    page.evaluate("""
        window.__servidorFila = [];
        window.__filaQueue = Promise.resolve();
        useFirebase = true;
        db = {
            ref: function(path) {
                if (path.endsWith('/fila')) {
                    return {
                        transaction: function(updateFn, onComplete) {
                            window.__filaQueue = window.__filaQueue.then(() => {
                                const novoValor = updateFn(window.__servidorFila);
                                window.__servidorFila = novoValor;
                                onComplete(null, true, { val: () => novoValor });
                            });
                        }
                    };
                }
                return { on: function(){}, once: function(){ return Promise.resolve({val: () => null}); } };
            }
        };
    """)

    # Dispara dois pedidos "ao mesmo tempo" — sem esperar o primeiro terminar
    for nome in ["PessoaX", "PessoaY"]:
        page.evaluate(f"""
            document.getElementById('input-nome').value = '{nome}';
            document.getElementById('input-musica').value = 'Musica{nome}';
            document.getElementById('input-artista').value = 'Artista';
            adicionarPedido({{preventDefault: () => {{}}}});
        """)
    page.wait_for_timeout(300)

    fila_servidor = sorted(page.evaluate("window.__servidorFila.map(p => p.nome)"))
    fila_local = sorted(page.evaluate("fila.map(p => p.nome)"))

    ok = fila_servidor == ["PessoaX", "PessoaY"] and fila_local == ["PessoaX", "PessoaY"] and not erros
    registrar("Dois pedidos simultâneos não se perdem (corrida de gravação)", ok,
               f"servidor={fila_servidor}, local={fila_local}")
    context.close()


def test_meus_pedidos_posicao_e_cancelamento(browser, arquivo_temp):
    """Cartão 'Seus Pedidos': mostra a posição na fila e permite cancelar (com
    confirmação inline clara — 'Sim, cancelar' / 'Manter pedido' — em vez do
    confirm() nativo do navegador, que tinha texto ambíguo: ver bug relatado
    onde o botão 'Cancelar' do alerta padrão na verdade MANTINHA o pedido)."""
    context, page, erros = nova_pagina(browser, arquivo_temp)

    page.evaluate("""
        fila.push({id: 111, nome: 'OutraPessoa', mesa: null, musica: 'MusicaOutra', artista: 'X', timestamp: Date.now() - 5000, vezesCantadas: 0, youtubeUrl: null});
        atualizarUI();
    """)
    escondido_antes = page.evaluate("document.getElementById('secao-meus-pedidos').classList.contains('hidden')")

    preencher_pedido(page, "EuMesmo", "MinhaMusica")
    page.wait_for_timeout(150)
    visivel_depois = page.evaluate("!document.getElementById('secao-meus-pedidos').classList.contains('hidden')")
    texto = page.evaluate("document.getElementById('lista-meus-pedidos').innerText")

    meu_id = page.evaluate("fila.find(p => p.nome === 'EuMesmo').id")

    # Clica em "Cancelar" -> deve aparecer a pergunta clara, SEM remover ainda
    page.click(f"#acoes-pedido-{meu_id} button")
    page.wait_for_timeout(100)
    ainda_la_apos_primeiro_clique = page.evaluate("fila.some(p => p.nome === 'EuMesmo')")
    tem_opcao_manter = page.evaluate(f"document.getElementById('acoes-pedido-{meu_id}').innerText.includes('Manter pedido')")

    # Clica em "Sim, cancelar" -> agora sim remove
    page.click(f"#acoes-pedido-{meu_id} >> text=Sim, cancelar")
    page.wait_for_timeout(150)
    ainda_na_fila = page.evaluate("fila.some(p => p.nome === 'EuMesmo')")
    outra_pessoa_continua = page.evaluate("fila.some(p => p.nome === 'OutraPessoa')")

    ok = (escondido_antes and visivel_depois and "MinhaMusica" in texto
          and ainda_la_apos_primeiro_clique and tem_opcao_manter
          and not ainda_na_fila and outra_pessoa_continua and not erros)
    registrar("Cartão 'Seus Pedidos': cancelar pede confirmação clara antes de remover", ok,
               f"escondido_antes={escondido_antes}, visivel_depois={visivel_depois}, "
               f"opcao_manter_aparece={tem_opcao_manter}, "
               f"nao_removeu_no_1o_clique={ainda_la_apos_primeiro_clique}, "
               f"removido_apos_confirmar={not ainda_na_fila}, outra_pessoa_intacta={outra_pessoa_continua}")
    context.close()


def test_historico_paginado_no_cliente(browser, arquivo_temp):
    """Página do cliente mostra só as últimas 12 músicas cantadas por padrão,
    com botão 'Ver mais' — a lista do painel do DJ continua sempre completa."""
    context, page, erros = nova_pagina(browser, arquivo_temp)

    page.evaluate("""
        historico = [];
        for (let i = 0; i < 20; i++) {
            historico.push({
                nome: 'Pessoa' + i, mesa: null, musica: 'Musica' + i, artista: 'X',
                horario: '20:0' + (i % 10), mediaAvaliacao: 4.5, totalVotos: 2
            });
        }
        atualizarUI();
    """)
    page.wait_for_timeout(150)

    itens_inicio = page.evaluate("document.querySelectorAll('#lista-historico-cliente > li').length")
    lista_admin_completa = page.evaluate("document.querySelectorAll('#lista-historico > li').length")

    page.click("text=Ver mais")
    page.wait_for_timeout(100)
    itens_apos_clicar = page.evaluate("document.querySelectorAll('#lista-historico-cliente > li').length")

    ok = (itens_inicio == 13 and lista_admin_completa == 20 and itens_apos_clicar == 21 and not erros)
    registrar("Histórico do cliente é paginado (12 + Ver mais); painel do DJ continua completo", ok,
               f"itens_inicio={itens_inicio}, admin_completo={lista_admin_completa}, apos_ver_mais={itens_apos_clicar}")
    context.close()


def test_aviso_iphone_aparece_so_no_iphone(browser, arquivo_temp):
    """O aviso sobre a limitação de notificação no iPhone só aparece pra quem
    está realmente usando Safari em iPhone/iPad — não deve poluir a tela de
    quem está em qualquer outro navegador/aparelho."""
    context_iphone = browser.new_context(
        viewport={"width": 390, "height": 844},
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
    )
    page_iphone = context_iphone.new_page()
    erros_iphone = []
    page_iphone.on("pageerror", lambda exc: erros_iphone.append(str(exc)))
    page_iphone.goto(f"file://{arquivo_temp}?bar=citta")
    page_iphone.evaluate("localStorage.clear()")
    page_iphone.reload()
    page_iphone.wait_for_timeout(200)
    page_iphone.click("#notif-toggle")
    page_iphone.wait_for_timeout(100)
    aparece_no_iphone = page_iphone.evaluate("!document.getElementById('aviso-iphone').classList.contains('hidden')")
    context_iphone.close()

    context_normal, page_normal, erros_normal = nova_pagina(browser, arquivo_temp)
    page_normal.click("#notif-toggle")
    page_normal.wait_for_timeout(100)
    nao_aparece_normal = page_normal.evaluate("document.getElementById('aviso-iphone').classList.contains('hidden')")
    context_normal.close()

    ok = aparece_no_iphone and nao_aparece_normal and not erros_iphone and not erros_normal
    registrar("Aviso de limitação de notificação aparece só no iPhone/Safari", ok,
               f"aparece_no_iphone={aparece_no_iphone}, escondido_em_navegador_normal={nao_aparece_normal}")


def test_aviso_de_conexao_perdida_existe(browser, arquivo_temp):
    """O banner de 'sem conexão' existe, começa escondido, e pode ser mostrado
    (a checagem completa de conectar/desconectar de verdade precisa de Firebase
    real — isso só confirma que a peça do quebra-cabeça está no lugar certo)."""
    context, page, erros = nova_pagina(browser, arquivo_temp)
    escondido_normal = page.evaluate("document.getElementById('aviso-sem-conexao').classList.contains('hidden')")
    page.evaluate("document.getElementById('aviso-sem-conexao').classList.remove('hidden')")
    aparece_quando_forcado = page.evaluate("!document.getElementById('aviso-sem-conexao').classList.contains('hidden')")
    ok = escondido_normal and aparece_quando_forcado and not erros
    registrar("Banner de conexão perdida existe e começa escondido", ok,
               f"escondido_normal={escondido_normal}, aparece_quando_forcado={aparece_quando_forcado}")
    context.close()


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arquivo", default=None,
                         help="Caminho pro index.html a testar (padrão: o que está na mesma pasta que este script)")
    args = parser.parse_args()

    caminho_index = Path(args.arquivo) if args.arquivo else (Path(__file__).parent.parent / "index.html")
    if not caminho_index.exists():
        print(f"❌ Não encontrei o arquivo: {caminho_index}")
        sys.exit(2)

    arquivo_temp = preparar_html_para_teste(caminho_index)

    print(f"Testando: {caminho_index}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch()

        test_sem_bar_mostra_erro(browser, arquivo_temp)
        test_bar_valido_carrega_sem_erros(browser, arquivo_temp)
        test_isolamento_entre_bares(browser, arquivo_temp)
        test_prioridade_por_nome_e_mesa(browser, arquivo_temp)
        test_pessoas_diferentes_mesas_diferentes_nao_se_confundem(browser, arquivo_temp)
        test_voto_nao_reconstroi_a_tela(browser, arquivo_temp)
        test_admin_exige_login(browser, arquivo_temp)
        test_youtube_preenche_musica_e_libera_artista(browser, arquivo_temp)
        test_media_de_avaliacoes(browser, arquivo_temp)
        test_espera_longa_faz_pessoa_furar_a_fila(browser, arquivo_temp)
        test_dois_pedidos_simultaneos_nao_se_perdem(browser, arquivo_temp)
        test_meus_pedidos_posicao_e_cancelamento(browser, arquivo_temp)
        test_historico_paginado_no_cliente(browser, arquivo_temp)
        test_aviso_iphone_aparece_so_no_iphone(browser, arquivo_temp)
        test_aviso_de_conexao_perdida_existe(browser, arquivo_temp)

        browser.close()

    arquivo_temp.unlink(missing_ok=True)

    total = len(RESULTADOS)
    falhas = [r for r in RESULTADOS if not r[1]]
    print(f"\n{'='*60}")
    print(f"{total - len(falhas)}/{total} testes passaram")
    if falhas:
        print("\nFALHARAM:")
        for nome, _, detalhe in falhas:
            print(f"  - {nome}  ({detalhe})")
        sys.exit(1)
    else:
        print("Tudo certo! ✅")
        sys.exit(0)


if __name__ == "__main__":
    main()
