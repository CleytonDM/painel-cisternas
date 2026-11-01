// Versão mínima do runtime de painéis do Claude, para o painel rodar como site estático.
// Implementa só o que painel/index.html usa: dash.data, dash.calc, dash.draw, dash.params e
// dash.setParams. Os conjuntos de dados são os CSVs de dados/, lidos como texto (como no Claude).
(() => {
  const FONTES = ['instrumentos', 'pagamentos', 'repasses', 'cronograma', 'metas', 'tecnologias',
    'prazos', 'situacoes', 'empenhos', 'rendimentos'];
  const dados = {};
  const calcs = [];
  const desenhos = new Map();
  let pronto = false;

  const data = (nome) => dados[nome] ?? {status: 'loading', data: []};
  const params = () => Object.fromEntries(new URLSearchParams(location.search));

  function desenhar(nome) {
    const roda = (nm, fn) => document.querySelectorAll(`[data-draw="${nm}"]`).forEach((el) => {
      try { fn(el); } catch (e) { console.error('desenho ' + nm, e); }
    });
    if (nome) { if (desenhos.has(nome)) roda(nome, desenhos.get(nome)); } else desenhos.forEach((fn, nm) => roda(nm, fn));
  }

  // Cálculos na ordem em que o painel os declara (um pode usar o resultado do anterior)
  function calcular() {
    for (const c of calcs) {
      const ent = c.inputs.map(data);
      if (ent.some((d) => d.status === 'error')) { dados[c.name] = {status: 'error', data: []}; continue; }
      try {
        dados[c.name] = {status: 'ok', data: c.fn(...ent.map((d) => d.data))};
      } catch (e) {
        console.error('cálculo ' + c.name, e);
        dados[c.name] = {status: 'error', data: []};
      }
    }
  }

  window.dash = {
    data,
    params,
    setParams(p) {
      const q = new URLSearchParams(location.search);
      Object.entries(p).forEach(([k, v]) => (v == null || v === '' ? q.delete(k) : q.set(k, v)));
      history.replaceState(null, '', (q.size ? '?' + q : location.pathname) + location.hash);
      desenhar();
    },
    calc(nome, def) { calcs.push({name: nome, ...def}); },
    draw(nome, fn) {
      if (fn) desenhos.set(nome, fn);
      if (pronto || !fn) desenhar(nome);
    },
    // Chamado depois dos scripts do painel: lê os CSVs e desenha tudo
    async iniciar() {
      desenhar();
      const lidos = await Promise.allSettled(FONTES.map((f) => d3.csv('dados/' + f + '.csv?v=' + (window.CIS_VERSAO ?? ''))));
      lidos.forEach((r, k) => {
        dados[FONTES[k]] = r.status === 'fulfilled' ? {status: 'ok', data: r.value} : {status: 'error', data: []};
        if (r.status !== 'fulfilled') console.error('dados/' + FONTES[k] + '.csv', r.reason);
      });
      calcular();
      pronto = true;
      desenhar();
      if (lidos.some((r) => r.status !== 'fulfilled')) {
        const p = document.createElement('p');
        p.className = 'site-erro';
        p.setAttribute('role', 'alert');
        p.textContent = 'Não foi possível carregar parte dos dados do painel. Recarregue a página em alguns minutos.';
        document.querySelector('#dash-root').prepend(p);
      }
    },
  };
})();
