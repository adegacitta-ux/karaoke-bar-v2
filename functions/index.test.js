// Testes unitários da lógica de verdade das Cloud Functions (não testam
// index.html nem o navegador -- isso é coberto por tests/test_karaoke.py).
// Mockam as chamadas HTTP ao Mercado Pago e ao Secret Manager, e usam um
// "Firebase falso" em memória (ver jest.mock('firebase-admin') abaixo) em vez
// do Realtime Database de verdade -- suficiente pra testar a lógica de
// autorização, preço, trava de duplicidade e validação do webhook, que é
// tudo pura leitura/escrita de dados, sem precisar de rede nem emulador.

jest.mock("firebase-admin", () => {
  const store = {};

  function getAtPath(path) {
    const partes = path.split("/").filter(Boolean);
    let atual = store;
    for (const parte of partes) {
      if (atual == null) return undefined;
      atual = atual[parte];
    }
    return atual;
  }

  function setAtPath(path, valor) {
    const partes = path.split("/").filter(Boolean);
    let atual = store;
    for (let i = 0; i < partes.length - 1; i++) {
      const parte = partes[i];
      if (typeof atual[parte] !== "object" || atual[parte] === null) atual[parte] = {};
      atual = atual[parte];
    }
    const ultima = partes[partes.length - 1];
    if (valor === null || valor === undefined) {
      delete atual[ultima];
    } else {
      atual[ultima] = valor;
    }
  }

  function ref(path) {
    return {
      once: async () => ({ val: () => { const v = getAtPath(path); return v === undefined ? null : v; } }),
      set: async (valor) => setAtPath(path, valor),
      update: async (parcial) => {
        const atual = getAtPath(path) || {};
        setAtPath(path, { ...atual, ...parcial });
      },
      remove: async () => setAtPath(path, null),
      // Simula uma transação "sequencial" (sem concorrência real -- não dá
      // pra testar corrida de verdade num teste unitário síncrono): lê o
      // valor atual, chama a função, e só grava se ela devolver algo
      // diferente de undefined -- exatamente a mesma regra do Firebase real.
      transaction: async (fn) => {
        const atual = getAtPath(path) ?? null;
        const resultado = fn(atual);
        if (resultado === undefined) {
          return { committed: false, snapshot: { val: () => atual } };
        }
        setAtPath(path, resultado);
        return { committed: true, snapshot: { val: () => resultado } };
      },
    };
  }

  const fakeDb = { ref };
  const databaseFn = jest.fn(() => fakeDb);
  databaseFn.ServerValue = { TIMESTAMP: "TIMESTAMP_FALSO" };

  return {
    apps: [],
    initializeApp: jest.fn(),
    database: databaseFn,
    __store: store,
  };
});

// Mocka o módulo inteiro de https do firebase-functions -- não só porque os
// testes não precisam do onCall/onRequest de verdade (chamam os handlers
// direto), mas porque REQUERER esse módulo de verdade puxa o firebase-admin
// inteiro (auth, jwks-rsa, jose) por dentro, e o pacote "jose" é ESM puro, que
// quebra o parser padrão do Jest. Só precisamos de um HttpsError com o mesmo
// formato {code, message} que o código real usa.
jest.mock("firebase-functions/v2/https", () => {
  class HttpsError extends Error {
    constructor(code, message) {
      super(message);
      this.code = code;
    }
  }
  return {
    onCall: (handler) => handler,
    onRequest: (handler) => handler,
    HttpsError,
  };
});

jest.mock("firebase-functions/logger", () => ({
  info: jest.fn(),
  warn: jest.fn(),
  error: jest.fn(),
}));

jest.mock("./mercadoPago", () => ({
  criarPagamentoPix: jest.fn(),
  buscarPagamento: jest.fn(),
  MINUTOS_ATE_EXPIRAR: 10,
}));

jest.mock("./secretManager", () => ({
  buscarAccessTokenDoBar: jest.fn(),
}));

