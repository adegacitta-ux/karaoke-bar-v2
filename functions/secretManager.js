const { SecretManagerServiceClient } = require("@google-cloud/secret-manager");

const cliente = new SecretManagerServiceClient();

// Cada bar tem seu próprio Access Token do Mercado Pago, então não dá pra usar
// defineSecret(...) (o jeito "padrão" de segredo do Firebase Functions v2) --
// defineSecret exige que o NOME do segredo seja fixo em tempo de deploy, sem
// interpolação com um valor (o barId) que só existe em tempo de execução. Em
// vez disso, buscamos o segredo diretamente pelo nome montado a partir do
// barId, sempre que a function roda. Isso é o que permite um bar novo
// funcionar só cadastrando o segredo dele (ver README.md), sem reimplantar as
// functions.
function nomeDoSegredo(barId) {
  return `mp-access-token-${barId}`;
}

async function buscarAccessTokenDoBar(barId) {
  const nomeSegredo = nomeDoSegredo(barId);
  try {
    const [versao] = await cliente.accessSecretVersion({
      name: `projects/${process.env.GCLOUD_PROJECT}/secrets/${nomeSegredo}/versions/latest`,
    });
    const valor = versao.payload?.data?.toString("utf8").trim();
    return valor || null;
  } catch (erro) {
    // Segredo não cadastrado ainda pra esse bar (bar novo, ou feature ainda não
    // configurada) -- não é uma falha da function, é uma etapa de configuração
    // pendente (ver README.md). Devolve null em vez de deixar o erro do Secret
    // Manager (que menciona nomes internos de projeto) vazar pro chamador.
    if (erro.code === 5 /* NOT_FOUND */) return null;
    throw erro;
  }
}

module.exports = { buscarAccessTokenDoBar };
