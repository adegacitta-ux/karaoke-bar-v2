// Service Worker do Cantokê — cacheia só a "casca" estática do app.
//
// Regra de ouro: NUNCA cachear nada relacionado a Firebase Realtime Database,
// Firebase Auth ou YouTube Data API. Isso é dado ao vivo (fila, apresentação
// atual, login) — cachear por engano cria "fila fantasma" pro usuário.
//
// Versionamento: mude SW_VERSION a cada deploy que altere HTML/CSS/JS do
// shell. Isso troca o nome do cache, então o cache antigo fica órfão e é
// apagado no `activate` — nenhuma página fica presa numa versão velha.
const SW_VERSION = 'v1';
const CACHE_NAME = `cantoke-shell-${SW_VERSION}`;

// HTML "casca" do app — cacheados com estratégia network-first (ver fetch).
const SHELL_URLS = [
    './index.html',
    './display.html',
    './catalogo.html',
    './manifest.json',
    './pwa.js',
    './favicon.ico',
    './icons/icon-192.png',
    './icons/icon-512.png',
    './icons/icon-192-maskable.png',
    './icons/icon-512-maskable.png',
];

// Hosts de dado ao vivo — o Service Worker nunca intercepta essas requisições
// (nem cache-first, nem network-first: passam direto, como se o SW não existisse).
const NUNCA_CACHEAR_HOSTS = [
    'firebaseio.com',           // Realtime Database (fallback REST/long-polling)
    'firebasedatabase.app',     // Realtime Database (domínio novo)
    'identitytoolkit.googleapis.com', // Firebase Auth
    'securetoken.googleapis.com',     // Firebase Auth (refresh de token)
    'www.googleapis.com',       // YouTube Data API (busca de karaokê)
];

function ehDadoAoVivo(url) {
    return NUNCA_CACHEAR_HOSTS.some((host) => url.hostname === host || url.hostname.endsWith('.' + host));
}

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(SHELL_URLS))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((nomes) => Promise.all(
                nomes
                    .filter((nome) => nome.startsWith('cantoke-shell-') && nome !== CACHE_NAME)
                    .map((nome) => caches.delete(nome))
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);

    // Só GET é cacheável; POST/PUT/etc (ex: gravações no Firebase) passam direto.
    if (request.method !== 'GET') return;

    // Dado ao vivo: nunca intercepta. Deixa o navegador/SDK cuidar da requisição.
    if (ehDadoAoVivo(url)) return;

    const ehNavegacaoHTML = request.mode === 'navigate' || request.destination === 'document';

    if (ehNavegacaoHTML) {
        event.respondWith(networkFirst(request));
    } else {
        event.respondWith(cacheFirst(request));
    }
});

// network-first: tenta buscar a versão mais nova da página; só usa cache
// se a rede falhar (ex: wifi caiu no meio da sessão ao vivo do bar).
async function networkFirst(request) {
    try {
        const resposta = await fetch(request);
        const cache = await caches.open(CACHE_NAME);
        cache.put(request, resposta.clone());
        return resposta;
    } catch (erro) {
        const cache = await caches.open(CACHE_NAME);
        const cacheado = await cache.match(request);
        if (cacheado) return cacheado;
        return new Response(
            '<!DOCTYPE html><html lang="pt-br"><head><meta charset="UTF-8">' +
            '<title>Sem conexão — Cantokê</title></head>' +
            '<body style="font-family:sans-serif;background:#150a0f;color:#f7ecd9;' +
            'display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center;padding:24px;">' +
            '<div><h1>Sem conexão</h1><p>Não foi possível carregar esta página e não há uma versão salva no celular.<br>' +
            'Verifique o wifi/dados e tente novamente.</p></div></body></html>',
            { status: 200, headers: { 'Content-Type': 'text/html; charset=UTF-8' } }
        );
    }
}

// cache-first: assets estáticos versionados (CDN do Tailwind, Font Awesome,
// Google Fonts, SDK do Firebase, ícones) — raramente mudam, então serve do
// cache direto e só busca na rede se ainda não tiver.
async function cacheFirst(request) {
    const cache = await caches.open(CACHE_NAME);
    const cacheado = await cache.match(request);
    if (cacheado) return cacheado;

    try {
        const resposta = await fetch(request);
        if (resposta.ok || resposta.type === 'opaque') {
            cache.put(request, resposta.clone());
        }
        return resposta;
    } catch (erro) {
        return Response.error();
    }
}
