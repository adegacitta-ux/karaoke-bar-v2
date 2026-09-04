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

    (ou aponte pra outro index.html com --arquivo /caminho/index.html — a pasta
    inteira onde esse arquivo está é servida por HTTP local automaticamente)

Os testes sobem um servidor HTTP local (python -m http.server, não file://) e
esperam o Tailwind CDN carregar de verdade antes de checar qualquer coisa na
tela. Se o ambiente não tiver internet pra baixar o Tailwind, a suíte AVISA
isso claramente no terminal e roda em modo degradado (só um CSS mínimo de
compatibilidade) — não finge que testou com o Tailwind real.

Cada teste imprime PASS ou FAIL. Ao final, mostra um resumo e sai com
código de erro != 0 se algo falhou (útil pra rodar antes de qualquer deploy).
"""

import sys
import re
import json
import argparse
import functools
import http.server
import socketserver
import socket
import threading
import contextlib
from pathlib import Path
from datetime import datetime

from playwright.sync_api import sync_playwright


RESULTADOS = []
_AVISO_TAILWIND_JA_MOSTRADO = False
ARQUIVO_INDEX = "index.html"  # ajustado em main() se --arquivo apontar pra outro nome
CAMINHO_INDEX = None  # Path completo, ajustado em main() — usado pelos testes estáticos (sem browser)
CAMINHO_REGRAS = None  # Path completo do database.rules.json correspondente


def registrar(nome, ok, detalhe=""):
    RESULTADOS.append((nome, ok, detalhe))
    marca = "✅ PASS" if ok else "❌ FAIL"
    linha = f"{marca}  {nome}"
    if detalhe:
        linha += f"  —  {detalhe}"
    print(linha)


def _porta_livre():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def servidor_http(pasta):
    """Sobe um servidor HTTP local de verdade (python -m http.server) servindo a
    pasta do projeto — mais fiel à produção (GitHub Pages serve por HTTP) do que
    abrir os arquivos direto por file://, que tem regras de navegador diferentes
    (ex: alguns comportamentos de fetch/CORS só se manifestam via http/https)."""
    porta = _porta_livre()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(pasta))
    httpd = socketserver.TCPServer(("127.0.0.1", porta), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{porta}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def aguardar_tailwind(page, timeout_ms=4000):
    """Espera o Tailwind CDN carregar e gerar as classes utilitárias DE VERDADE
    (ele injeta os estilos via JS depois que o <script> externo carrega — não é
    instantâneo). Confirma checando uma propriedade bem específica do Tailwind
    (border-radius de .rounded-2xl) que só existe se o CDN realmente rodou.

    Se não conseguir carregar dentro do tempo — tipicamente por falta de acesso à
    internet no ambiente que está rodando os testes — cai para um CSS mínimo
    (só a classe .hidden) pra não travar a suíte inteira, mas avisa isso
    CLARAMENTE no terminal, porque testar sem o Tailwind real não é equivalente:
    é um modo degradado, não a validação completa."""
    global _AVISO_TAILWIND_JA_MOSTRADO
    try:
        page.wait_for_function(
            """() => {
                const el = document.createElement('div');
                el.className = 'rounded-2xl';
                document.body.appendChild(el);
                const raio = getComputedStyle(el).borderRadius;
                el.remove();
                return raio !== '' && raio !== '0px';
            }""",
            timeout=timeout_ms,
        )
        return True
    except Exception:
        pass

    if not _AVISO_TAILWIND_JA_MOSTRADO:
        print("⚠️  AVISO: o Tailwind CDN não carregou (provavelmente sem acesso à "
              "internet neste ambiente). Os testes vão rodar com um CSS mínimo de "
              "compatibilidade (só '.hidden'), o que NÃO é equivalente a testar com "
              "o Tailwind de verdade. Rode esta suíte num ambiente com internet "
              "pra validação completa antes de qualquer deploy.")
        _AVISO_TAILWIND_JA_MOSTRADO = True
    page.add_style_tag(content=".hidden{display:none;}")
    return False


def nova_pagina(browser, base_url, bar="citta", viewport=None):
    context = browser.new_context(viewport=viewport or {"width": 480, "height": 900},
                                   permissions=["notifications"])
    page = context.new_page()
    erros = []
    page.on("pageerror", lambda exc: erros.append(str(exc)))
    url = f"{base_url}/{ARQUIVO_INDEX}"
    if bar is not None:
        url += f"?bar={bar}"
    page.goto(url)
    aguardar_tailwind(page)
    page.evaluate("localStorage.clear()")
    page.reload()
    aguardar_tailwind(page)
    page.wait_for_timeout(250)

    # O app fecha a fila automaticamente perto das 23h (HORARIO_LIMITE) — sem isso,
    # os testes ficam "flaky": passam de dia e falham à noite, dependendo da hora
    # real de quem rodar. Neutraliza só pros testes, não é um bug do app.
    if bar is not None:
        page.evaluate("window.isFilaBloqueada = () => false;")

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

def test_sem_bar_mostra_erro(browser, base_url):
    context, page, erros = nova_pagina(browser, base_url, bar=None)
    tem_aviso = page.evaluate("document.body.innerText.includes('Link incompleto')")
    ok = tem_aviso and not erros
    registrar("Acessar sem ?bar= mostra aviso claro (sem tela quebrada)", ok,
               f"aviso presente={tem_aviso}, erros JS={erros}")
    context.close()


def test_bar_valido_carrega_sem_erros(browser, base_url):
    context, page, erros = nova_pagina(browser, base_url, bar="citta")
    ok = len(erros) == 0
    registrar("Acessar com ?bar=citta carrega sem erros de JS", ok, f"erros={erros}")
    context.close()


def test_isolamento_entre_bares(browser, base_url):
    context, page, _ = nova_pagina(browser, base_url, bar="citta")
    preencher_pedido(page, "PessoaDoCitta", "MusicaDoCitta")
    fila_citta = page.evaluate("fila.map(p => p.nome)")
    context.close()

    context2, page2, _ = nova_pagina(browser, base_url, bar="outrobar")
    fila_outrobar = page2.evaluate("fila.map(p => p.nome)")
    context2.close()

    ok = fila_citta == ["PessoaDoCitta"] and fila_outrobar == []
    registrar("Dados de um bar não vazam pra outro (?bar=citta vs ?bar=outrobar)", ok,
               f"citta={fila_citta}, outrobar={fila_outrobar}")


def test_prioridade_por_nome_e_mesa(browser, base_url):
    context, page, erros = nova_pagina(browser, base_url)
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


def test_pessoas_diferentes_mesas_diferentes_nao_se_confundem(browser, base_url):
    context, page, erros = nova_pagina(browser, base_url)
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


def test_voto_nao_reconstroi_a_tela(browser, base_url):
    """Este é o teste mais importante: replica o bug real de produção onde o
    Firebase reordena as chaves dos objetos, e isso fazia a tela toda
    piscar/recarregar a cada voto."""
    context, page, erros = nova_pagina(browser, base_url)
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


def test_admin_exige_login(browser, base_url):
    context, page, erros = nova_pagina(browser, base_url)
    autenticado_antes = page.evaluate("isAdminAuthenticated()")
    page.evaluate("switchTab('admin')")
    page.wait_for_timeout(100)
    modal_visivel = page.evaluate("!document.getElementById('admin-auth-modal').classList.contains('hidden')")
    ok = (not autenticado_antes) and modal_visivel and not erros
    registrar("Acessar aba Admin sem login mostra o modal de senha", ok,
               f"autenticado_antes={autenticado_antes}, modal_visivel={modal_visivel}")
    context.close()


def test_youtube_preenche_musica_e_libera_artista(browser, base_url):
    context, page, erros = nova_pagina(browser, base_url)

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


def test_media_de_avaliacoes(browser, base_url):
    context, page, erros = nova_pagina(browser, base_url)
    media = page.evaluate("mediaEVotos({a: 5, b: 4, c: 5, d: 3, e: 5}).media")
    votos = page.evaluate("mediaEVotos({a: 5, b: 4, c: 5, d: 3, e: 5}).votos")
    ok = media == 4.4 and votos == 5 and not erros
    registrar("Cálculo da média de avaliações está correto", ok, f"media={media}, votos={votos}")
    context.close()


def test_espera_longa_faz_pessoa_furar_a_fila(browser, base_url):
    """Regra pedida após teste com público real: quem já cantou não pode ficar
    preso no fim da fila pra sempre só porque gente nova continua chegando —
    com tempo de espera suficiente, ela volta a furar a frente."""
    context, page, erros = nova_pagina(browser, base_url)

    preencher_pedido(page, "PessoaA", "MusicaA1")
    id_a = page.evaluate("fila[0].id")
    page.evaluate(f"acaoProximo({id_a})")
    page.evaluate("acaoFinalizarApresentacao()")
    page.wait_for_timeout(100)

    # Pessoa A pede de novo (já com vezesCantadas=1) e Pessoa B, nova, entra depois.
    # Pessoa B precisa ser um deviceId DIFERENTE: a identidade da fila agora é por
    # deviceId (ver test_deviceid_impede_burlar_cooldown_trocando_nome), então se
    # ela viesse pelo mesmo formulário/navegador desta página ela contaria como o
    # MESMO dispositivo de Pessoa A, o que não é o que este teste quer simular.
    preencher_pedido(page, "PessoaA", "MusicaA2")
    page.evaluate("""
        fila.push({
            id: 777001, nome: 'PessoaB', mesa: null, musica: 'MusicaB1', artista: 'X',
            deviceId: 'device-pessoab-outro-aparelho',
            timestamp: Date.now(), timestampFila: Date.now(), vezesCantadas: 0, youtubeUrl: null
        });
        ordenarFila();
        atualizarUI();
    """)
    ordem_normal = page.evaluate("fila.map(p => p.nome)")

    # Simula 20 minutos de espera no pedido da Pessoa A (mais que o limite de
    # 15min configurado pra perdoar uma vez cantada)
    # Simula uma espera bem maior que o limite configurado (2x + 5min de folga),
    # pra esse teste continuar valendo mesmo se você mudar o valor do minutos-pra-perdoar
    limite_minutos = page.evaluate("MINUTOS_PARA_PERDOAR_UMA_VEZ_CANTADA")
    minutos_de_espera_simulada = (limite_minutos * 2) + 5
    # "timestampFila" é o relógio de espera que a fila usa pra calcular prioridade
    # (ver calcularPrioridadeEfetiva) — "timestamp" puro é só a hora do pedido,
    # usada no relatório de horário de pico, e não afeta mais a ordem da fila.
    page.evaluate(f"""
        const pedidoA = fila.find(p => p.nome === 'PessoaA');
        pedidoA.timestampFila = Date.now() - ({minutos_de_espera_simulada} * 60 * 1000);
    """)
    page.evaluate("atualizarUI()")
    page.wait_for_timeout(100)
    ordem_apos_espera = page.evaluate("fila.map(p => p.nome)")

    ok = (ordem_normal[0] == "PessoaB" and ordem_apos_espera[0] == "PessoaA" and not erros)
    registrar("Espera longa faz quem já cantou furar a frente de quem é novo", ok,
               f"sem_esperar={ordem_normal}, apos_20min={ordem_apos_espera}")
    context.close()


def test_fila_evita_pedidos_consecutivos_da_mesma_pessoa(browser, base_url):
    """Regra anti-sequência: dois pedidos da MESMA pessoa (mesmo deviceId) não
    devem ficar colados um atrás do outro no topo da fila, furando quem já
    está esperando — mesmo que a prioridade "bruta" colocasse os dois juntos.
    ordenarFila() deve trazer pra frente o próximo pedido de outra pessoa,
    já que a diferença de prioridade entre os dois é pequena aqui."""
    context, page, erros = nova_pagina(browser, base_url)

    agora = page.evaluate("Date.now()")
    page.evaluate(f"""
        fila = [
            {{id: 1, nome: 'PessoaA', mesa: null, musica: 'MusicaA1', artista: 'X',
              deviceId: 'device-a', timestamp: {agora}, timestampFila: {agora},
              vezesCantadas: 0, youtubeUrl: null}},
            {{id: 2, nome: 'PessoaA', mesa: null, musica: 'MusicaA2', artista: 'X',
              deviceId: 'device-a', timestamp: {agora + 1000}, timestampFila: {agora + 1000},
              vezesCantadas: 0, youtubeUrl: null}},
            {{id: 3, nome: 'PessoaB', mesa: null, musica: 'MusicaB1', artista: 'X',
              deviceId: 'device-b', timestamp: {agora + 2000}, timestampFila: {agora + 2000},
              vezesCantadas: 0, youtubeUrl: null}}
        ];
        ordenarFila();
        atualizarUI();
    """)

    ids_ordem = page.evaluate("fila.map(p => p.id)")
    ok = ids_ordem == [1, 3, 2] and not erros
    registrar("Pedidos consecutivos da mesma pessoa são separados pelo próximo pedido de outra pessoa", ok,
               f"ids_ordem={ids_ordem}")
    context.close()


def test_fila_mantem_sequencia_quando_so_sobra_a_mesma_pessoa(browser, base_url):
    """Se TODOS os pedidos restantes na fila são da mesma pessoa, não tem outra
    pessoa pra trazer pra frente — a sequência é mantida (não dá pra evitar)."""
    context, page, erros = nova_pagina(browser, base_url)

    agora = page.evaluate("Date.now()")
    page.evaluate(f"""
        fila = [
            {{id: 1, nome: 'PessoaA', mesa: null, musica: 'MusicaA1', artista: 'X',
              deviceId: 'device-a', timestamp: {agora}, timestampFila: {agora},
              vezesCantadas: 0, youtubeUrl: null}},
            {{id: 2, nome: 'PessoaA', mesa: null, musica: 'MusicaA2', artista: 'X',
              deviceId: 'device-a', timestamp: {agora + 1000}, timestampFila: {agora + 1000},
              vezesCantadas: 0, youtubeUrl: null}},
            {{id: 3, nome: 'PessoaA', mesa: null, musica: 'MusicaA3', artista: 'X',
              deviceId: 'device-a', timestamp: {agora + 2000}, timestampFila: {agora + 2000},
              vezesCantadas: 0, youtubeUrl: null}}
        ];
        ordenarFila();
        atualizarUI();
    """)

    ids_ordem = page.evaluate("fila.map(p => p.id)")
    ok = ids_ordem == [1, 2, 3] and not erros
    registrar("Fila com pedidos só da mesma pessoa mantém a sequência (não tem como evitar)", ok,
               f"ids_ordem={ids_ordem}")
    context.close()


def test_fila_nao_fura_prioridade_pra_desfazer_sequencia(browser, base_url):
    """A troca anti-sequência só deve acontecer se a diferença de prioridade
    entre os dois pedidos envolvidos for pequena (LIMITE_TROCA_ANTI_SEQUENCIA)
    — não vale furar a frente de alguém com prioridade bem pior só pra separar
    os pedidos consecutivos da mesma pessoa."""
    context, page, erros = nova_pagina(browser, base_url)

    limite = page.evaluate("LIMITE_TROCA_ANTI_SEQUENCIA")
    agora = page.evaluate("Date.now()")
    page.evaluate(f"""
        fila = [
            {{id: 1, nome: 'PessoaA', mesa: null, musica: 'MusicaA1', artista: 'X',
              deviceId: 'device-a', timestamp: {agora}, timestampFila: {agora},
              vezesCantadas: 0, youtubeUrl: null}},
            {{id: 2, nome: 'PessoaA', mesa: null, musica: 'MusicaA2', artista: 'X',
              deviceId: 'device-a', timestamp: {agora}, timestampFila: {agora},
              vezesCantadas: 0, youtubeUrl: null}},
            {{id: 3, nome: 'PessoaB', mesa: null, musica: 'MusicaB1', artista: 'X',
              deviceId: 'device-b', timestamp: {agora}, timestampFila: {agora},
              vezesCantadas: {limite + 5}, youtubeUrl: null}}
        ];
        ordenarFila();
        atualizarUI();
    """)

    ids_ordem = page.evaluate("fila.map(p => p.id)")
    ok = ids_ordem == [1, 2, 3] and not erros
    registrar("Troca anti-sequência não fura fila de quem tem prioridade bem pior", ok,
               f"ids_ordem={ids_ordem}, limite={limite}")
    context.close()


def test_teto_de_espera_maxima_fura_mesmo_com_vezes_cantadas_alto(browser, base_url):
    """O desconto de calcularPrioridadeEfetiva é linear e na mesma taxa pra
    todo mundo — então a DIFERENÇA de prioridade entre dois pedidos que já
    estão na fila nunca muda com o tempo, só porque os dois descontos crescem
    juntos. Sem um teto, alguém com vezesCantadas bem alto (ex: 7x) ficaria
    preso atrás de gente com vezesCantadas baixo pra sempre, não importa
    quanto tempo espere. MINUTOS_ESPERA_MAXIMA existe pra quebrar esse
    travamento: passado esse teto, o pedido fura pra frente de qualquer um."""
    context, page, erros = nova_pagina(browser, base_url)

    teto_minutos = page.evaluate("MINUTOS_ESPERA_MAXIMA")

    # PessoaVeterana já cantou muitas vezes (prioridade efetiva ruim mesmo sem
    # o teto) e está esperando bem mais que o teto configurado.
    # PessoaRecente é nova (vezesCantadas=0) e chegou bem depois — sem o teto,
    # ela ficaria na frente pra sempre, já que a diferença de prioridade entre
    # os dois nunca diminui com o tempo (só o próprio teto quebra isso).
    page.evaluate(f"""
        fila.length = 0;
        fila.push({{
            id: 777101, nome: 'PessoaVeterana', mesa: null, musica: 'MusicaV', artista: 'X',
            deviceId: 'device-veterana',
            timestamp: Date.now() - ({teto_minutos} * 2 * 60 * 1000),
            timestampFila: Date.now() - ({teto_minutos} * 2 * 60 * 1000),
            vezesCantadas: 7, youtubeUrl: null
        }});
        fila.push({{
            id: 777102, nome: 'PessoaRecente', mesa: null, musica: 'MusicaR', artista: 'X',
            deviceId: 'device-recente',
            timestamp: Date.now(), timestampFila: Date.now(),
            vezesCantadas: 0, youtubeUrl: null
        }});
        atualizarUI();
    """)
    page.wait_for_timeout(100)
    ordem_apos_teto = page.evaluate("fila.map(p => p.nome)")

    ok = (ordem_apos_teto[0] == "PessoaVeterana" and not erros)
    registrar("Teto de espera máxima fura a fila mesmo com vezesCantadas alto", ok,
               f"teto_minutos={teto_minutos}, ordem={ordem_apos_teto}")
    context.close()


def test_teto_de_espera_maxima_empate_por_ordem_de_chegada(browser, base_url):
    """Quando MÚLTIPLOS pedidos passam do teto ao mesmo tempo (todos com
    prioridade forçada a -Infinity), o empate deve ser resolvido por quem
    está esperando há mais tempo (timestampFila mais antigo primeiro) —
    mesmo tie-break de sempre, usado em qualquer empate de ordenarFila()."""
    context, page, erros = nova_pagina(browser, base_url)

    teto_minutos = page.evaluate("MINUTOS_ESPERA_MAXIMA")

    page.evaluate(f"""
        fila.length = 0;
        fila.push({{
            id: 777201, nome: 'MaisAntiga', mesa: null, musica: 'M1', artista: 'X',
            deviceId: 'device-mais-antiga',
            timestamp: Date.now() - ({teto_minutos} * 3 * 60 * 1000),
            timestampFila: Date.now() - ({teto_minutos} * 3 * 60 * 1000),
            vezesCantadas: 0, youtubeUrl: null
        }});
        fila.push({{
            id: 777202, nome: 'MaisNova', mesa: null, musica: 'M2', artista: 'X',
            deviceId: 'device-mais-nova',
            timestamp: Date.now() - ({teto_minutos} * 2 * 60 * 1000),
            timestampFila: Date.now() - ({teto_minutos} * 2 * 60 * 1000),
            vezesCantadas: 5, youtubeUrl: null
        }});
        atualizarUI();
    """)
    page.wait_for_timeout(100)
    ordem = page.evaluate("fila.map(p => p.nome)")

    ok = (ordem == ["MaisAntiga", "MaisNova"] and not erros)
    registrar("Empate entre pedidos acima do teto respeita ordem de chegada", ok,
               f"teto_minutos={teto_minutos}, ordem={ordem}")
    context.close()


def test_deviceid_impede_burlar_cooldown_trocando_nome(browser, base_url):
    """Anti-fraude (deviceId): antes, "vezesCantadas" era agrupado por nome+mesa
    digitados — bastava digitar um nome diferente pra "resetar" a prioridade de
    quem já cantou. Agora a identidade real é o deviceId (o mesmo navegador),
    então trocar nome e mesa não deve mais ter esse efeito."""
    context, page, erros = nova_pagina(browser, base_url)

    preencher_pedido(page, "PessoaOriginal", "Musica1", mesa="1")
    id1 = page.evaluate("fila[0].id")
    page.evaluate(f"acaoProximo({id1})")
    page.evaluate("acaoFinalizarApresentacao()")
    page.wait_for_timeout(100)

    # Mesmo dispositivo/navegador, mas nome E mesa completamente diferentes
    preencher_pedido(page, "NomeTotalmenteDiferente", "Musica2", mesa="99")
    pedido2 = page.evaluate("fila.find(p => p.musica === 'Musica2')")
    device_id_bate = page.evaluate("fila.find(p => p.musica === 'Musica2').deviceId === DEVICE_ID")

    ok = pedido2 is not None and pedido2["vezesCantadas"] == 1 and device_id_bate and not erros
    registrar("Trocar nome/mesa não reseta a prioridade — deviceId é a identidade real", ok,
               f"vezesCantadas={pedido2 and pedido2.get('vezesCantadas')}, deviceId_bate={device_id_bate}")
    context.close()


def test_dois_pedidos_simultaneos_nao_se_perdem(browser, base_url):
    """Regra crítica: reproduz o bug relatado de nomes "sumindo e reaparecendo".
    Causa era uma corrida de gravação — dois pedidos quase ao mesmo tempo podiam
    se sobrescrever. Usa um Firebase simulado que processa uma transação de
    cada vez (como o servidor real faz) pra provar que os dois sobrevivem."""
    context, page, erros = nova_pagina(browser, base_url)

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


def test_limite_de_creditos_bloqueia_sexto_pedido_com_fila_cheia(browser, base_url):
    """Teto de créditos por dispositivo: depois de LIMITE_PEDIDOS_ATIVOS_POR_DEVICE
    pedidos pendentes do mesmo device, o próximo é bloqueado — desde que haja
    gente suficiente de FORA desse device esperando (senão a fila é considerada
    "curta" e o limite é ignorado, ver o teste seguinte)."""
    context, page, erros = nova_pagina(browser, base_url)

    limite = page.evaluate("LIMITE_PEDIDOS_ATIVOS_POR_DEVICE")
    limiar_fila_curta = page.evaluate("LIMIAR_FILA_CURTA")

    # Gente de OUTROS dispositivos esperando, o suficiente pra fila não ser "curta"
    page.evaluate(f"""
        fila = Array.from({{length: {limiar_fila_curta}}}, (_, i) => ({{
            id: 9000 + i, nome: 'Outro' + i, mesa: null, musica: 'MusicaOutro' + i,
            artista: 'X', deviceId: 'outro-device-' + i,
            timestamp: Date.now(), timestampFila: Date.now(), vezesCantadas: 0, youtubeUrl: null
        }}));
        atualizarUI();
    """)

    for i in range(limite):
        preencher_pedido(page, "MesmoDispositivo", f"MinhaMusica{i}")
    total_antes = page.evaluate("fila.filter(p => p.deviceId === DEVICE_ID).length")

    bloqueou = {"sim": False}
    page.on("dialog", lambda dialog: (bloqueou.__setitem__("sim", True), dialog.accept()))
    preencher_pedido(page, "MesmoDispositivo", "MusicaQueDeveriaSerBloqueada")
    total_depois = page.evaluate("fila.filter(p => p.deviceId === DEVICE_ID).length")

    ok = total_antes == limite and total_depois == limite and bloqueou["sim"] and not erros
    registrar(f"{limite + 1}º pedido pendente do mesmo device é bloqueado (fila não está curta)", ok,
               f"antes={total_antes}, depois={total_depois}, bloqueou={bloqueou['sim']}")
    context.close()


def test_limite_de_creditos_libera_com_fila_curta(browser, base_url):
    """Mesmo cenário do teste acima, mas sem gente de outros dispositivos
    esperando — a fila "curta" deve liberar o pedido mesmo tendo estourado o
    teto de créditos, pra não travar um cliente sozinho num bar vazio."""
    context, page, erros = nova_pagina(browser, base_url)

    limite = page.evaluate("LIMITE_PEDIDOS_ATIVOS_POR_DEVICE")

    for i in range(limite):
        preencher_pedido(page, "MesmoDispositivo", f"MinhaMusica{i}")
    total_antes = page.evaluate("fila.filter(p => p.deviceId === DEVICE_ID).length")

    preencher_pedido(page, "MesmoDispositivo", "MusicaQueDeveriaSerLiberada")
    total_depois = page.evaluate("fila.filter(p => p.deviceId === DEVICE_ID).length")

    ok = total_antes == limite and total_depois == limite + 1 and not erros
    registrar("Limite de créditos é ignorado quando a fila está curta (não trava cliente sozinho)", ok,
               f"antes={total_antes}, depois={total_depois}")
    context.close()


def test_cancelamento_admin_libera_credito_imediatamente(browser, base_url):
    """Se o DJ/admin remove (cancela) um pedido, o crédito correspondente deve
    voltar na hora — sem esperar os MINUTOS_RECARGA_CREDITO minutos — já que a
    contagem é sempre feita consultando a fila atual, não um contador separado."""
    context, page, erros = nova_pagina(browser, base_url)

    limite = page.evaluate("LIMITE_PEDIDOS_ATIVOS_POR_DEVICE")
    limiar_fila_curta = page.evaluate("LIMIAR_FILA_CURTA")

    page.evaluate(f"""
        fila = Array.from({{length: {limiar_fila_curta}}}, (_, i) => ({{
            id: 9000 + i, nome: 'Outro' + i, mesa: null, musica: 'MusicaOutro' + i,
            artista: 'X', deviceId: 'outro-device-' + i,
            timestamp: Date.now(), timestampFila: Date.now(), vezesCantadas: 0, youtubeUrl: null
        }}));
        atualizarUI();
    """)

    for i in range(limite):
        preencher_pedido(page, "MesmoDispositivo", f"MinhaMusica{i}")

    # Admin cancela (remove) um dos pedidos desse dispositivo
    id_para_remover = page.evaluate("fila.find(p => p.deviceId === DEVICE_ID).id")
    page.evaluate(f"acaoRemover({id_para_remover})")
    page.wait_for_timeout(100)

    # Agora deveria caber mais um pedido desse mesmo dispositivo, sem esperar nada
    preencher_pedido(page, "MesmoDispositivo", "MusicaAposCancelamento")
    conseguiu_pedir_de_novo = page.evaluate(
        "fila.some(p => p.deviceId === DEVICE_ID && p.musica === 'MusicaAposCancelamento')")

    ok = conseguiu_pedir_de_novo and not erros
    registrar("Cancelamento pelo admin libera o crédito na hora (sem esperar a janela de recarga)", ok,
               f"conseguiu_pedir_de_novo={conseguiu_pedir_de_novo}")
    context.close()


def test_indicador_creditos_nao_aparece_com_poucos_pedidos(browser, base_url):
    """O indicador visual de créditos deve ficar invisível durante o uso normal —
    só aparece perto do limite (ver LIMIAR_AVISO_CREDITO), não a cada pedido."""
    context, page, erros = nova_pagina(browser, base_url)

    limiar = page.evaluate("LIMIAR_AVISO_CREDITO")
    for i in range(limiar - 1):
        preencher_pedido(page, "MesmoDispositivo", f"Musica{i}")

    escondido = page.evaluate("document.getElementById('indicador-creditos').classList.contains('hidden')")

    ok = escondido and not erros
    registrar(f"Indicador de créditos fica escondido com menos de {limiar} pedidos ativos", ok,
               f"pedidos_feitos={limiar - 1}, escondido={escondido}")
    context.close()


def test_indicador_creditos_aparece_no_limiar(browser, base_url):
    """Ao atingir LIMIAR_AVISO_CREDITO pedidos ativos, o indicador aparece
    mostrando a contagem correta ("X de 5 pedidos usados")."""
    context, page, erros = nova_pagina(browser, base_url)

    limiar = page.evaluate("LIMIAR_AVISO_CREDITO")
    limite = page.evaluate("LIMITE_PEDIDOS_ATIVOS_POR_DEVICE")
    for i in range(limiar):
        preencher_pedido(page, "MesmoDispositivo", f"Musica{i}")

    visivel = page.evaluate("!document.getElementById('indicador-creditos').classList.contains('hidden')")
    texto = page.evaluate("document.getElementById('indicador-creditos').textContent")

    ok = visivel and str(limiar) in texto and str(limite) in texto and not erros
    registrar(f"Indicador de créditos aparece ao atingir {limiar} pedidos ativos, com contagem correta", ok,
               f"visivel={visivel}, texto='{texto}'")
    context.close()


def test_indicador_creditos_minutos_ate_liberar(browser, base_url):
    """O texto de "minutos até liberar" é calculado a partir do timestamp MAIS
    ANTIGO dentro da janela ativa: timestampMaisAntigo + MINUTOS_RECARGA_CREDITO."""
    context, page, erros = nova_pagina(browser, base_url)

    limiar = page.evaluate("LIMIAR_AVISO_CREDITO")
    minutos_recarga = page.evaluate("MINUTOS_RECARGA_CREDITO")

    for i in range(limiar):
        preencher_pedido(page, "MesmoDispositivo", f"Musica{i}")

    # Força o pedido mais antigo desse device a ter sido feito há X minutos —
    # simula a passagem do tempo sem precisar esperar de verdade
    minutos_passados = 10
    page.evaluate(f"""
        const meus = fila.filter(p => p.deviceId === DEVICE_ID);
        const maisAntigo = meus.reduce((a, b) => a.timestamp < b.timestamp ? a : b);
        maisAntigo.timestamp = Date.now() - ({minutos_passados} * 60 * 1000);
        atualizarUI();
    """)

    texto = page.evaluate("document.getElementById('indicador-creditos').textContent")
    minutos_esperados = minutos_recarga - minutos_passados

    ok = str(minutos_esperados) in texto and not erros
    registrar("Minutos até liberar é calculado a partir do pedido mais antigo da janela ativa", ok,
               f"minutos_passados={minutos_passados}, minutos_recarga={minutos_recarga}, "
               f"minutos_esperados={minutos_esperados}, texto='{texto}'")
    context.close()


def test_meus_pedidos_posicao_e_cancelamento(browser, base_url):
    """Cartão 'Seus Pedidos': mostra a posição na fila e permite cancelar (com
    confirmação inline clara — 'Sim, cancelar' / 'Manter pedido' — em vez do
    confirm() nativo do navegador, que tinha texto ambíguo: ver bug relatado
    onde o botão 'Cancelar' do alerta padrão na verdade MANTINHA o pedido)."""
    context, page, erros = nova_pagina(browser, base_url)

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


def test_historico_paginado_no_cliente(browser, base_url):
    """Página do cliente mostra só as últimas 12 músicas cantadas por padrão,
    com botão 'Ver mais' — a lista do painel do DJ continua sempre completa."""
    context, page, erros = nova_pagina(browser, base_url)

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


def test_aviso_iphone_aparece_so_no_iphone(browser, base_url):
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
    page_iphone.goto(f"{base_url}/{ARQUIVO_INDEX}?bar=citta")
    aguardar_tailwind(page_iphone)
    page_iphone.evaluate("localStorage.clear()")
    page_iphone.reload()
    aguardar_tailwind(page_iphone)
    page_iphone.wait_for_timeout(200)
    page_iphone.click("#notif-toggle")
    page_iphone.wait_for_timeout(100)
    aparece_no_iphone = page_iphone.evaluate("!document.getElementById('aviso-iphone').classList.contains('hidden')")
    context_iphone.close()

    context_normal, page_normal, erros_normal = nova_pagina(browser, base_url)
    page_normal.click("#notif-toggle")
    page_normal.wait_for_timeout(100)
    nao_aparece_normal = page_normal.evaluate("document.getElementById('aviso-iphone').classList.contains('hidden')")
    context_normal.close()

    ok = aparece_no_iphone and nao_aparece_normal and not erros_iphone and not erros_normal
    registrar("Aviso de limitação de notificação aparece só no iPhone/Safari", ok,
               f"aparece_no_iphone={aparece_no_iphone}, escondido_em_navegador_normal={nao_aparece_normal}")


def test_aviso_de_conexao_perdida_existe(browser, base_url):
    """O banner de 'sem conexão' existe, começa escondido, e pode ser mostrado
    (a checagem completa de conectar/desconectar de verdade precisa de Firebase
    real — isso só confirma que a peça do quebra-cabeça está no lugar certo)."""
    context, page, erros = nova_pagina(browser, base_url)
    escondido_normal = page.evaluate("document.getElementById('aviso-sem-conexao').classList.contains('hidden')")
    page.evaluate("document.getElementById('aviso-sem-conexao').classList.remove('hidden')")
    aparece_quando_forcado = page.evaluate("!document.getElementById('aviso-sem-conexao').classList.contains('hidden')")
    ok = escondido_normal and aparece_quando_forcado and not erros
    registrar("Banner de conexão perdida existe e começa escondido", ok,
               f"escondido_normal={escondido_normal}, aparece_quando_forcado={aparece_quando_forcado}")
    context.close()


def test_modo_escuro_alterna_e_persiste(browser, base_url):
    """O botão de modo escuro alterna a classe no <body>, muda o ícone (lua/sol),
    e a escolha continua valendo depois de recarregar a página."""
    context, page, erros = nova_pagina(browser, base_url)

    inicio_claro = not page.evaluate("document.body.classList.contains('modo-escuro')")
    page.click("#btn-toggle-tema")
    page.wait_for_timeout(100)
    ativou = page.evaluate("document.body.classList.contains('modo-escuro')")
    icone_virou_sol = page.evaluate("document.getElementById('icone-tema').className.includes('fa-sun')")

    page.reload()
    page.wait_for_timeout(300)
    persistiu = page.evaluate("document.body.classList.contains('modo-escuro')")

    ok = inicio_claro and ativou and icone_virou_sol and persistiu and not erros
    registrar("Modo escuro alterna, troca o ícone e persiste após recarregar", ok,
               f"inicio_claro={inicio_claro}, ativou={ativou}, icone_sol={icone_virou_sol}, persistiu={persistiu}")
    context.close()


def test_protecao_contra_xss(browser, base_url):
    """Nome, música e mesa digitados pelo cliente entram em vários lugares via
    innerHTML (fila do DJ, próximos, já cantadas) — sem escapar, alguém poderia
    digitar HTML/JavaScript malicioso nesses campos e rodar código na tela de
    outras pessoas conectadas (XSS). Confirma que isso está bloqueado.

    Mesa usa validação de formato (só letras/números/hífen) que já barra
    qualquer caractere de HTML antes mesmo de chegar no escape — por isso o
    payload malicioso de mesa é testado separadamente (deve ser REJEITADO pela
    validação, nem chegar a ser enviado). Nome e música não têm essa restrição
    de formato (afinal um nome ou música pode ter praticamente qualquer
    caractere), então neles o que protege é o escape de HTML mesmo — é isso que
    o envio principal deste teste continua cobrindo."""
    context, page, erros = nova_pagina(browser, base_url)

    disparou = {"sim": False}
    page.on("dialog", lambda dialog: (disparou.__setitem__("sim", True), dialog.dismiss()))

    # Mesa com payload malicioso -> a validação de formato deve rejeitar,
    # impedindo o envio do formulário inteiro
    if page.is_visible("#btn-nao-e-voce"):
        page.click("#btn-nao-e-voce")
    page.fill("#input-nome", "Pessoa Teste")
    page.fill("#input-mesa", '"><svg onload=alert(3)>')
    page.fill("#input-musica", "Musica Teste")
    page.fill("#input-artista", "X")
    page.click("#btn-enviar")
    page.wait_for_timeout(150)
    mesa_invalida_bloqueou_envio = page.evaluate("fila.length === 0")
    mesa_mostra_erro = page.evaluate("!document.getElementById('erro-mesa').classList.contains('hidden')")

    # Nome e música com payload malicioso, mesa válida -> deve enviar
    # normalmente, mas o conteúdo malicioso precisa aparecer ESCAPADO na tela
    page.fill("#input-mesa", "12")
    page.fill("#input-nome", "<img src=x onerror=alert(1)>")
    page.fill("#input-musica", "<script>alert(2)</script>Musica")
    page.fill("#input-artista", "X")
    page.click("#btn-enviar")
    page.wait_for_timeout(250)

    tem_img_real = page.evaluate("document.querySelectorAll('#tabela-fila img').length > 0")
    tem_svg_real = page.evaluate("document.querySelectorAll('#tabela-fila svg').length > 0")
    texto_literal = page.evaluate("document.getElementById('tabela-fila').innerText.includes('<img')")

    ok = (mesa_invalida_bloqueou_envio and mesa_mostra_erro
          and not disparou["sim"] and not tem_img_real and not tem_svg_real and texto_literal and not erros)
    registrar("Nome/música/mesa maliciosos não executam código (proteção XSS)", ok,
               f"mesa_invalida_bloqueada={mesa_invalida_bloqueou_envio}, mesa_mostra_erro={mesa_mostra_erro}, "
               f"script_disparou={disparou['sim']}, tag_img_real={tem_img_real}, "
               f"tag_svg_real={tem_svg_real}, aparece_como_texto={texto_literal}")
    context.close()


def test_listeners_separados_por_pedaco(browser, base_url):
    """Em vez de um listener só no nó inteiro do bar (que reenviava fila +
    histórico + tudo mais toda vez que qualquer coisa mudasse), cada pedaço
    (fila, apresentacaoAtual, contagem, manualFechada) tem seu próprio listener
    em tempo real, e o histórico usa limitToFirst em vez de vir tudo de uma vez."""
    context, page, erros = nova_pagina(browser, base_url)

    caminhos = page.evaluate("""
        (function() {
            window.__caminhos = [];
            useFirebase = true;
            db = {
                ref: function(path) {
                    return {
                        on: function(evento, cb) { window.__caminhos.push(path); cb({ val: () => null }); },
                        limitToFirst: function(n) {
                            return { on: function(evento, cb) {
                                window.__caminhos.push(path + ' (limitToFirst ' + n + ')');
                                cb({ val: () => null });
                            }};
                        },
                        once: function() { return Promise.resolve({ val: () => ({}) }); }
                    };
                }
            };
            sincronizarComFirebase();
            return window.__caminhos;
        })()
    """)

    tem_fila_tempo_real = any(c.endswith("/fila") for c in caminhos)
    tem_apresentacao_tempo_real = any(c.endswith("/apresentacaoAtual") for c in caminhos)
    tem_contagem_tempo_real = any(c.endswith("/contagem") for c in caminhos)
    historico_com_limite = any("historico" in c and "limitToFirst" in c for c in caminhos)
    sem_listener_no_no_pai = not any(c.endswith("/karaoke") for c in caminhos)

    ok = (tem_fila_tempo_real and tem_apresentacao_tempo_real and tem_contagem_tempo_real
          and historico_com_limite and sem_listener_no_no_pai and not erros)
    registrar("Listeners separados por pedaço (fila/apresentação/contagem em tempo real; histórico limitado)", ok,
               f"caminhos={caminhos}")
    context.close()


def test_historico_completo_sob_demanda(browser, base_url):
    """O histórico completo só é baixado quando alguém realmente pede pra ver
    tudo (clica 'Ver mais') — antes disso, só os primeiros ~12 ficam carregados,
    mesmo que existam muito mais no banco."""
    context, page, erros = nova_pagina(browser, base_url)

    page.evaluate("""
        window.__buscouCompleto = false;
        useFirebase = true;
        const historicoCompleto20 = [];
        for (let i = 0; i < 20; i++) {
            historicoCompleto20.push({nome: 'P'+i, musica: 'M'+i, artista: 'X', horario: '20:00', mediaAvaliacao: 4, totalVotos: 1});
        }
        db = {
            ref: function(path) {
                return {
                    limitToFirst: function(n) {
                        return { on: function(evento, cb) { cb({ val: () => historicoCompleto20.slice(0, n) }); } };
                    },
                    once: function() {
                        window.__buscouCompleto = true;
                        return Promise.resolve({ val: () => historicoCompleto20 });
                    },
                    on: function(evento, cb) { cb({ val: () => null }); }
                };
            }
        };
        sincronizarComFirebase();
    """)
    page.wait_for_timeout(150)

    tamanho_antes = page.evaluate("historico.length")
    buscou_antes = page.evaluate("window.__buscouCompleto")

    page.click("text=Ver mais")
    page.wait_for_timeout(200)

    tamanho_depois = page.evaluate("historico.length")
    buscou_depois = page.evaluate("window.__buscouCompleto")

    ok = (tamanho_antes <= 13 and not buscou_antes and tamanho_depois == 20 and buscou_depois and not erros)
    registrar("Histórico completo só é buscado sob demanda (clicar 'Ver mais')", ok,
               f"tamanho_antes={tamanho_antes}, buscou_antes={buscou_antes}, "
               f"tamanho_depois={tamanho_depois}, buscou_depois={buscou_depois}")
    context.close()


def test_validacao_de_formulario(browser, base_url):
    """Nome vazio, música vazia e mesa em formato inválido devem ser bloqueados
    no envio, com mensagem de erro clara — e o formulário deve aceitar
    normalmente quando os campos estão certos.

    Usa clique disparado via JS (element.click()) em vez do clique por
    coordenada do Playwright — neste ambiente de teste sem o Tailwind CDN
    carregado (ver aguardar_tailwind), o layout sem CSS de espaçamento pode
    deslocar alguns pixels quando uma mensagem de erro aparece, e o clique por
    coordenada às vezes "erra" o botão por uma fração de pixel nesse instante.
    Isso é uma instabilidade do ambiente de teste sem CSS real, não um bug do
    app — clique via JS não depende de coordenada na tela."""
    context, page, erros = nova_pagina(browser, base_url)

    def clicar_enviar():
        page.evaluate("document.getElementById('btn-enviar').click()")

    # Envio com nome e música vazios -> bloqueado, com erro visível
    page.fill("#input-nome", "")
    page.fill("#input-musica", "")
    page.fill("#input-artista", "X")
    clicar_enviar()
    page.wait_for_timeout(150)
    bloqueado_por_campos_vazios = page.evaluate("fila.length === 0")
    erro_nome_visivel = page.evaluate("!document.getElementById('erro-nome').classList.contains('hidden')")
    erro_musica_visivel = page.evaluate("!document.getElementById('erro-musica').classList.contains('hidden')")

    # Mesa com formato inválido (símbolos não permitidos) -> bloqueado
    page.fill("#input-nome", "Pessoa")
    page.fill("#input-mesa", "mesa@123!")
    page.fill("#input-musica", "Musica")
    clicar_enviar()
    page.wait_for_timeout(150)
    bloqueado_por_mesa_invalida = page.evaluate("fila.length === 0")

    # Tudo certo -> envia normalmente
    page.fill("#input-mesa", "12")
    clicar_enviar()
    page.wait_for_timeout(150)
    enviou_com_dados_validos = page.evaluate("fila.length === 1")

    ok = (bloqueado_por_campos_vazios and erro_nome_visivel and erro_musica_visivel
          and bloqueado_por_mesa_invalida and enviou_com_dados_validos and not erros)
    registrar("Formulário valida nome/música/mesa antes de enviar", ok,
               f"bloqueado_campos_vazios={bloqueado_por_campos_vazios}, erro_nome_visivel={erro_nome_visivel}, "
               f"erro_musica_visivel={erro_musica_visivel}, bloqueado_mesa_invalida={bloqueado_por_mesa_invalida}, "
               f"enviou_valido={enviou_com_dados_validos}")
    context.close()


def test_link_colado_no_campo_musica_e_bloqueado(browser, base_url):
    """Gente às vezes cola o link do YouTube direto no campo "Nome da Música"
    em vez de usar o botão "Buscar no YouTube". As regras do Firebase já
    rejeitam isso (database.rules.json, campo "musica"), mas antes dessa
    mudança o resultado era o erro genérico de permission_denied — agora o
    front-end bloqueia ANTES de tentar enviar, com uma mensagem explicando o
    motivo. Confere pt e en, e que música com nome normal não vira falso
    positivo."""
    context, page, erros = nova_pagina(browser, base_url)

    def clicar_enviar():
        page.evaluate("document.getElementById('btn-enviar').click()")

    page.fill("#input-nome", "Pessoa")
    page.fill("#input-artista", "X")

    # Link colado (sem espaço) -> bloqueado no front-end, mensagem certa, nada na fila
    page.fill("#input-musica", "https://youtube.com/watch?v=abc123")
    clicar_enviar()
    page.wait_for_timeout(150)
    bloqueado_pt = page.evaluate("fila.length === 0")
    mensagem_pt = page.evaluate("document.getElementById('erro-musica').innerText")
    esperado_pt = page.evaluate("t('erro_musica_link')")

    # Link com espaço na frente (" https://...") -> trim() ainda pega o caso
    page.fill("#input-musica", "   https://youtu.be/xyz789")
    clicar_enviar()
    page.wait_for_timeout(150)
    bloqueado_com_espaco = page.evaluate("fila.length === 0")

    # Nome de música normal -> continua funcionando (sem falso positivo)
    page.fill("#input-musica", "Evidências")
    clicar_enviar()
    page.wait_for_timeout(150)
    enviou_nome_normal = page.evaluate("fila.length === 1")

    # Troca pro inglês e repete a checagem do link
    page.evaluate("aplicarIdioma('en')")
    page.fill("#input-musica", "https://youtube.com/watch?v=abc123")
    clicar_enviar()
    page.wait_for_timeout(150)
    bloqueado_en = page.evaluate("fila.length === 1")  # continua 1 (não deixou enviar de novo)
    mensagem_en = page.evaluate("document.getElementById('erro-musica').innerText")
    esperado_en = page.evaluate("t('erro_musica_link')")

    ok = (bloqueado_pt and mensagem_pt == esperado_pt and bloqueado_com_espaco
          and enviou_nome_normal and bloqueado_en and mensagem_en == esperado_en
          and mensagem_pt != mensagem_en and not erros)
    registrar("Link colado no campo música é bloqueado no envio (pt/en), sem falso positivo em nome normal", ok,
               f"bloqueado_pt={bloqueado_pt}, mensagem_pt={mensagem_pt!r}, bloqueado_com_espaco={bloqueado_com_espaco}, "
               f"enviou_nome_normal={enviou_nome_normal}, bloqueado_en={bloqueado_en}, mensagem_en={mensagem_en!r}, "
               f"erros JS={erros}")
    context.close()


def test_acessibilidade_basica(browser, base_url):
    """Labels associados aos campos (via for/id), ícones decorativos marcados
    como aria-hidden, e áreas dinâmicas com aria-live — checagens estruturais
    básicas de acessibilidade."""
    context, page, erros = nova_pagina(browser, base_url)

    labels_associados = page.evaluate("""
        () => {
            const campos = ['input-nome', 'input-mesa', 'input-musica', 'input-artista'];
            return campos.every(id => document.querySelector(`label[for="${id}"]`) !== null);
        }
    """)
    tem_icones_aria_hidden = page.evaluate("document.querySelectorAll('i[aria-hidden=\"true\"]').length > 0")
    feedback_tem_aria_live = page.evaluate("document.getElementById('feedback-sucesso').getAttribute('aria-live') === 'polite'")
    abas_tem_role_tabpanel = page.evaluate("""
        document.getElementById('cliente').getAttribute('role') === 'tabpanel' &&
        document.getElementById('admin').getAttribute('role') === 'tabpanel'
    """)

    ok = (labels_associados and tem_icones_aria_hidden and feedback_tem_aria_live
          and abas_tem_role_tabpanel and not erros)
    registrar("Estrutura básica de acessibilidade presente (labels, aria-hidden, aria-live, tabpanel)", ok,
               f"labels_associados={labels_associados}, icones_aria_hidden={tem_icones_aria_hidden}, "
               f"feedback_aria_live={feedback_tem_aria_live}, abas_tabpanel={abas_tem_role_tabpanel}")
    context.close()


def test_relatorios_da_noite(browser, base_url):
    """O painel 'Relatórios da Noite' calcula total de músicas, pessoas
    diferentes, nota média, apresentação mais bem avaliada e os rankings de
    músicas/cantores — tudo a partir do histórico e contagem já carregados,
    sem nenhuma consulta nova ao Firebase."""
    context, page, erros = nova_pagina(browser, base_url)

    # A identidade usada por contagemCantores agora é baseada em deviceId (ver
    # obterChaveIdentidade) — os registros do histórico precisam de "id" e
    # "deviceId" pra bater com as chaves de contagemCantores abaixo.
    page.evaluate("""
        historico = [
            {id: 1, deviceId: 'dev-carlos', nome: 'Carlos', mesa: '5', musica: 'Evidencias', artista: 'X', horario: '20:00', mediaAvaliacao: 4.5, totalVotos: 4},
            {id: 2, deviceId: 'dev-maria', nome: 'Maria', mesa: '3', musica: 'Numb', artista: 'Linkin Park', horario: '20:15', mediaAvaliacao: 5.0, totalVotos: 6},
            {id: 3, deviceId: 'dev-carlos', nome: 'Carlos', mesa: '5', musica: 'Evidencias', artista: 'X', horario: '20:30', mediaAvaliacao: 3.0, totalVotos: 2},
            {id: 4, deviceId: 'dev-joao', nome: 'Joao', mesa: '8', musica: 'Numb', artista: 'Linkin Park', horario: '20:45', mediaAvaliacao: null, totalVotos: 0}
        ];
        contagemCantores = {'device:dev-carlos': 2, 'device:dev-maria': 1, 'device:dev-joao': 1};
        atualizarUI();
    """)
    page.wait_for_timeout(200)

    vazio_escondido = page.evaluate("document.getElementById('relatorio-vazio').classList.contains('hidden')")
    total_musicas = page.evaluate("document.getElementById('rel-total-musicas').innerText")
    total_pessoas = page.evaluate("document.getElementById('rel-total-pessoas').innerText")
    media_geral = page.evaluate("document.getElementById('rel-media-geral').innerText")
    melhor_avaliada = page.evaluate("document.getElementById('rel-melhor-avaliada-texto').innerText")
    ranking_cantores = page.evaluate("document.getElementById('rel-ranking-cantores').innerText")

    # Reset -> relatório volta pro estado vazio
    page.evaluate("historico = []; atualizarUI();")
    page.wait_for_timeout(150)
    vazio_apos_reset = page.evaluate("!document.getElementById('relatorio-vazio').classList.contains('hidden')")

    ok = (vazio_escondido and total_musicas == "4" and total_pessoas == "3"
          and media_geral == "4.2" and "Maria" in melhor_avaliada and "Numb" in melhor_avaliada
          and "Carlos" in ranking_cantores.split("\n")[0] and vazio_apos_reset and not erros)
    registrar("Relatórios da Noite calcula totais, média e rankings corretamente", ok,
               f"total_musicas={total_musicas}, total_pessoas={total_pessoas}, media_geral={media_geral}, "
               f"melhor_avaliada='{melhor_avaliada}', 1o_ranking_cantores='{ranking_cantores.splitlines()[0] if ranking_cantores else ''}', "
               f"volta_vazio_apos_reset={vazio_apos_reset}")
    context.close()


def test_ranking_cantores_mostra_nome_de_apresentacao_nao_finalizada(browser, base_url):
    """contagemCantores é incrementado quando a apresentação COMEÇA
    (acaoProximo), mas um registro só entra em "historico" quando ela é
    FINALIZADA (acaoFinalizarApresentacao). Se alguém começou a cantar mas a
    apresentação nunca foi finalizada (ainda em andamento, ou abandonada), o
    nome não existia em historico e o ranking mostrava a chave crua tipo
    "device:56046966-...". atualizarRelatorios() agora também busca o nome
    em `fila` e em `apresentacaoAtual`, não só em `historico`."""
    context, page, erros = nova_pagina(browser, base_url)

    page.evaluate("""
        historico = [
            {id: 1, deviceId: 'dev-carlos', nome: 'Carlos', mesa: '5', musica: 'Evidencias', artista: 'X', horario: '20:00', mediaAvaliacao: 4.5, totalVotos: 4}
        ];
        // dev-maria: apresentação em andamento (apresentacaoAtual), nunca finalizada.
        apresentacaoAtual = {id: 2, deviceId: 'dev-maria', nome: 'Maria', mesa: '3', musica: 'Numb', artista: 'Linkin Park'};
        // dev-joao: já cantou uma vez (registrado em historico) e pediu de novo,
        // o novo pedido ainda está só na fila, não finalizado.
        fila = [
            {id: 3, deviceId: 'dev-joao', nome: 'Joao', mesa: '8', musica: 'Garota de Ipanema', artista: 'Y', timestamp: Date.now()}
        ];
        contagemCantores = {'device:dev-carlos': 1, 'device:dev-maria': 1, 'device:dev-joao': 1};
        atualizarUI();
    """)
    page.wait_for_timeout(200)

    ranking_cantores = page.evaluate("document.getElementById('rel-ranking-cantores').innerText")

    ok = ("Carlos" in ranking_cantores and "Maria" in ranking_cantores and "Joao" in ranking_cantores
          and "device:" not in ranking_cantores and not erros)
    registrar("Ranking de cantores mostra o nome mesmo sem apresentação finalizada (fila/apresentacaoAtual)", ok,
               f"ranking_cantores={ranking_cantores!r}, erros JS={erros}")
    context.close()


def test_horario_de_pico(browser, base_url):
    """O gráfico 'Pedidos por horário' agrupa os pedidos pela hora do timestamp
    e identifica corretamente qual horário teve mais movimento."""
    context, page, erros = nova_pagina(browser, base_url)

    def ts_na_hora(hora, minuto=0):
        agora = datetime.now()
        return int(agora.replace(hour=hora, minute=minuto, second=0, microsecond=0).timestamp() * 1000)

    # 20h: 2 pedidos | 21h: 5 pedidos (deve ser o pico) | 22h: 3 pedidos
    horarios = [(20, 10), (20, 20), (21, 0), (21, 15), (21, 30), (21, 45), (21, 50), (22, 0), (22, 10), (22, 20)]
    itens = ", ".join(
        f'{{nome: "P{i}", mesa: null, musica: "M{i}", artista: "X", horario: "x", '
        f'timestamp: {ts_na_hora(h, m)}, mediaAvaliacao: null, totalVotos: 0}}'
        for i, (h, m) in enumerate(horarios)
    )
    page.evaluate(f"""
        historico = [{itens}];
        contagemCantores = {{}};
        atualizarUI();
    """)
    page.wait_for_timeout(200)

    pico_visivel = page.evaluate("!document.getElementById('rel-pico-card').classList.contains('hidden')")
    texto_pico = page.evaluate("document.getElementById('rel-pico-texto').innerText")
    qtd_barras = page.evaluate("document.querySelectorAll('#rel-grafico-horas > div').length")

    ok = (pico_visivel and "21h" in texto_pico and "5 pedidos" in texto_pico and qtd_barras == 3 and not erros)
    registrar("Horário de pico identifica corretamente a hora mais movimentada", ok,
               f"pico_visivel={pico_visivel}, texto_pico='{texto_pico}', qtd_barras={qtd_barras}")
    context.close()


def test_catalogo_pagina_separada_lista_por_letra(browser, base_url):
    """O catálogo agora é uma página separada (catalogo.html), em formato de
    lista alfabética tipo agenda telefônica — agrupada por letra, com um
    índice A-Z fixo no topo pra pular direto pra uma letra."""
    context = browser.new_context(viewport={"width": 480, "height": 900})
    page = context.new_page()
    erros = []
    page.on("pageerror", lambda exc: erros.append(str(exc)))
    page.goto(f"{base_url}/catalogo.html?bar=citta")
    aguardar_tailwind(page)
    page.wait_for_timeout(300)

    # Tem pelo menos uma seção por letra, com cabeçalho e itens dentro
    qtd_cabecalhos = page.evaluate("document.querySelectorAll('.cabecalho-letra').length")
    tem_evidencias = page.evaluate("document.getElementById('lista-catalogo').innerText.includes('Evidências')")

    # "Evidências" começa com E — deve estar dentro da seção da letra E
    dentro_da_secao_e = page.evaluate("""
        (function() {
            const secaoE = document.getElementById('letra-E');
            if (!secaoE) return false;
            // A música fica numa <div> irmã logo depois do cabeçalho da letra
            const container = secaoE.parentElement;
            return container.innerText.includes('Evidências');
        })()
    """)

    # Índice A-Z existe, com letras que têm música clicáveis (viram link <a>)
    link_letra_e = page.evaluate("document.querySelector('#indice-letras a[href=\"#letra-E\"]') !== null")

    ok = (qtd_cabecalhos > 1 and tem_evidencias and dentro_da_secao_e and link_letra_e and not erros)
    registrar("Catálogo em página separada: lista agrupada por letra tipo agenda telefônica", ok,
               f"qtd_cabecalhos={qtd_cabecalhos}, tem_evidencias={tem_evidencias}, "
               f"dentro_da_secao_e={dentro_da_secao_e}, link_indice_e={link_letra_e}")
    context.close()


def test_catalogo_escolher_musica_preenche_index(browser, base_url):
    """Clicar numa música no catálogo leva de volta pra tela de pedidos já com
    o formulário preenchido (música + artista), via parâmetros na URL."""
    context = browser.new_context(viewport={"width": 480, "height": 900})
    page = context.new_page()
    erros = []
    page.on("pageerror", lambda exc: erros.append(str(exc)))
    page.goto(f"{base_url}/catalogo.html?bar=citta")
    aguardar_tailwind(page)
    page.wait_for_timeout(300)

    # Acha o índice do item "Numb" no catálogo e "clica" nele via JS. Usa
    # expect_navigation() em vez de só um wait_for_timeout fixo — escolherMusica()
    # navega via "window.location.href", e sem esperar a navegação de verdade
    # (page.evaluate retorna antes dela terminar) esse teste ficava instável em
    # ambientes mais lentos/sem internet, tentando ler o formulário no meio da
    # troca de página.
    with page.expect_navigation(timeout=30000):
        page.evaluate("""
            const indice = CATALOGO_MUSICAS.findIndex(m => m.musica === 'Numb');
            escolherMusica(indice);
        """)
    page.wait_for_load_state("domcontentloaded")
    aguardar_tailwind(page)
    page.wait_for_timeout(200)

    foi_para_index = "index.html" in page.url
    musica_preenchida = page.evaluate("document.getElementById('input-musica').value")
    artista_preenchido = page.evaluate("document.getElementById('input-artista').value")
    url_limpou_parametros = "musica=" not in page.url  # replaceState deve ter limpado

    ok = (foi_para_index and musica_preenchida == "Numb" and artista_preenchido == "Linkin Park"
          and url_limpou_parametros and not erros)
    registrar("Escolher música no catálogo preenche o formulário na volta", ok,
               f"foi_para_index={foi_para_index}, musica='{musica_preenchida}', "
               f"artista='{artista_preenchido}', url_limpa={url_limpou_parametros}, url_final={page.url}")
    context.close()


def test_voto_que_falha_avisa_a_pessoa(browser, base_url):
    """Se um voto não conseguir salvar no Firebase, a pessoa precisa saber —
    senão ela acha que votou quando na verdade não votou. O aviso deve sumir
    sozinho assim que a tela atualizar de novo normalmente."""
    context, page, erros = nova_pagina(browser, base_url)

    page.evaluate("""
        fila.push({id: 1, nome: 'Carlos', mesa: null, musica: 'M', artista: 'X', timestamp: Date.now(), vezesCantadas: 0, youtubeUrl: null});
        acaoProximo(1);
    """)
    page.wait_for_timeout(100)

    # Mock assíncrono (como o Firebase real) que sempre falha ao salvar
    page.evaluate("""
        useFirebase = true;
        db = { ref: () => ({ set: (valor, cb) => setTimeout(() => cb({code: 'NETWORK_ERROR', message: 'falhou'}), 50) }) };
    """)
    page.evaluate("avaliarApresentacao(5)")
    page.wait_for_timeout(200)
    texto_erro = page.evaluate("document.getElementById('avaliar-status').innerText")
    tem_estilo_erro = page.evaluate("document.getElementById('avaliar-status').classList.contains('text-red-600')")

    page.evaluate("atualizarUI()")
    page.wait_for_timeout(100)
    texto_normal = page.evaluate("document.getElementById('avaliar-status').innerText")
    ainda_tem_erro = page.evaluate("document.getElementById('avaliar-status').classList.contains('text-red-600')")

    ok = ("não foi salvo" in texto_erro and tem_estilo_erro
          and "não foi salvo" not in texto_normal and not ainda_tem_erro and not erros)
    registrar("Voto que falha ao salvar avisa a pessoa, e o aviso some no próximo ciclo normal", ok,
               f"texto_erro='{texto_erro}', tem_estilo_erro={tem_estilo_erro}, "
               f"texto_normal='{texto_normal}', ainda_tem_erro={ainda_tem_erro}")
    context.close()


def test_display_mostra_status_de_conexao_honesto(browser, base_url):
    """O indicador '🔥 Conectado ao Firebase' do telão não pode ficar fixo —
    precisa realmente refletir se a conexão caiu, senão a equipe do bar não
    tem como saber que a tela parou de atualizar."""
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    erros = []
    page.on("pageerror", lambda exc: erros.append(str(exc)))
    page.goto(f"{base_url}/display.html?bar=citta")
    aguardar_tailwind(page)
    page.wait_for_timeout(300)

    page.evaluate("atualizarStatusFirebaseDisplay(false)")
    page.wait_for_timeout(100)
    texto_desconectado = page.evaluate("document.getElementById('status-text').innerText")
    fundo_vermelho = page.evaluate("document.getElementById('firebase-status').style.background")

    page.evaluate("atualizarStatusFirebaseDisplay(true)")
    page.wait_for_timeout(100)
    texto_reconectado = page.evaluate("document.getElementById('status-text').innerText")

    ok = ("Sem conexão" in texto_desconectado and "220, 38, 38" in fundo_vermelho
          and "Conectado" in texto_reconectado and not erros)
    registrar("Telão mostra status de conexão honesto (não fica fixo em 'Conectado')", ok,
               f"texto_desconectado='{texto_desconectado}', fundo='{fundo_vermelho}', "
               f"texto_reconectado='{texto_reconectado}'")
    context.close()


def test_historico_permanente_limita_a_um_ano(browser, base_url):
    """O 'Histórico Permanente' só considera os últimos 12 meses (registros mais
    antigos ficam de fora das estatísticas) e limpa sozinho, no banco, qualquer
    registro que já passou dessa janela — evita crescer pra sempre."""
    context, page, erros = nova_pagina(browser, base_url)

    page.evaluate("""
        window.__removidos = [];
        useFirebase = true;
        const agora = Date.now();
        const umAno = 365 * 24 * 60 * 60 * 1000;

        const banco = {
            'recente1': {nome: 'Carlos', mesa: '5', musica: 'Evidencias', artista: 'X', timestamp: agora - (10 * 24*60*60*1000), horario: 'x', mediaAvaliacao: 4, totalVotos: 2},
            'recente2': {nome: 'Maria', mesa: '3', musica: 'Numb', artista: 'Linkin Park', timestamp: agora - (100 * 24*60*60*1000), horario: 'x', mediaAvaliacao: 5, totalVotos: 3},
            'antigo1': {nome: 'Joao', mesa: '8', musica: 'Antiga', artista: 'Y', timestamp: agora - umAno - (10 * 24*60*60*1000), horario: 'x', mediaAvaliacao: 3, totalVotos: 1},
            'antigo2': {nome: 'Ana', mesa: '2', musica: 'MuitoAntiga', artista: 'Z', timestamp: agora - umAno - (400 * 24*60*60*1000), horario: 'x', mediaAvaliacao: 2, totalVotos: 1}
        };

        function filtrarPorTimestamp(corte, pegarMaiorOuIgual) {
            const resultado = {};
            Object.keys(banco).forEach(chave => {
                const ts = banco[chave].timestamp;
                if (pegarMaiorOuIgual ? ts >= corte : ts <= corte) resultado[chave] = banco[chave];
            });
            return resultado;
        }

        db = {
            ref: function(path) {
                return {
                    orderByChild: function(campo) {
                        return {
                            startAt: function(corte) {
                                return { once: function() { return Promise.resolve({ val: () => filtrarPorTimestamp(corte, true) }); } };
                            },
                            endAt: function(corte) {
                                return { once: function() { return Promise.resolve({ val: () => filtrarPorTimestamp(corte, false) }); } };
                            }
                        };
                    },
                    update: function(atualizacoes) {
                        Object.keys(atualizacoes).forEach(chave => {
                            if (atualizacoes[chave] === null) window.__removidos.push(chave);
                        });
                        return Promise.resolve();
                    }
                };
            }
        };

        carregarEstatisticasPermanentes();
    """)
    page.wait_for_timeout(500)

    total_musicas = page.evaluate("document.getElementById('perm-total-musicas').innerText")
    removidos = page.evaluate("window.__removidos")

    ok = (total_musicas == "2" and set(removidos) == {"antigo1", "antigo2"} and not erros)
    registrar("Histórico permanente limita a 1 ano e limpa registros antigos sozinho", ok,
               f"total_musicas_exibido={total_musicas} (esperado 2), removidos={removidos} (esperado antigo1+antigo2)")
    context.close()


def _contraste(cor1, cor2):
    """Calcula a taxa de contraste entre duas cores hex, seguindo a fórmula do
    WCAG. 4.5 é o mínimo recomendado pra texto normal ler bem."""
    def luminancia(hex_cor):
        hex_cor = hex_cor.lstrip("#")
        r, g, b = [int(hex_cor[i:i+2], 16) / 255 for i in (0, 2, 4)]
        def ajustar(c):
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        r, g, b = ajustar(r), ajustar(g), ajustar(b)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    l1, l2 = luminancia(cor1), luminancia(cor2)
    claro, escuro = max(l1, l2), min(l1, l2)
    return (claro + 0.05) / (escuro + 0.05)


def _rgb_para_hex(rgb_css):
    """Converte 'rgb(134, 239, 172)' pra '#86efac'."""
    numeros = [int(n) for n in rgb_css.strip("rgb()").split(",")]
    return "#{:02x}{:02x}{:02x}".format(*numeros)


def test_contraste_de_cores_no_modo_escuro(browser, base_url):
    """Vários textos coloridos (verde, amarelo, laranja, vermelho, azul) tinham
    o FUNDO escurecido no modo escuro, mas o texto continuava com a cor clara
    original — as duas cores escuras ficavam quase impossíveis de ler. Confirma
    que agora todas têm contraste acima do mínimo recomendado (4.5)."""
    context, page, erros = nova_pagina(browser, base_url)
    page.evaluate("document.body.classList.add('modo-escuro')")

    page.evaluate("""
        fila = [{id: 1, nome: 'Teste', mesa: null, musica: 'Musica', artista: 'X', timestamp: Date.now(), vezesCantadas: 0, youtubeUrl: null}];
        registrarMeuPedido(1);
        apresentacaoAtual = {id: 1, nome: 'Teste', musica: 'Musica', artista: 'X', avaliacoes: {a:5,b:5}};
        atualizarUI();
    """)
    page.wait_for_timeout(200)

    pares = page.evaluate("""
        (function() {
            function corDe(seletor, propriedade) {
                const el = document.querySelector(seletor);
                return el ? getComputedStyle(el)[propriedade] : null;
            }
            return {
                verde: [corDe('.text-green-700', 'color'), corDe('.bg-green-50', 'backgroundColor')],
                amarelo: [corDe('.text-yellow-600', 'color'), corDe('.bg-yellow-50', 'backgroundColor')]
            };
        })()
    """)

    resultados = {}
    ok_geral = True
    for nome, (cor_texto, cor_fundo) in pares.items():
        if not cor_texto or not cor_fundo:
            continue
        contraste = _contraste(_rgb_para_hex(cor_texto), _rgb_para_hex(cor_fundo))
        resultados[nome] = round(contraste, 2)
        if contraste < 4.5:
            ok_geral = False

    ok = ok_geral and len(resultados) > 0 and not erros
    registrar("Contraste de texto colorido no modo escuro está acima do mínimo (4.5)", ok,
               f"contrastes={resultados}")
    context.close()


def test_campos_do_pedido_batem_com_regras_do_firebase(browser, base_url):
    """As regras reais do Firebase (database.rules.json) travam a fila com uma
    whitelist de campos ($other: false) — se o JS gravar um campo que as regras
    não conhecem, a transação inteira é rejeitada com permission_denied, e nada
    disso aparece nos outros testes (que rodam em modo localStorage, sem as
    regras reais). Já aconteceu de verdade com o campo "youtubeUrl". Esse teste
    não abre browser: só compara estaticamente os campos que montarNovoPedido()
    grava com o schema declarado em fila/$index nas regras."""
    conteudo = CAMINHO_INDEX.read_text(encoding="utf-8")
    regras = json.loads(CAMINHO_REGRAS.read_text(encoding="utf-8"))

    match_funcao = re.search(
        r"function montarNovoPedido\(\).*?return \{(.*?)\};",
        conteudo, re.DOTALL
    )
    linhas_sem_comentario = "\n".join(
        linha for linha in match_funcao.group(1).splitlines()
        if not linha.strip().startswith("//")
    )
    campos_do_pedido = set(re.findall(r"^\s*(\w+):", linhas_sem_comentario, re.MULTILINE))

    schema_fila = regras["rules"]["bares"]["$barId"]["karaoke"]["fila"]["$index"]
    campos_permitidos = {chave for chave in schema_fila.keys() if not chave.startswith(("$", "."))}

    campos_nao_permitidos = campos_do_pedido - campos_permitidos

    ok = bool(match_funcao) and len(campos_do_pedido) > 0 and not campos_nao_permitidos
    registrar("Campos gravados em /fila batem com a whitelist de database.rules.json", ok,
              f"gravados={sorted(campos_do_pedido)}, "
              f"permitidos={sorted(campos_permitidos)}, "
              f"fora_da_whitelist={sorted(campos_nao_permitidos)}")


# ---------------------------------------------------------------------------

def main():
    global ARQUIVO_INDEX, CAMINHO_INDEX, CAMINHO_REGRAS

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arquivo", default=None,
                         help="Caminho pro index.html a testar (padrão: o que está na mesma pasta que este script)")
    args = parser.parse_args()

    caminho_index = Path(args.arquivo) if args.arquivo else (Path(__file__).parent.parent / "index.html")
    if not caminho_index.exists():
        print(f"❌ Não encontrei o arquivo: {caminho_index}")
        sys.exit(2)

    pasta = caminho_index.parent.resolve()
    ARQUIVO_INDEX = caminho_index.name
    CAMINHO_INDEX = caminho_index.resolve()
    CAMINHO_REGRAS = Path(__file__).parent.parent / "database.rules.json"

    print(f"Testando: {caminho_index}")
    print(f"Servindo {pasta} por HTTP local (não mais file://, pra ficar mais fiel à produção)\n")

    with servidor_http(pasta) as base_url:
        with sync_playwright() as p:
            browser = p.chromium.launch()

            test_sem_bar_mostra_erro(browser, base_url)
            test_bar_valido_carrega_sem_erros(browser, base_url)
            test_isolamento_entre_bares(browser, base_url)
            test_prioridade_por_nome_e_mesa(browser, base_url)
            test_pessoas_diferentes_mesas_diferentes_nao_se_confundem(browser, base_url)
            test_voto_nao_reconstroi_a_tela(browser, base_url)
            test_admin_exige_login(browser, base_url)
            test_youtube_preenche_musica_e_libera_artista(browser, base_url)
            test_media_de_avaliacoes(browser, base_url)
            test_espera_longa_faz_pessoa_furar_a_fila(browser, base_url)
            test_fila_evita_pedidos_consecutivos_da_mesma_pessoa(browser, base_url)
            test_fila_mantem_sequencia_quando_so_sobra_a_mesma_pessoa(browser, base_url)
            test_fila_nao_fura_prioridade_pra_desfazer_sequencia(browser, base_url)
            test_teto_de_espera_maxima_fura_mesmo_com_vezes_cantadas_alto(browser, base_url)
            test_teto_de_espera_maxima_empate_por_ordem_de_chegada(browser, base_url)
            test_deviceid_impede_burlar_cooldown_trocando_nome(browser, base_url)
            test_dois_pedidos_simultaneos_nao_se_perdem(browser, base_url)
            test_limite_de_creditos_bloqueia_sexto_pedido_com_fila_cheia(browser, base_url)
            test_limite_de_creditos_libera_com_fila_curta(browser, base_url)
            test_cancelamento_admin_libera_credito_imediatamente(browser, base_url)
            test_indicador_creditos_nao_aparece_com_poucos_pedidos(browser, base_url)
            test_indicador_creditos_aparece_no_limiar(browser, base_url)
            test_indicador_creditos_minutos_ate_liberar(browser, base_url)
            test_meus_pedidos_posicao_e_cancelamento(browser, base_url)
            test_historico_paginado_no_cliente(browser, base_url)
            test_aviso_iphone_aparece_so_no_iphone(browser, base_url)
            test_aviso_de_conexao_perdida_existe(browser, base_url)
            test_modo_escuro_alterna_e_persiste(browser, base_url)
            test_protecao_contra_xss(browser, base_url)
            test_listeners_separados_por_pedaco(browser, base_url)
            test_historico_completo_sob_demanda(browser, base_url)
            test_validacao_de_formulario(browser, base_url)
            test_link_colado_no_campo_musica_e_bloqueado(browser, base_url)
            test_acessibilidade_basica(browser, base_url)
            test_relatorios_da_noite(browser, base_url)
            test_ranking_cantores_mostra_nome_de_apresentacao_nao_finalizada(browser, base_url)
            test_horario_de_pico(browser, base_url)
            test_catalogo_pagina_separada_lista_por_letra(browser, base_url)
            test_catalogo_escolher_musica_preenche_index(browser, base_url)
            test_voto_que_falha_avisa_a_pessoa(browser, base_url)
            test_display_mostra_status_de_conexao_honesto(browser, base_url)
            test_historico_permanente_limita_a_um_ano(browser, base_url)
            test_contraste_de_cores_no_modo_escuro(browser, base_url)
            test_campos_do_pedido_batem_com_regras_do_firebase(browser, base_url)

            browser.close()

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
