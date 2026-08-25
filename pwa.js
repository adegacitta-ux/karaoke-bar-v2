// Registro do Service Worker + manifest dinâmico por bar.
// Incluído em index.html, display.html e catalogo.html.
//
// O manifest.json é um arquivo estático (GitHub Pages não roda servidor),
// então start_url não pode ler o "?bar=ID" da URL sozinho. Pra instalar o
// app já apontando pro bar certo, geramos uma cópia do manifest em memória
// (Blob URL) com start_url ajustado, e trocamos o href do <link rel="manifest">
// antes do navegador usá-lo pra instalar.
(function ajustarManifestParaBar() {
    try {
        const params = new URLSearchParams(window.location.search);
        const barId = (params.get('bar') || '').trim().toLowerCase().replace(/[^a-z0-9-]/g, '');
        if (!barId) return; // sem ?bar= na URL: mantém o manifest.json estático

        const linkManifest = document.querySelector('link[rel="manifest"]');
        if (!linkManifest) return;

        fetch(linkManifest.href)
            .then((resposta) => resposta.json())
            .then((manifest) => {
                const pagina = window.location.pathname.split('/').pop() || 'index.html';
                manifest.start_url = `./${pagina}?bar=${encodeURIComponent(barId)}`;
                manifest.id = manifest.start_url;
                const blob = new Blob([JSON.stringify(manifest)], { type: 'application/json' });
                linkManifest.setAttribute('href', URL.createObjectURL(blob));
            })
            .catch((erro) => console.error('[Cantokê PWA] Falha ao ajustar manifest para o bar atual:', erro));
    } catch (erro) {
        console.error('[Cantokê PWA] Erro ao preparar manifest dinâmico:', erro);
    }
})();

if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('./service-worker.js')
            .then((registro) => console.info('[Cantokê PWA] Service worker registrado:', registro.scope))
            .catch((erro) => console.error('[Cantokê PWA] Falha ao registrar o service worker:', erro));
    });
} else {
    console.warn('[Cantokê PWA] Este navegador não suporta service workers — o app funciona normalmente, mas sem cache offline.');
}
