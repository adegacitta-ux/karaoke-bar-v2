const { onCall, onRequest, HttpsError } = require("firebase-functions/v2/https");
const logger = require("firebase-functions/logger");
const admin = require("firebase-admin");
const { criarPagamentoPix, buscarPagamento, MINUTOS_ATE_EXPIRAR } = require("./mercadoPago");
const { buscarAccessTokenDoBar } = require("./secretManager");

if (admin.apps.length === 0) admin.initializeApp();
const db = admin.database();

// Só letras, números e hífen -- mesma validação de BAR_ID usada no front-end
// (ver obterBarId em index.html). Trata barId como dado NÃO confiável (vem do
// cliente ou da query string do webhook), então valida de novo aqui: sem
// isso, alguém poderia mandar um barId tipo "../outro-bar" tentando montar um
// caminho de leitura pra outro bar.
function barIdValido(barId) {
  return typeof barId === "string" && /^[a-z0-9-]{1,64}$/.test(barId);
}

async function buscarConfigDoBar(barId) {
  const snapshot = await db.ref(`bares/${barId}/config`).once("value");
  return snapshot.val() || {};
}

// --- criarCobrancaPix ------------------------------------------------------
//
// Lógica de verdade, separada do wrapper onCall() só pra poder ser testada
// direto pelos testes Jest (ver functions/index.test.js) sem precisar simular
// toda a infraestrutura de Callable Function do Firebase.
async function criarCobrancaPixHandler({ barId, pedidoId, uid }) {
  if (!barIdValido(barId)) {
    throw new HttpsError("invalid-argument", "barId inválido.");
  }
  if (typeof pedidoId !== "string" && typeof pedidoId !== "number") {
    throw new HttpsError("invalid-argument", "pedidoId inválido.");
  }
  const pedidoIdTexto = String(pedidoId);

  const config = await buscarConfigDoBar(barId);

  // O preço NUNCA vem do cliente -- é sempre lido daqui, do config público do
  // bar, e é esse valor (não nenhum outro) que vira a cobrança PIX de verdade.
  const preco = Number(config.precoFurarFila);
  if (!Number.isFinite(preco) || preco <= 0) {
    throw new HttpsError(
      "failed-precondition",
      "Esse bar ainda não configurou o valor de furar a fila."
    );
  }

  // Confere que o pedido realmente existe, ainda está pendente na fila (não
  // chamado/finalizado/cancelado) E pertence a quem está chamando -- sem essa
  // segunda parte, alguém que descobrisse o ID do pedido de outra pessoa
  // poderia pagar (e furar a fila) em nome dela. Devolve o mesmo erro genérico
  // nos dois casos (pedido não existe OU não pertence a esse uid) pra não dar
  // pista de qual dos dois é verdade pra quem está tentando adivinhar IDs.
  const filaSnapshot = await db.ref(`bares/${barId}/karaoke/fila`).once("value");
  const fila = filaSnapshot.val() || [];
  const pedido = fila.find((p) => String(p.id) === pedidoIdTexto);
  if (!pedido || pedido.criadoPorUid !== uid) {
    throw new HttpsError(
      "permission-denied",
      "Esse pedido não existe, já saiu da fila, ou não pertence a você."
    );
  }

  const refReserva = db.ref(`bares/${barId}/karaoke/pagamentosPixPrivado/${pedidoIdTexto}`);

  // Trava atômica contra corrida de clique duplo (duas abas, ou um duplo-tap na
  // tela do celular): a transação garante que só UMA chamada consegue gravar o
  // registro "reservando" -- a outra recebe de volta o que a primeira já
  // gravou, sem sobrescrever nada. Isso é o mesmo padrão já usado em
  // adicionarPedido() no index.html pra evitar corrida de gravação quando duas
  // pessoas entram na fila ao mesmo tempo.
  //
  // IMPORTANTE: a chamada de rede pro Mercado Pago (efeito colateral real, que
  // cria uma cobrança de verdade) fica DE FORA desse callback -- transações do
  // Firebase podem reexecutar o callback mais de uma vez internamente quando
  // detectam disputa de escrita, e se a chamada à API estivesse aqui dentro
  // ela poderia disparar mais de uma vez sem querer.
  const resultadoTransacao = await refReserva.transaction((atual) => {
    if (atual) return; // já existe (reservando, aguardando pagamento ou aprovado) -- aborta
    return {
      status: "reservando",
      criadoPorUid: uid,
      valorPago: preco,
      metodoPagamento: "pix",
      criadoEm: Date.now(),
    };
  });

  if (!resultadoTransacao.committed) {
    const atual = resultadoTransacao.snapshot.val();

    if (atual && atual.status === "aprovado") {
      throw new HttpsError("failed-precondition", "Esse pedido já pagou pra furar a fila.");
    }

    if (atual && atual.status === "aguardando_pagamento") {
      if (Date.now() < atual.dataExpiracaoMs) {
        // Cobrança anterior ainda válida -- devolve a MESMA em vez de criar
        // outra (clique duplo no botão "Pagar com PIX" continua mostrando o
        // mesmo QR Code, não gera uma segunda cobrança).
        return {
          paymentId: atual.paymentId,
          qrCodeBase64: atual.qrCodeBase64,
          copiaECola: atual.copiaECola,
          valorEmReais: atual.valorPago,
          dataExpiracaoMs: atual.dataExpiracaoMs,
        };
      }
      // Expirou -- libera a reserva antiga pra essa chamada (ou a próxima)
      // poder gerar uma cobrança nova.
      await refReserva.remove();
      throw new HttpsError("aborted", "A cobrança anterior expirou. Tente de novo.");
    }

    // status "reservando" de outra chamada concorrente, na janela de poucos
    // milissegundos entre reservar e gravar o resultado -- pede pra tentar de
    // novo em vez de travar esperando.
    throw new HttpsError("aborted", "Já existe uma cobrança sendo gerada pra esse pedido. Tente de novo em instantes.");
  }

  // Ganhou a corrida -- essa é a única chamada que efetivamente cria a
  // cobrança no Mercado Pago, fora da transação (ver comentário acima).
  const accessToken = await buscarAccessTokenDoBar(barId);
  if (!accessToken) {
    await refReserva.remove(); // libera a reserva -- não dá pra cobrar sem token configurado
    throw new HttpsError(
      "failed-precondition",
      "Esse bar ainda não está configurado pra receber pagamentos PIX."
    );
  }

  const baseUrl = process.env.FUNCTION_URL_BASE || `https://${process.env.GCLOUD_PROJECT}.cloudfunctions.net`;
  // O barId vai na query string da notification_url -- é assim que o webhook,
  // que só recebe o ID do pagamento (sem mais nenhum contexto), descobre de
  // qual bar buscar o Access Token. O external_reference (barId:pedidoId, ver
  // mercadoPago.js) é a confirmação independente disso.
  const notificationUrl = `${baseUrl}/webhookMercadoPago?barId=${encodeURIComponent(barId)}`;

  try {
    const pagamento = await criarPagamentoPix({
      accessToken,
      valorEmReais: preco,
      descricao: `Furar a fila - ${config.nome || barId}`,
      barId,
      pedidoId: pedidoIdTexto,
      notificationUrl,
      chaveIdempotencia: `furar-fila-${barId}-${pedidoIdTexto}`,
    });

    const dadosPix = pagamento?.point_of_interaction?.transaction_data;
    if (!dadosPix?.qr_code) {
      logger.error("Mercado Pago não devolveu QR code PIX", { barId, pedidoId, pagamento });
      await refReserva.remove();
      throw new HttpsError("internal", "O Mercado Pago não devolveu um QR Code PIX pra esse pagamento.");
    }

    const dataExpiracaoMs = Date.now() + MINUTOS_ATE_EXPIRAR * 60 * 1000;
    const resultado = {
      paymentId: pagamento.id,
      qrCodeBase64: dadosPix.qr_code_base64,
      copiaECola: dadosPix.qr_code,
      valorEmReais: preco,
      dataExpiracaoMs,
    };

    // Atualiza o MESMO registro já reservado -- é ele que o webhook vai
    // conferir (paymentId, valor e uid) antes de liberar a prioridade.
    await refReserva.update({
      status: "aguardando_pagamento",
      paymentId: resultado.paymentId,
      qrCodeBase64: resultado.qrCodeBase64,
      copiaECola: resultado.copiaECola,
      dataExpiracaoMs,
    });

    return resultado;
  } catch (erro) {
    logger.error("Erro ao criar cobrança PIX", { barId, pedidoId, mensagem: erro.message });
    await refReserva.remove(); // libera a trava pra permitir uma nova tentativa
    if (erro instanceof HttpsError) throw erro;
    throw new HttpsError("internal", "Não foi possível criar a cobrança PIX agora. Tente de novo em instantes.");
  }
}