const admin = require("firebase-admin");
const { criarPagamentoPix, buscarPagamento } = require("./mercadoPago");
const { buscarAccessTokenDoBar } = require("./secretManager");
const { criarCobrancaPixHandler, webhookHandler } = require("./index");

const BAR_ID = "citta";
const store = admin.__store;

function limparStore() {
  Object.keys(store).forEach((chave) => delete store[chave]);
}

function seed(caminho, valor) {
  admin.database().ref(caminho).set(valor);
}

beforeEach(() => {
  limparStore();
  jest.clearAllMocks();
  seed(`bares/${BAR_ID}/config`, { nome: "Bar da Citta", precoFurarFila: 5 });
  buscarAccessTokenDoBar.mockResolvedValue("TOKEN-FALSO");
});

describe("criarCobrancaPixHandler", () => {
  test("rejeita se o pedido não pertence ao uid de quem chama", async () => {
    seed(`bares/${BAR_ID}/karaoke/fila`, [
      { id: 1, nome: "Dona do pedido", criadoPorUid: "uid-dono" },
    ]);

    await expect(
      criarCobrancaPixHandler({ barId: BAR_ID, pedidoId: 1, uid: "uid-intruso" })
    ).rejects.toMatchObject({ code: "permission-denied" });

    expect(criarPagamentoPix).not.toHaveBeenCalled();
  });

  test("ignora qualquer valor que o cliente tentasse mandar e usa o preço configurado do bar", async () => {
    seed(`bares/${BAR_ID}/karaoke/fila`, [
      { id: 1, nome: "Dono", criadoPorUid: "uid-dono" },
    ]);
    criarPagamentoPix.mockResolvedValue({
      id: "PAG-1",
      point_of_interaction: { transaction_data: { qr_code: "copia-e-cola", qr_code_base64: "base64" } },
    });

    // O handler nem aceita um parâmetro de valor vindo do cliente -- só
    // barId/pedidoId/uid. Confirma que o valor realmente usado na cobrança é
    // o que está configurado no bar (5), não algo que um cliente adulterado
    // pudesse tentar injetar por fora desse contrato.
    await criarCobrancaPixHandler({ barId: BAR_ID, pedidoId: 1, uid: "uid-dono" });

    expect(criarPagamentoPix).toHaveBeenCalledWith(
      expect.objectContaining({ valorEmReais: 5 })
    );
  });

  test("não cria cobrança duplicada se já existe uma pendente (trava por transação)", async () => {
    seed(`bares/${BAR_ID}/karaoke/fila`, [
      { id: 1, nome: "Dono", criadoPorUid: "uid-dono" },
    ]);
    seed(`bares/${BAR_ID}/karaoke/pagamentosPixPrivado/1`, {
      status: "aguardando_pagamento",
      criadoPorUid: "uid-dono",
      valorPago: 5,
      paymentId: "PAG-EXISTENTE",
      qrCodeBase64: "base64-existente",
      copiaECola: "copia-existente",
      dataExpiracaoMs: Date.now() + 5 * 60 * 1000,
    });

    const resultado = await criarCobrancaPixHandler({ barId: BAR_ID, pedidoId: 1, uid: "uid-dono" });

    expect(resultado.paymentId).toBe("PAG-EXISTENTE");
    expect(resultado.copiaECola).toBe("copia-existente");
    expect(criarPagamentoPix).not.toHaveBeenCalled(); // não bateu de novo no Mercado Pago
  });
});

