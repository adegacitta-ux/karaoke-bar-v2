# 📋 Plano de Refatoração - Karaoke Bar v2

## 🎯 Objetivo
Melhorar a manutenibilidade, performance, segurança e acessibilidade do projeto sem perder funcionalidades.

---

## 🔴 CRÍTICO - Segurança

### 1. **Remover Credenciais Hardcoded**
**Localização:** `index.html` linhas 495 e 498-507
**Problema:** API keys do YouTube e Firebase expostas no código-fonte público
**Impacto:** ALTO - Risco de abuso das APIs

**Solução:**
```javascript
// ❌ ANTES (index.html)
const YOUTUBE_API_KEY = "AIzaSyDLAwdk2PZ3NsKJFHOrXsE8odiJDnJFvlY";
const firebaseConfig = { /* chaves expostas */ };

// ✅ DEPOIS (carregar via servidor)
// 1. Criar arquivo .env.local (não versionar)
// 2. Backend retorna config seguro via API
// 3. Ou usar Firebase REST API sem exposição de keys
```

**Tarefas:**
- [ ] Criar endpoint `/api/config` que retorna firebaseConfig (apenas client-side config seguro)
- [ ] Mover YOUTUBE_API_KEY para backend com rate limiting
- [ ] Adicionar `.env.local` ao `.gitignore`
- [ ] Documentar como configurar credenciais localmente

---

## 🟠 ALTO - Estrutura & Performance

### 2. **Dividir HTML em Módulos JavaScript**
**Localização:** `index.html` (1000+ linhas)
**Problema:** Arquivo monolítico dificultando manutenção

**Estrutura Proposta:**
```
src/
├── index.html (apenas estrutura, sem lógica)
├── js/
│   ├── config/
│   │   ├── firebase-config.js
│   │   └── youtube-config.js
│   ├── modules/
│   │   ├── auth.js (autenticação, login do DJ)
│   │   ├── queue-manager.js (fila, ordenação)
│   │   ├── ui-manager.js (renderização, switchTab)
│   │   ├── notifications.js (notificações, banner)
│   │   ├── theme.js (modo escuro)
│   │   ├── youtube-search.js (modal YouTube)
│   │   └── ratings.js (avaliação de apresentações)
│   ├── utils/
│   │   ├── firebase-sync.js (sincronização)
│   │   ├── storage-manager.js (localStorage)
│   │   ├── validators.js (validações)
│   │   └── formatters.js (formatação de dados)
│   └── app.js (inicialização principal)
├── css/
│   ├── styles.css (CSS inline movido)
│   ├── theme.css (modo escuro)
│   ├── components.css (componentes reutilizáveis)
│   └── responsive.css (media queries)
└── assets/
    ├── icons/
    └── images/
```

**Benefícios:**
- Código mais testável
- Mais fácil de debugar
- Reutilização de funções
- Melhor cache do browser

**Tarefas:**
- [ ] Extrair `auth.js` com funções de autenticação
- [ ] Extrair `queue-manager.js` com lógica de fila
- [ ] Extrair `ui-manager.js` com renderização
- [ ] Extrair `notifications.js` com avisos
- [ ] Extrair tema/CSS para arquivo separado
- [ ] Criar `app.js` que orquestra tudo

---

### 3. **Otimizar Carregamento de Scripts**
**Localização:** `index.html` linhas 7-12
**Problema:** Scripts síncronos bloqueando renderização

**Solução:**
```html
<!-- ❌ ANTES -->
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
<script src="https://www.gstatic.com/firebasejs/10.7.0/firebase-app-compat.js"></script>

<!-- ✅ DEPOIS -->
<!-- Critical: Tailwind (gerar CSS estático em produção) -->
<link rel="preload" href="/css/tailwind.css" as="style">
<link href="/css/tailwind.css" rel="stylesheet">

<!-- Font Awesome async -->
<link rel="preload" href="/css/font-awesome.min.css" as="style">
<link href="/css/font-awesome.min.css" rel="stylesheet" media="print" onload="this.media='all'">

<!-- Firebase carregado após renderização inicial -->
<script defer src="https://www.gstatic.com/firebasejs/10.7.0/firebase-app-compat.js"></script>
<script defer src="/js/app.js"></script>
```

