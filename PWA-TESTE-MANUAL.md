# Checklist manual de teste do PWA — Cantokê

Testes que a suíte Playwright (`tests/test_karaoke.py`) não cobre, porque
dependem de comportamento real do navegador mobile (instalação, modo
standalone, rede instável) e do Firebase real — não do modo localStorage
usado nos testes automatizados. Rodar isso num bar real antes de anunciar
o PWA pros clientes/DJs.

Testar pelo menos em: **Android + Chrome** e **iPhone + Safari**. Se possível,
testar também Android + Firefox, já que trata o manifest de forma diferente.

---

## 1. Prompt de instalação aparece

### Android Chrome
- [ ] Abrir `index.html?bar=SEU_BAR` num Android com Chrome, navegar um pouco
      (Chrome só oferece instalar depois de "engajamento" mínimo — não é
      instantâneo no primeiro load).
- [ ] Confirmar que aparece o banner/menu "Instalar app" (ou o ícone de
      instalação na barra de endereço).
- [ ] Tocar em instalar e confirmar que o ícone que aparece é o placeholder
      "CK" (ou a arte final, se já tiver sido trocada — ver `icons/README.md`).
- [ ] Confirmar que o nome do app na tela inicial é "Cantokê" (não
      "Karaokê Manager", que é só o `<title>` da aba do navegador).

### iOS Safari
- [ ] **Atenção:** iOS **não** mostra prompt automático de instalação. O
      caminho é manual: botão de compartilhar (□↑) → "Adicionar à Tela de
      Início". Confirmar que essa opção aparece normalmente.
- [ ] Confirmar que o ícone e o nome "Cantokê" aparecem corretos na tela de
      confirmação antes de adicionar.
- [ ] iOS ignora várias partes do `manifest.json` (cores, `display`) — quem
      manda ali são as tags `apple-mobile-web-app-*` que já estão no
      `<head>`. Confirmar visualmente que ficou coerente (sem barra de URL
      do Safari sobrando, cor da status bar não conflitando feio com o
      fundo escuro do app).

---

## 2. App abre em modo standalone

- [ ] Abrir o app pelo ícone instalado (não pelo navegador) em Android e
      confirmar que **não** aparece a barra de endereço/URL do Chrome.
- [ ] Mesmo teste no iOS: abrir pelo ícone da tela de início e confirmar
      que abre em tela cheia, sem a barra do Safari.
- [ ] Conferir que a cor da barra de status do celular combina com o tema
      escuro do app (`theme-color` / `apple-mobile-web-app-status-bar-style`),
      em vez de aparecer branca ou destoando.
- [ ] Fechar e reabrir o app pelo ícone algumas vezes — confirmar que
      sempre volta em modo standalone (não volta a abrir dentro do
      navegador depois de alguma atualização).

---

## 3. Fila em tempo real continua funcionando normalmente após instalado

Este é o ponto mais crítico — o objetivo do PWA é **não** quebrar o
comportamento ao vivo.

- [ ] Com o app instalado e aberto em standalone, pedir uma música na aba
      "Pedir Música" e confirmar que ela aparece na fila (Firebase
      Realtime Database) imediatamente.
- [ ] Com dois dispositivos (ex: celular instalado + notebook no
      `display.html` num navegador comum), confirmar que uma mudança de
      fila num aparece em tempo real no outro — sem precisar recarregar
      a página manualmente.
- [ ] Login do DJ (Firebase Auth) funcionando normalmente dentro do app
      instalado — sem loop de login, sem erro de permissão.
- [ ] Avaliar uma apresentação (avaliação/nota) e confirmar que grava e
      reflete em tempo real pra quem está vendo o `display.html`.
- [ ] Verificar no console do navegador (via `chrome://inspect` remoto no
      Android, ou Web Inspector remoto do Safari no iOS) que **não** há
      nenhum log do tipo "Service worker interceptou firebaseio.com" —
      só deve aparecer o log de registro do SW (`[Cantokê PWA] Service
      worker registrado: ...`) e nada de cache relacionado a dado ao vivo.
- [ ] Forçar uma atualização de arquivo (ex: mudar um texto qualquer no
      `index.html` e publicar) e confirmar que, ao reabrir o app
      instalado, a versão nova aparece em pouco tempo (graças ao
      `network-first` + `skipWaiting`/`clients.claim` do service worker) —
      **não** deve ficar preso mostrando a versão antiga por dias, que foi
      o tipo de problema que já causou deploy quebrado silenciosamente em
      mobile antes.

---

## 4. Comportamento quando o wifi cai no meio de uma sessão ao vivo

- [ ] Com o app aberto (fila carregada, tudo funcionando), desligar o
      wifi/dados do celular.
- [ ] Confirmar que a tela **não** trava numa "fila fantasma" — ou mostra
      claramente que perdeu conexão (ex: indicador de status do Firebase
      que já existe no app), ou visualmente para de atualizar sem parecer
      que ainda está em tempo real.
- [ ] Tentar pedir uma música com a rede caída: confirmar que o app avisa
      erro (não finge que o pedido foi salvo).
- [ ] Tentar **navegar para uma página nova** (ex: abrir `catalogo.html` a
      partir do app) com a rede caída: como é `network-first`, se não
      houver cache da página, deve aparecer a tela de "Sem conexão" do
      service worker (`service-worker.js`, função `networkFirst`) em vez
      de erro cru do navegador.
- [ ] Religar o wifi/dados e confirmar que a fila volta a sincronizar
      sozinha (o listener do Firebase reconecta) sem precisar fechar e
      reabrir o app.
- [ ] Repetir o teste alternando entre wifi e dados móveis (não só
      wifi caindo totalmente) — é o cenário mais comum num bar lotado.

---

## Limitações conhecidas (não são bugs, são o esperado)

- **iOS não oferece prompt automático de instalação** — depende do
  usuário saber usar "Adicionar à Tela de Início" manualmente. Não tem
  como contornar isso sem um app nativo de verdade.
- **iOS Safari pode limpar dados/cache do PWA** depois de ~7 dias sem uso
  (Intelligent Tracking Prevention / cache eviction). Isso é normal;
  o app deve continuar funcionando porque busca tudo de novo do Firebase
  ao reabrir, só perde o cache do *shell* estático.
- **Nada relacionado à fila, apresentação atual ou login deve nunca
  funcionar offline** — isso é intencional. Só a "casca" da interface
  (HTML/CSS/JS de UI) funciona sem internet; qualquer tela que dependa de
  dado ao vivo deve deixar claro que está sem conexão, nunca mostrar dado
  desatualizado como se fosse atual.
- **Atualizações do YouTube (busca de karaokê) e login do DJ nunca devem
  ficar em cache** — se algum resultado de busca ou tela de login parecer
  "grudado"/desatualizado depois de uma atualização de rede, é bug, não
  comportamento esperado do cache.