// HTTPS Callable chamado pelo botão "Furar a fila (PIX)" no index.html. Não dá
// pra criar a cobrança direto do navegador porque isso exigiria colocar o
// Access Token do Mercado Pago (uma credencial que MOVIMENTA DINHEIRO da conta
// do bar) no JavaScript público -- qualquer pessoa poderia abrir o DevTools,
// pegar o token e fazer cobranças em nome do bar. Por isso essa etapa só
// existe aqui, do lado do servidor, onde o token nunca é exposto.
exports.criarCobrancaPix = onCall(async (request) => {
  if (!request.auth) {
    // Todo visitante (mesmo sem logar) já recebe uma sessão anônima do
    // Firebase Auth automaticamente (ver signInAnonymously() em index.html) --
    // chegar aqui sem auth normalmente só acontece se alguém chamar a function
    // direto, fora do app.
    throw new HttpsError("unauthenticated", "É preciso estar autenticado (mesmo que anonimamente).");
  }
  const { barId, pedidoId } = request.data || {};
  return criarCobrancaPixHandler({ barId, pedidoId, uid: request.auth.uid });
});

// --- webhookMercadoPago -----------------------------------------------------
//
// Lógica de verdade, separada do wrapper onRequest() só pra poder ser testada
// direto pelos testes Jest -- devolve {status, corpo} em vez de escrever numa
// Response do Express, que é mais chato de simular num teste unitário.
async function webhookHandler({ barId, paymentId }) {
  if (!barIdValido(barId)) {
    logger.warn("Webhook recebido com barId ausente/inválido", { barId });
    return { status: 400, corpo: "barId inválido" };
  }
  if (!paymentId) {
    // Notificação de outro tipo de evento (ex: teste de configuração) -- não é
    // erro, só não tem nada a fazer aqui.
    return { status: 200, corpo: "ignorado (sem id de pagamento)" };
  }

  const accessToken = await buscarAccessTokenDoBar(barId);
  if (!accessToken) {
    logger.error("Webhook recebido pra bar sem Access Token configurado", { barId });
    return { status: 200, corpo: "bar sem token configurado" }; // 200 pra MP não ficar reenviando pra sempre
  }

  // Essa é a checagem que importa de verdade: busca o pagamento DIRETO na API
  // do Mercado Pago, autenticado com o Access Token do bar -- nunca confiamos
  // no payload que chegou na notificação em si.
  const pagamento = await buscarPagamento({ accessToken, paymentId: String(paymentId) });

  if (pagamento.status !== "approved") {
    // Ainda pendente, rejeitado, cancelado etc -- não faz nada agora; se
    // aprovar depois, o Mercado Pago manda uma notificação nova.
    return { status: 200, corpo: `status atual: ${pagamento.status}` };
  }

  // external_reference vem no formato "barId:pedidoId" (ver criarPagamentoPix
  // em mercadoPago.js) -- é essa referência, não outro dado do payload, que diz
  // com certeza qual bar/pedido esse pagamento deve atualizar.
  const referencia = String(pagamento.external_reference || "");
  const separador = referencia.indexOf(":");
  const barIdDoPagamento = separador === -1 ? "" : referencia.slice(0, separador);
  const pedidoId = separador === -1 ? "" : referencia.slice(separador + 1);

  if (!pedidoId || barIdDoPagamento !== barId) {
    logger.error("external_reference não bate com o barId da notificação", {
      barIdDaQuery: barId, barIdDoPagamento, paymentId, referencia,
    });
    return { status: 200, corpo: "external_reference não confere" };
  }

  const refReserva = db.ref(`bares/${barId}/karaoke/pagamentosPixPrivado/${pedidoId}`);
  const reservaSnapshot = await refReserva.once("value");
  const reserva = reservaSnapshot.val();

  // Idempotência: o Mercado Pago pode reenviar a mesma notificação várias
  // vezes (comportamento esperado da plataforma). Se esse pagamento já foi
  // processado antes, devolve "ok" de novo sem repetir nenhum efeito.
  if (reserva && reserva.status === "aprovado" && String(reserva.paymentId) === String(pagamento.id)) {
    return { status: 200, corpo: "já processado" };
  }

  const CENTAVOS_DE_TOLERANCIA = 0.005; // arredondamento de ponto flutuante, não fraude
  if (
    !reserva ||
    reserva.status !== "aguardando_pagamento" ||
    String(reserva.paymentId) !== String(pagamento.id) ||
    Math.abs(Number(reserva.valorPago) - Number(pagamento.transaction_amount)) > CENTAVOS_DE_TOLERANCIA
  ) {
    logger.error("Pagamento aprovado não bate com a reserva registrada -- prioridade NÃO liberada", {
      barId, pedidoId, paymentId,
      valorEsperado: reserva?.valorPago,
      valorPago: pagamento.transaction_amount,
      paymentIdEsperado: reserva?.paymentId,
    });
    return { status: 200, corpo: "pagamento não confere com a cobrança registrada" };
  }

  // Confere se o pedido ainda está esperando na fila -- pode ser que o DJ já
  // tenha chamado esse pedido (foi pra apresentacaoAtual) ou a pessoa tenha
  // cancelado enquanto o pagamento ainda estava em trânsito. Nesse caso o
  // dinheiro foi recebido de verdade mas não gera mais benefício nenhum --
  // registra como pagamento órfão pra decisão manual do dono do bar (não
  // implementamos reembolso automático), em vez de tentar encaixar a
  // prioridade em outro lugar.
  const [filaSnapshot, apresentacaoSnapshot] = await Promise.all([
    db.ref(`bares/${barId}/karaoke/fila`).once("value"),
    db.ref(`bares/${barId}/karaoke/apresentacaoAtual`).once("value"),
  ]);
  const fila = filaSnapshot.val() || [];
  const apresentacaoAtual = apresentacaoSnapshot.val();
  const aindaNaFila = fila.some((p) => String(p.id) === pedidoId);

  if (!aindaNaFila) {
    const motivo = apresentacaoAtual && String(apresentacaoAtual.id) === pedidoId
      ? "PAGAMENTO_RECEBIDO_APOS_CHAMADA"
      : "PAGAMENTO_RECEBIDO_APOS_CANCELAMENTO";
    await Promise.all([
      db.ref(`bares/${barId}/karaoke/pagamentosOrfaos/${paymentId}`).set({
        pedidoId,
        valorPago: reserva.valorPago,
        criadoPorUid: reserva.criadoPorUid,
        motivo,
        timestamp: admin.database.ServerValue.TIMESTAMP,
      }),
      refReserva.update({ status: "orfao" }),
    ]);
    logger.warn("Pagamento aprovado, mas pedido já saiu da fila -- registrado como órfão", {
      barId, pedidoId, paymentId, motivo,
    });
    return { status: 200, corpo: "pagamento órfão registrado" };
  }

  // Grava em DOIS nós separados: um público mínimo (só o necessário pra
  // ordenar a fila e mostrar o selo pra todo mundo) e um privado (detalhe
  // financeiro, sem motivo pra qualquer visitante conseguir ler o paymentId ou
  // o valor pago por outra pessoa). Nunca dentro do array "fila" em si -- o
  // array é reordenado o tempo todo pelo cliente (ordenarFila()), o que
  // tornaria inviável proteger um campo dentro dele via regra .validate (a
  // posição de cada pedido muda a cada reordenação).
  await Promise.all([
    db.ref(`bares/${barId}/karaoke/pagamentosPixPublico/${pedidoId}`).set({
      prioridadePaga: true,
      timestampPago: admin.database.ServerValue.TIMESTAMP,
    }),
    refReserva.update({ status: "aprovado", processadoEm: admin.database.ServerValue.TIMESTAMP }),
  ]);

  logger.info("Prioridade paga confirmada", { barId, pedidoId, paymentId });
  return { status: 200, corpo: "ok" };
}