**Tarefas:**
- [ ] Usar Tailwind CSS estático em produção
- [ ] Lazy load Font Awesome
- [ ] Adicionar `defer` aos scripts
- [ ] Implementar skeleton screens enquanto carrega

---

## 🟡 MÉDIO - Funcionalidades

### 4. **Melhorar Validação de Formulário**
**Localização:** `index.html` linhas 196-226
**Problema:** Validação insuficiente, sem feedback de erro

**Exemplo de Melhoria:**
```javascript
// ✅ validators.js
const VALIDATORS = {
  nome: (valor) => ({
    valido: valor.trim().length > 0 && valor.trim().length <= 50,
    mensagem: 'Nome deve ter entre 1 e 50 caracteres'
  }),
  musica: (valor) => ({
    valido: valor.trim().length > 0 && valor.trim().length <= 100,
    mensagem: 'Música deve ter entre 1 e 100 caracteres'
  }),
  mesa: (valor) => ({
    valido: !valor || valor.match(/^[\d\-\w]{1,20}$/) !== null,
    mensagem: 'Número da mesa inválido'
  }),
  artista: (valor) => ({
    valido: !valor || valor.trim().length <= 100,
    mensagem: 'Artista deve ter até 100 caracteres'
  })
};

function validarFormulario(dados) {
  const erros = {};
  Object.keys(VALIDATORS).forEach(campo => {
    if (campo in dados) {
      const resultado = VALIDATORS[campo](dados[campo]);
      if (!resultado.valido) {
        erros[campo] = resultado.mensagem;
      }
    }
  });
  return { valido: Object.keys(erros).length === 0, erros };
}
```

**Tarefas:**
- [ ] Criar arquivo `utils/validators.js`
- [ ] Implementar validação real-time no formulário
- [ ] Mostrar mensagens de erro claras
- [ ] Sanitizar entrada (XSS prevention)
- [ ] Testar edge cases

---

### 5. **Melhorar Gerenciamento de Estado**
**Localização:** `index.html` linhas 699-715
**Problema:** Estado global espalhado, sem pattern claro

**Solução - Estado Centralizado:**
```javascript
// ✅ utils/store.js
class KaraokeStore {
  constructor() {
    this.listeners = [];
    this.state = {
      fila: [],
      historico: [],
      contagemCantores: {},
      filaManualFechada: false,
      apresentacaoAtual: null,
      usuarioAtual: null,
      firebaseConnected: false,
      modoEscuroAtivo: false
    };
  }

  setState(updates) {
    this.state = { ...this.state, ...updates };
    this.notifyListeners();
  }

  getState() {
    return { ...this.state };
  }

  subscribe(listener) {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter(l => l !== listener);
    };
  }

  notifyListeners() {
    this.listeners.forEach(listener => listener(this.state));
  }
}

// Uso:
const store = new KaraokeStore();
store.subscribe(novoState => {
  console.log('Estado atualizado:', novoState);
  atualizarUI(novoState);
});
```

**Tarefas:**
- [ ] Criar `utils/store.js` com gerenciador de estado
- [ ] Refatorar funções para usar `store.setState()`
- [ ] Remover variáveis globais
- [ ] Implementar time-travel debugging (opcional, para desenvolvimento)

---

## 🟢 MÉDIO - Acessibilidade

### 6. **Adicionar Labels Acessíveis**
**Localização:** `index.html` linhas 141-145, 188-190, etc
**Problema:** Botões sem `aria-label`, inputs sem labels associados

**Exemplo:**
```html
<!-- ❌ ANTES -->
<button onclick="switchTab('cliente')" class="px-3 py-1 text-sm font-medium rounded-md hover:bg-gray-100">Pedir Música</button>

<!-- ✅ DEPOIS -->
<button 
  onclick="switchTab('cliente')" 
  class="px-3 py-1 text-sm font-medium rounded-md hover:bg-gray-100"
  aria-label="Ir para aba de pedido de música"
  aria-current="page">
  Pedir Música
</button>

<!-- Para toggle tema -->
<button 
  onclick="alternarModoEscuro()" 
  id="btn-toggle-tema" 
  class="toggle-tema-btn" 
  title="Alternar modo escuro/claro"
  aria-label="Alternar tema"
  aria-pressed="false">
  <i class="fas fa-moon" id="icone-tema" aria-hidden="true"></i>
</button>
```