describe("webhookHandler", () => {
  function seedReservaAguardando() {
    seed(`bares/${BAR_ID}/karaoke/pagamentosPixPrivado/1`, {
      status: "aguardando_pagamento",
      criadoPorUid: "uid-dono",
      valorPago: 5,
      paymentId: "PAG-1",
      dataExpiracaoMs: Date.now() + 5 * 60 * 1000,
    });
  }

  test("processa a mesma notificação duas vezes sem duplicar efeito (idempotência)", async () => {
    seed(`bares/${BAR_ID}/karaoke/fila`, [{ id: 1, criadoPorUid: "uid-dono" }]);
    seedReservaAguardando();
    buscarPagamento.mockResolvedValue({
      id: "PAG-1",
      status: "approved",
      transaction_amount: 5,
      external_reference: `${BAR_ID}:1`,
    });

    const primeira = await webhookHandler({ barId: BAR_ID, paymentId: "PAG-1" });
    expect(primeira.status).toBe(200);
    expect(admin.database().ref(`bares/${BAR_ID}/karaoke/pagamentosPixPublico/1`).once).toBeDefined();
    const publicoAposPrimeira = await (await admin.database().ref(`bares/${BAR_ID}/karaoke/pagamentosPixPublico/1`).once()).val();
    expect(publicoAposPrimeira.prioridadePaga).toBe(true);

    const segunda = await webhookHandler({ barId: BAR_ID, paymentId: "PAG-1" });
    expect(segunda.corpo).toBe("já processado");
  });

  test("rejeita se o valor pago não bate com o preço configurado", async () => {
    seed(`bares/${BAR_ID}/karaoke/fila`, [{ id: 1, criadoPorUid: "uid-dono" }]);
    seedReservaAguardando(); // reserva foi feita esperando R$5
    buscarPagamento.mockResolvedValue({
      id: "PAG-1",
      status: "approved",
      transaction_amount: 0.5, // Mercado Pago confirma só 50 centavos
      external_reference: `${BAR_ID}:1`,
    });

    const resultado = await webhookHandler({ barId: BAR_ID, paymentId: "PAG-1" });

    expect(resultado.corpo).toMatch(/não confere/);
    const publico = await (await admin.database().ref(`bares/${BAR_ID}/karaoke/pagamentosPixPublico/1`).once()).val();
    expect(publico).toBeNull(); // prioridade NÃO foi liberada
  });

  test("grava em pagamentosOrfaos quando o pedido já saiu da fila (cancelado)", async () => {
    // fila SEM o pedido 1 -- a pessoa cancelou ou o pedido já foi processado
    seed(`bares/${BAR_ID}/karaoke/fila`, []);
    seedReservaAguardando();
    buscarPagamento.mockResolvedValue({
      id: "PAG-1",
      status: "approved",
      transaction_amount: 5,
      external_reference: `${BAR_ID}:1`,
    });

    const resultado = await webhookHandler({ barId: BAR_ID, paymentId: "PAG-1" });

    expect(resultado.corpo).toBe("pagamento órfão registrado");
    const orfao = await (await admin.database().ref(`bares/${BAR_ID}/karaoke/pagamentosOrfaos/PAG-1`).once()).val();
    expect(orfao.motivo).toBe("PAGAMENTO_RECEBIDO_APOS_CANCELAMENTO");
    const publico = await (await admin.database().ref(`bares/${BAR_ID}/karaoke/pagamentosPixPublico/1`).once()).val();
    expect(publico).toBeNull();
  });

  test("grava em pagamentosOrfaos com motivo 'chamado' quando o DJ já chamou o pedido", async () => {
    seed(`bares/${BAR_ID}/karaoke/fila`, []); // já saiu da fila...
    seed(`bares/${BAR_ID}/karaoke/apresentacaoAtual`, { id: 1 }); // ...porque está cantando agora
    seedReservaAguardando();
    buscarPagamento.mockResolvedValue({
      id: "PAG-1",
      status: "approved",
      transaction_amount: 5,
      external_reference: `${BAR_ID}:1`,
    });

    const resultado = await webhookHandler({ barId: BAR_ID, paymentId: "PAG-1" });

    const orfao = await (await admin.database().ref(`bares/${BAR_ID}/karaoke/pagamentosOrfaos/PAG-1`).once()).val();
    expect(orfao.motivo).toBe("PAGAMENTO_RECEBIDO_APOS_CHAMADA");
    expect(resultado.status).toBe(200);
  });
});
