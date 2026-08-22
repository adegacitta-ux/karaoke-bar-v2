// Chamadas HTTP pra API do Mercado Pago — nada aqui usa SDK deles (evita mais uma
// dependência pesada), é só fetch nativo do Node contra os endpoints REST.
// https://www.mercadopago.com.br/developers/pt/reference/payments/_payments/post

const MERCADO_PAGO_API = "https://api.mercadopago.com";
const MINUTOS_ATE_EXPIRAR = 10;

// Cria uma cobrança PIX de verdade na conta do Mercado Pago DESSE bar (cada bar
// tem seu próprio Access Token — ver secretManager.js). O "external_reference"
// leva "barId:pedidoId" — é assim que o webhook confirma que o pagamento
// aprovado realmente pertence ao bar/pedido que ele está processando, e não a
// outro (ver webhookMercadoPago em index.js).
//
// "date_of_expiration" limita o QR Code a alguns minutos: sem isso, uma pessoa
// que desiste de pagar deixaria uma cobrança pendente pra sempre, ocupando a
// reserva daquele pedido (ver a trava por transação em criarCobrancaPix) sem
// nunca liberar.
async function criarPagamentoPix({
  accessToken,
  valorEmReais,
  descricao,
  barId,
  pedidoId,
  notificationUrl,
  chaveIdempotencia,
}) {
  const expiraEm = new Date(Date.now() + MINUTOS_ATE_EXPIRAR * 60 * 1000);

  const resposta = await fetch(`${MERCADO_PAGO_API}/v1/payments`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
      // Evita cobrar duas vezes se a função for reexecutada (retry automático de
      // Cloud Functions) -- o Mercado Pago usa essa chave pra devolver o MESMO
      // pagamento em vez de criar um novo quando a chave já foi vista antes.
      // É fixa por pedido (não aleatória), recebida de fora porque também
      // participa da trava atômica do Firebase (ver criarCobrancaPix em index.js).
      "X-Idempotency-Key": chaveIdempotencia,
    },
    body: JSON.stringify({
      transaction_amount: valorEmReais,
      description: descricao,
      payment_method_id: "pix",
      // O Mercado Pago exige um e-mail de pagador, mas o app não coleta e-mail
      // de ninguém (seria fricção extra num pedido rápido de karaokê). Usamos
      // um e-mail sintético só pra satisfazer o schema da API — não é enviado
      // nem prometido como e-mail de contato de verdade.
      payer: { email: `pedido-${pedidoId}@furar-fila.invalid` },
      external_reference: `${barId}:${pedidoId}`,
      notification_url: notificationUrl,
      date_of_expiration: expiraEm.toISOString(),
    }),
  });

  const dados = await resposta.json();
  if (!resposta.ok) {
    const erro = new Error(
      `Mercado Pago recusou a criação do pagamento: ${resposta.status} ${JSON.stringify(dados)}`
    );
    erro.statusCode = resposta.status;
    throw erro;
  }
  return dados;
}

// Busca o pagamento DIRETO na API do Mercado Pago, usando o Access Token do
// bar — é essa chamada, e não o corpo da notificação do webhook, que decide se
// o pagamento realmente foi aprovado. Um webhook forjado (alguém mandando um
// POST fake pro nosso endpoint dizendo "status: approved") não engana isso,
// porque a resposta vem direto do servidor do Mercado Pago, autenticada com
// nosso próprio Access Token.
async function buscarPagamento({ accessToken, paymentId }) {
  const resposta = await fetch(`${MERCADO_PAGO_API}/v1/payments/${paymentId}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!resposta.ok) {
    const erro = new Error(
      `Não foi possível consultar o pagamento ${paymentId} no Mercado Pago: ${resposta.status}`
    );
    erro.statusCode = resposta.status;
    throw erro;
  }
  return resposta.json();
}

module.exports = { criarPagamentoPix, buscarPagamento, MINUTOS_ATE_EXPIRAR };