**Tarefas:**
- [ ] Adicionar `aria-label` a todos os botões
- [ ] Associar labels aos inputs via `for` e `id`
- [ ] Adicionar `aria-hidden="true"` a ícones decorativos
- [ ] Adicionar `aria-live="polite"` a áreas dinâmicas
- [ ] Testar com screen reader (NVDA, JAWS)
- [ ] Garantir contraste de cores (WCAG AA)

---

### 7. **Melhorar Semântica HTML**
**Localização:** Todo o HTML
**Problema:** Divs genéricas sem semântica

**Exemplo:**
```html
<!-- ❌ ANTES -->
<div id="cliente" class="tab-content active">

<!-- ✅ DEPOIS -->
<section id="cliente" class="tab-content active" role="tabpanel" aria-labelledby="tab-cliente">
```

**Tarefas:**
- [ ] Usar `<section>`, `<article>`, `<aside>` apropriadamente
- [ ] Adicionar `role="tabpanel"` às abas
- [ ] Usar `<header>`, `<nav>`, `<footer>` semanticamente
- [ ] Melhorar hierarquia de headings (h1, h2, h3)

---

## 🟢 BAIXO - Qualidade de Código

### 8. **Adicionar Testes Unitários**
**Localização:** Novo arquivo `tests/`
**Problema:** Sem testes, difícil garantir qualidade

**Estrutura:**
```
tests/
├── unit/
│   ├── validators.test.js
│   ├── formatters.test.js
│   └── queue-manager.test.js
├── integration/
│   └── firebase-sync.test.js
└── e2e/
    └── user-flow.test.js
```

**Exemplo com Jest:**
```javascript
// ✅ tests/unit/validators.test.js
describe('Validators', () => {
  test('deve validar nome corretamente', () => {
    expect(VALIDATORS.nome('João').valido).toBe(true);
    expect(VALIDATORS.nome('').valido).toBe(false);
    expect(VALIDATORS.nome('a'.repeat(51)).valido).toBe(false);
  });

  test('deve validar música corretamente', () => {
    expect(VALIDATORS.musica('Evidências').valido).toBe(true);
    expect(VALIDATORS.musica('').valido).toBe(false);
  });

  test('deve validar mesa corretamente', () => {
    expect(VALIDATORS.mesa('12').valido).toBe(true);
    expect(VALIDATORS.mesa('mesa-1').valido).toBe(true);
    expect(VALIDATORS.mesa('mesa@123').valido).toBe(false);
  });
});
```

**Tarefas:**
- [ ] Configurar Jest
- [ ] Escrever testes para validators
- [ ] Escrever testes para formatters
- [ ] Escrever testes para queue-manager
- [ ] Configurar CI/CD com testes automáticos

---

### 9. **Adicionar Logging Estruturado**
**Localização:** Novo arquivo `utils/logger.js`
**Problema:** `console.log` espalhado sem padrão

**Solução:**
```javascript
// ✅ utils/logger.js
const LOG_LEVELS = {
  DEBUG: 0,
  INFO: 1,
  WARN: 2,
  ERROR: 3
};

class Logger {
  constructor(moduleName, level = LOG_LEVELS.INFO) {
    this.moduleName = moduleName;
    this.level = level;
  }

  debug(msg, data = {}) {
    if (this.level <= LOG_LEVELS.DEBUG) {
      console.debug(`[${this.moduleName}] ${msg}`, data);
    }
  }

  info(msg, data = {}) {
    if (this.level <= LOG_LEVELS.INFO) {
      console.info(`[${this.moduleName}] ${msg}`, data);
    }
  }

  warn(msg, data = {}) {
    if (this.level <= LOG_LEVELS.WARN) {
      console.warn(`[${this.moduleName}] ${msg}`, data);
    }
  }

  error(msg, error = null) {
    if (this.level <= LOG_LEVELS.ERROR) {
      console.error(`[${this.moduleName}] ${msg}`, error);
    }
  }
}

export default Logger;
```