// Endpoint HTTP público que o Mercado Pago chama sozinho quando o status de um
// pagamento muda. NUNCA confiamos no que vem no corpo dessa notificação --
// qualquer pessoa na internet pode mandar um POST fingindo ser o Mercado Pago.
// A defesa de verdade (dentro de webhookHandler) consulta a API do Mercado
// Pago, confere o valor pago e o external_reference antes de liberar qualquer
// prioridade.
exports.webhookMercadoPago = onRequest(async (request, response) => {
  const barId = request.query.barId;
  // Mercado Pago manda o ID do pagamento de duas formas possíveis dependendo
  // do tipo de notificação (webhooks novos vs. IPN antigo) -- aceita as duas.
  const paymentId = request.body?.data?.id || request.query["data.id"] || request.query.id;

  try {
    const resultado = await webhookHandler({ barId, paymentId });
    response.status(resultado.status).send(resultado.corpo);
  } catch (erro) {
    logger.error("Erro ao processar webhook do Mercado Pago", { barId, paymentId, mensagem: erro.message });
    // 500 faz o Mercado Pago tentar reenviar essa notificação mais tarde --
    // correto aqui, já que o erro foi nosso (ex: falha temporária de rede),
    // não do pagamento em si.
    response.status(500).send("erro ao processar");
  }
});

module.exports.criarCobrancaPixHandler = criarCobrancaPixHandler;
module.exports.webhookHandler = webhookHandler;
module.exports.barIdValido = barIdValido;