**Tarefas:**
- [ ] Criar `utils/logger.js`
- [ ] Substituir `console.log` por logger
- [ ] Adicionar contexto a cada log
- [ ] Implementar envio de logs para servidor (em produção)

---

### 10. **Melhorar Tratamento de Erros**
**Localização:** Todo o código
**Problema:** Falta de try-catch, erros silenciosos

**Exemplo:**
```javascript
// ✅ Antes
try {
  firebase.auth().signInAnonymously().catch((error) => {
    console.error('❌ Erro na autenticação anônima:', error);
  });
} catch (error) {
  console.warn('⚠️ Erro ao inicializar Firebase, usando localStorage:', error);
}

// ✅ Depois
async function inicializarAutenticacao() {
  try {
    const user = await firebase.auth().signInAnonymously();
    logger.info('Autenticação anônima iniciada', { uid: user.user.uid });
    return user;
  } catch (error) {
    logger.error('Falha na autenticação anônima', error);
    // Fallback gracioso
    return null;
  }
}
```

**Tarefas:**
- [ ] Envolver Firebase calls em try-catch
- [ ] Implementar error boundaries
- [ ] Mostrar erros amigáveis ao usuário
- [ ] Registrar erros para análise

---

## 📊 Tabela de Prioridades

| ID | Tarefa | Prioridade | Esforço | Resultado |
|----|--------|-----------|--------|-----------|
| 1 | Remover API keys hardcoded | 🔴 CRÍTICO | 2h | Segurança |
| 2 | Dividir HTML em módulos | 🟠 ALTO | 8h | Manutenibilidade |
| 3 | Otimizar carregamento scripts | 🟠 ALTO | 3h | Performance |
| 4 | Validação de formulário | 🟡 MÉDIO | 3h | Qualidade |
| 5 | Gerenciamento de estado | 🟡 MÉDIO | 4h | Manutenibilidade |
| 6 | Acessibilidade (aria-labels) | 🟢 MÉDIO | 2h | Inclusão |
| 7 | Semântica HTML | 🟢 MÉDIO | 2h | Qualidade |
| 8 | Testes unitários | 🟢 BAIXO | 6h | Qualidade |
| 9 | Logging estruturado | 🟢 BAIXO | 2h | Debugging |
| 10 | Tratamento de erros | 🟡 MÉDIO | 3h | Confiabilidade |

---

## 🚀 Ordem de Implementação Recomendada

### Fase 1 (Sprint 1) - Segurança & Estabilidade
1. ✅ Remover API keys hardcoded (ID 1)
2. ✅ Validação de formulário (ID 4)
3. ✅ Tratamento de erros melhorado (ID 10)

### Fase 2 (Sprint 2) - Performance & Estrutura
4. ✅ Otimizar carregamento scripts (ID 3)
5. ✅ Dividir HTML em módulos (ID 2) - Pode ser feito gradualmente
6. ✅ Gerenciamento de estado centralizado (ID 5)

### Fase 3 (Sprint 3) - Qualidade & Acessibilidade
7. ✅ Acessibilidade (ID 6)
8. ✅ Semântica HTML (ID 7)
9. ✅ Logging estruturado (ID 9)

### Fase 4 (Sprint 4+) - Testes & Polish
10. ✅ Testes unitários (ID 8)

---

## 📝 Checklist de Implementação

### Para cada tarefa:
- [ ] Criar branch feature (`git checkout -b refactor/tarefa-x`)
- [ ] Implementar mudanças
- [ ] Testar localmente
- [ ] Criar pull request com descrição clara
- [ ] Code review
- [ ] Merge para main
- [ ] Deploy em staging
- [ ] Testar em produção

---

## 🔗 Referências & Resources

- [MDN - Web Accessibility](https://developer.mozilla.org/en-US/docs/Web/Accessibility)
- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [Firebase Security Best Practices](https://firebase.google.com/docs/rules/basics)
- [JavaScript Design Patterns](https://www.patterns.dev/posts/module-pattern/)
- [Jest Testing Framework](https://jestjs.io/)

---

**Última atualização:** 2026-08-18
**Responsável:** Refactoring Task
