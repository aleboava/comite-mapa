/* Mapa de respondentes por cidade — site estático (D3 v7, sem dependências de servidor). */
(function () {
  'use strict';

  const CORES = ['#2f6fdf', '#e07b39', '#2a9d8f', '#c44e7a', '#8a6fd1', '#c9a227', '#5b8c3a', '#b35c3c'];
  const COR_BRASIL = CORES[0];
  const COR_EXTERIOR = CORES[1];
  const fmt = (v) => d3.format(',')(v).replace(/,/g, '.');
  const semMovimento = () => !(window.matchMedia && window.matchMedia('(prefers-reduced-motion: no-preference)').matches);
  const dur = (ms) => (semMovimento() ? 0 : ms);

  const carregar = (nome) => fetch('data/' + nome).then((r) => {
    if (!r.ok) throw new Error('Não foi possível carregar ' + nome);
    return r.json();
  });

  // ---------- utilidades comuns aos mapas ----------

  function preencher(attr, obj) {
    document.querySelectorAll('[' + attr + ']').forEach((el) => {
      const v = obj[el.getAttribute(attr)];
      el.textContent = v == null ? '—' : fmt(v);
    });
  }

  function criaTooltip(el) {
    const tip = document.createElement('div');
    tip.className = 'mp-tip';
    tip.hidden = true;
    el.append(tip);
    return {
      show(ev, linhas) {
        tip.replaceChildren();
        linhas.filter(Boolean).forEach((t, i) => {
          const n = document.createElement(i === 0 ? 'strong' : 'span');
          n.textContent = t;
          tip.append(n);
        });
        tip.hidden = false;
        const box = el.getBoundingClientRect();
        let x = ev.clientX - box.left + 12, y = ev.clientY - box.top + 12;
        if (x + tip.offsetWidth > box.width) x = ev.clientX - box.left - tip.offsetWidth - 12;
        if (y + tip.offsetHeight > box.height) y = ev.clientY - box.top - tip.offsetHeight - 12;
        tip.style.left = Math.max(0, x) + 'px';
        tip.style.top = Math.max(0, y) + 'px';
      },
      hide() { tip.hidden = true; }
    };
  }

  function nivelZoom(el) {
    const d = document.createElement('div');
    d.className = 'mp-zoomlvl';
    el.append(d);
    return (k) => { d.textContent = 'Zoom ' + (Math.round(k * 10) / 10).toString().replace('.', ',') + '×'; };
  }

  // Coloca rótulos sem sobreposição, à direita ou à esquerda do círculo.
  function rotular(gLabels, itens, w, h, classe) {
    const charW = 6.6, lblH = 14, placed = [], out = [];
    for (const it of itens) {
      if (out.length >= 45) break;
      const { x, y, text, rr, key, centro } = it;
      if (x < 0 || x > w || y < 0 || y > h) continue;
      const tw = text.length * charW + (centro ? 6 : 0);
      const opcoes = centro ? [{ a: 'middle', x0: x - tw / 2, tx: x }]
        : [{ a: 'start', x0: x + rr, tx: x + rr }, { a: 'end', x0: x - rr - tw, tx: x - rr }];
      for (const o of opcoes) {
        const b = { x1: o.x0, x2: o.x0 + tw, y1: y - lblH / 2 - 2, y2: y + lblH / 2 };
        if (b.x1 < 2 || b.x2 > w - 2) continue;
        if (placed.some((p) => !(b.x2 < p.x1 || b.x1 > p.x2 || b.y2 < p.y1 || b.y1 > p.y2))) continue;
        placed.push(b);
        out.push({ key, text, a: o.a, x: o.tx, y: y + 4, fora: it.fora });
        break;
      }
    }
    gLabels.selectAll('text').data(out, (o) => o.key).join('text').attr('class', classe)
      .classed('fora', (o) => !!o.fora)
      .attr('text-anchor', (o) => o.a).attr('x', (o) => o.x).attr('y', (o) => o.y).text((o) => o.text);
  }

  function ligaBotoes(el, attr, svg, zoom, aoResetar) {
    const box = el.parentElement;
    if (!box) return;
    box.querySelectorAll('[' + attr + ']').forEach((b) => {
      b.onclick = () => {
        const z = b.getAttribute(attr);
        if (z === 'in') svg.transition().duration(dur(300)).call(zoom.scaleBy, 2);
        else if (z === 'out') svg.transition().duration(dur(300)).call(zoom.scaleBy, 0.5);
        else { if (aoResetar) aoResetar(); svg.transition().duration(dur(600)).call(zoom.transform, d3.zoomIdentity); }
      };
    });
  }

  function legendaTamanho(g, r, max, h, rMax, extraTopo) {
    const lx = 14 + rMax, ly = h - 14;
    const vals = [10, 100, max].filter((v, i, a) => v <= max && a.indexOf(v) === i);
    const topo = ly - 2 * rMax - 26 - (extraTopo || 0);
    g.append('rect').attr('class', 'mp-leg-bg').attr('x', 2).attr('y', topo).attr('width', 2 * rMax + 96).attr('height', ly - topo + 8).attr('rx', 6);
    g.append('text').attr('class', 'mp-leg-t').attr('x', 8).attr('y', ly - 2 * rMax - 10).text('Pessoas');
    vals.forEach((v) => {
      g.append('circle').attr('class', 'mp-leg-c').attr('cx', lx).attr('cy', ly - r(v)).attr('r', r(v));
      g.append('text').attr('class', 'mp-leg-t').attr('x', lx + rMax + 6).attr('y', ly - 2 * r(v) + 4).text(fmt(v));
    });
    return { x: 8, y: topo };
  }

  // Redesenha quando a largura muda, mantendo o zoom se a largura for a mesma.
  function quandoRedimensionar(el, desenhar) {
    let ultima = 0, timer = null;
    const ro = new ResizeObserver(() => {
      const w = el.clientWidth;
      if (Math.abs(w - ultima) < 2) return;
      ultima = w;
      clearTimeout(timer);
      timer = setTimeout(desenhar, 120);
    });
    ro.observe(el);
    ultima = el.clientWidth;
    desenhar();
  }

  function falha(el, msg) {
    el.replaceChildren();
    const p = document.createElement('p');
    p.className = 'mp-fail';
    p.textContent = msg;
    el.append(p);
  }

  function alturaMapa(w, fator) {
    return Math.round(Math.min(w * fator, Math.max(420, (window.innerHeight || 800) * 0.8)));
  }

  // ---------- 1) mapa de pessoas por cidade ----------

  function mapaCidades(el, estados, cidades) {
    let vista = { w: 0, t: d3.zoomIdentity };
    function desenhar() {
      el.replaceChildren();
      const w = Math.max(280, el.clientWidth), h = alturaMapa(w, 0.95);
      const proj = d3.geoMercator().fitExtent([[10, 10], [w - 10, h - 10]], estados);
      const path = d3.geoPath(proj);
      const rows = cidades.map((d) => { const [px, py] = proj([d.lon, d.lat]); return { ...d, px, py, chave: d.cidade + '/' + d.uf }; });
      const porChave = new Map(rows.map((d) => [d.chave, d]));
      const max = d3.max(rows, (d) => d.pessoas) || 1;
      const rMax = Math.max(14, Math.min(36, w / 22));
      const r = d3.scaleSqrt().domain([0, max]).range([0, rMax]);
      const rad = (d) => Math.max(3, r(d.pessoas));

      const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${w} ${h}`).attr('width', '100%')
        .attr('role', 'img').attr('aria-label', 'Mapa do Brasil com círculos por cidade, com zoom');
      const gMap = svg.append('g');
      gMap.selectAll('path').data(estados.features).join('path').attr('class', 'mp-state').attr('d', path);
      const gDots = svg.append('g'), gLabels = svg.append('g'), gLeg = svg.append('g');
      const nivel = nivelZoom(el), tip = criaTooltip(el);

      const dots = gDots.selectAll('circle').data(rows.slice().sort((a, b) => b.pessoas - a.pessoas)).join('circle')
        .attr('class', 'mp-dot').attr('r', rad)
        .on('pointerenter pointermove', function (ev, d) {
          tip.show(ev, [d.cidade + ' (' + d.uf + ')', fmt(d.pessoas) + (d.pessoas === 1 ? ' pessoa' : ' pessoas')]);
          dots.classed('on', false); d3.select(this).classed('on', true);
        })
        .on('pointerleave', () => { tip.hide(); dots.classed('on', false); })
        .on('click', (ev, d) => { ev.stopPropagation(); irPara(d); });

      const render = (t) => {
        gMap.attr('transform', t);
        dots.attr('cx', (d) => t.applyX(d.px)).attr('cy', (d) => t.applyY(d.py));
        const minN = t.k < 1.5 ? Infinity : Math.max(1, 60 / t.k);
        rotular(gLabels, rows.filter((d, i) => i < 5 || d.pessoas >= minN).map((d) => ({
          key: d.chave, x: t.applyX(d.px), y: t.applyY(d.py), rr: rad(d) + 4, text: d.cidade + ' ' + fmt(d.pessoas)
        })), w, h, 'mp-label');
        nivel(t.k);
      };
      const zoom = d3.zoom().scaleExtent([1, 60]).translateExtent([[0, 0], [w, h]]).extent([[0, 0], [w, h]])
        .on('start', tip.hide)
        .on('zoom', (ev) => { vista.t = ev.transform; render(ev.transform); });
      svg.call(zoom).on('dblclick.zoom', null);

      function irPara(d) {
        const k = Math.min(60, Math.max(vista.t.k * 2, 10));
        svg.transition().duration(dur(600)).call(zoom.transform, d3.zoomIdentity.translate(w / 2, h / 2).scale(k).translate(-d.px, -d.py));
      }
      mapaCidades.irPara = (chave) => {
        const d = porChave.get(chave);
        if (!d) return;
        irPara(d);
        el.scrollIntoView({ block: 'nearest', behavior: semMovimento() ? 'auto' : 'smooth' });
      };
      ligaBotoes(el, 'data-zoom', svg, zoom);
      legendaTamanho(gLeg, r, max, h, rMax);

      const inicio = vista.w === w ? vista.t : d3.zoomIdentity;
      vista.w = w;
      svg.call(zoom.transform, inicio);
    }
    quandoRedimensionar(el, desenhar);
  }

  function tabelaRanking(tb, cidades) {
    tb.replaceChildren();
    cidades.slice(0, 15).forEach((r) => {
      const tr = document.createElement('tr');
      [r.cidade, r.uf, fmt(r.pessoas)].forEach((v, i) => {
        const td = document.createElement('td'); td.textContent = v; if (i === 2) td.className = 'n'; tr.append(td);
      });
      tr.onclick = () => mapaCidades.irPara && mapaCidades.irPara(r.cidade + '/' + r.uf);
      tb.append(tr);
    });
  }

  // ---------- 2) mapa dos grupos ----------

  let grupoSel = null;
  let atualizaTabelaGrupos = () => {};

  function convexHull(ps) {
    const p = ps.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    if (p.length < 3) return p;
    const cr = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    const lo = [], up = [];
    for (const q of p) { while (lo.length >= 2 && cr(lo[lo.length - 2], lo[lo.length - 1], q) <= 0) lo.pop(); lo.push(q); }
    for (const q of p.slice().reverse()) { while (up.length >= 2 && cr(up[up.length - 2], up[up.length - 1], q) <= 0) up.pop(); up.push(q); }
    return lo.slice(0, -1).concat(up.slice(0, -1));
  }

  function mapaGrupos(el, estados, gcid) {
    let vista = { w: 0, t: d3.zoomIdentity };
    function desenhar() {
      el.replaceChildren();
      const w = Math.max(280, el.clientWidth), h = alturaMapa(w, 0.95);
      const proj = d3.geoMercator().fitExtent([[10, 10], [w - 10, h - 10]], estados);
      const path = d3.geoPath(proj);
      const pts = gcid.map((d) => { const [px, py] = proj([d.lon, d.lat]); return { ...d, px, py, ox: 0, oy: 0 }; });
      // cidades divididas entre grupos: anel de pontos em volta da cidade
      for (const lista of d3.group(pts, (d) => d.cidade + '/' + d.uf).values()) {
        if (lista.length < 2) continue;
        lista.sort((a, b) => a.grupo.localeCompare(b.grupo));
        const raio = 7 + lista.length * 1.5;
        lista.forEach((d, i) => { const a = (2 * Math.PI * i) / lista.length - Math.PI / 2; d.ox = raio * Math.cos(a); d.oy = raio * Math.sin(a); });
      }
      const grupos = d3.groups(pts, (d) => d.grupo).map(([gid, ps]) => {
        const n = d3.sum(ps, (d) => d.pessoas);
        return { gid, pessoas: n, pts: ps, cx: d3.sum(ps, (d) => d.px * d.pessoas) / n, cy: d3.sum(ps, (d) => d.py * d.pessoas) / n };
      });
      // cores: grupos vizinhos recebem cores diferentes
      grupos.slice().sort((a, b) => a.gid.localeCompare(b.gid)).forEach((gr) => {
        const viz = grupos.filter((o) => o !== gr && o.cor != null)
          .sort((a, b) => Math.hypot(a.cx - gr.cx, a.cy - gr.cy) - Math.hypot(b.cx - gr.cx, b.cy - gr.cy)).slice(0, CORES.length - 1);
        const usadas = new Set(viz.map((o) => o.cor));
        let k = 0; while (usadas.has(k) && k < CORES.length - 1) k++;
        gr.cor = k;
      });
      const corDe = new Map(grupos.map((g) => [g.gid, CORES[g.cor]]));
      const grDe = new Map(grupos.map((g) => [g.gid, g]));
      const r = d3.scaleSqrt().domain([0, d3.max(pts, (d) => d.pessoas) || 1]).range([0, Math.max(9, Math.min(18, w / 45))]);
      const rad = (d) => Math.max(3, r(d.pessoas));

      const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${w} ${h}`).attr('width', '100%')
        .attr('role', 'img').attr('aria-label', 'Mapa do Brasil com os grupos propostos, uma cor por grupo, com zoom');
      const gMap = svg.append('g');
      gMap.selectAll('path').data(estados.features).join('path').attr('class', 'mp-state').attr('d', path);
      const gHull = svg.append('g'), gDots = svg.append('g'), gLabels = svg.append('g');
      const nivel = nivelZoom(el), tip = criaTooltip(el);
      const pos = (d, t) => [t.applyX(d.px) + d.ox, t.applyY(d.py) + d.oy];
      let tAtual = d3.zoomIdentity;

      const dots = gDots.selectAll('circle').data(pts.slice().sort((a, b) => b.pessoas - a.pessoas)).join('circle')
        .attr('class', 'mg-dot').attr('r', rad)
        .style('fill', (d) => corDe.get(d.grupo)).style('stroke', (d) => corDe.get(d.grupo))
        .on('pointerenter pointermove', (ev, d) => tip.show(ev, [
          d.cidade + ' (' + d.uf + ')',
          fmt(d.pessoas) + (d.pessoas === 1 ? ' pessoa' : ' pessoas') + ' neste grupo',
          d.grupo + ' · ' + d.grupo_nome + ' · ' + fmt(grDe.get(d.grupo).pessoas) + ' no total'
        ]))
        .on('pointerleave', tip.hide)
        .on('click', (ev, d) => { ev.stopPropagation(); foco(d.grupo); });

      const render = (t) => {
        tAtual = t;
        gMap.attr('transform', t);
        dots.attr('cx', (d) => pos(d, t)[0]).attr('cy', (d) => pos(d, t)[1]).classed('fora', (d) => grupoSel != null && d.grupo !== grupoSel);
        const sel = grupoSel ? grDe.get(grupoSel) : null;
        gHull.selectAll('path').data(sel ? [sel] : [], (x) => x.gid).join('path').attr('class', 'mg-hull')
          .style('stroke', (x) => corDe.get(x.gid)).style('fill', (x) => corDe.get(x.gid))
          .attr('d', (x) => {
            const ps = [];
            x.pts.forEach((d) => {
              const [cx, cy] = pos(d, t), rr = rad(d) + 8;
              for (let i = 0; i < 12; i++) { const a = (2 * Math.PI * i) / 12; ps.push([cx + rr * Math.cos(a), cy + rr * Math.sin(a)]); }
            });
            const hh = convexHull(ps);
            return hh.length ? 'M' + hh.map((q) => q.join(',')).join('L') + 'Z' : null;
          });
        const ordem = grupos.slice().sort((a, b) => (a.gid === grupoSel ? -1 : b.gid === grupoSel ? 1 : b.pessoas - a.pessoas));
        rotular(gLabels, ordem.map((g) => ({
          key: g.gid, x: t.applyX(g.cx), y: t.applyY(g.cy), text: g.gid, centro: true, fora: grupoSel != null && g.gid !== grupoSel
        })), w, h, 'mg-label');
        nivel(t.k);
      };
      const zoom = d3.zoom().scaleExtent([1, 60]).translateExtent([[0, 0], [w, h]]).extent([[0, 0], [w, h]])
        .on('start', tip.hide)
        .on('zoom', (ev) => { vista.t = ev.transform; render(ev.transform); });
      svg.call(zoom).on('dblclick.zoom', null);
      svg.on('click', () => { if (grupoSel) { grupoSel = null; render(tAtual); atualizaTabelaGrupos(); } });

      function foco(gid) {
        grupoSel = gid;
        atualizaTabelaGrupos();
        const gr = grDe.get(gid);
        if (!gr) { render(tAtual); return; }
        const xs = gr.pts.map((d) => d.px), ys = gr.pts.map((d) => d.py);
        const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
        const k = Math.max(1, Math.min(30, 0.6 / Math.max((x1 - x0) / w, (y1 - y0) / h, 1 / 30)));
        render(tAtual);
        svg.transition().duration(dur(600)).call(zoom.transform, d3.zoomIdentity.translate(w / 2, h / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2));
      }
      mapaGrupos.foco = (gid) => { foco(gid); el.scrollIntoView({ block: 'nearest', behavior: semMovimento() ? 'auto' : 'smooth' }); };
      ligaBotoes(el, 'data-zoom-g', svg, zoom, () => { grupoSel = null; atualizaTabelaGrupos(); });

      const inicio = vista.w === w ? vista.t : d3.zoomIdentity;
      vista.w = w;
      svg.call(zoom.transform, inicio);
    }
    quandoRedimensionar(el, desenhar);
  }

  function tabelaGrupos(tb, resumo) {
    atualizaTabelaGrupos = () => {
      tb.replaceChildren();
      resumo.forEach((r) => {
        const tr = document.createElement('tr');
        if (r.grupo === grupoSel) tr.className = 'sel';
        [r.grupo, r.grupo_nome, fmt(r.pessoas), r.principais, r.ufs].forEach((v, i) => {
          const td = document.createElement('td'); td.textContent = v; if (i === 2) td.className = 'n'; tr.append(td);
        });
        tr.onclick = () => mapaGrupos.foco && mapaGrupos.foco(r.grupo);
        tb.append(tr);
      });
    };
    atualizaTabelaGrupos();
  }

  // ---------- 3) mapa-múndi ----------

  function mapaMundo(el, mundo, cidades, exterior) {
    let vista = { w: 0, t: d3.zoomIdentity };
    function desenhar() {
      el.replaceChildren();
      const w = Math.max(280, el.clientWidth);
      const h = Math.round(Math.min(w * 0.55, Math.max(380, (window.innerHeight || 800) * 0.75)));
      const proj = d3.geoNaturalEarth1().fitExtent([[8, 8], [w - 8, h - 8]], mundo);
      const path = d3.geoPath(proj);
      const pts = [];
      cidades.forEach((d) => pts.push({ nome: d.cidade, onde: d.uf + ', Brasil', pessoas: d.pessoas, lat: d.lat, lon: d.lon, br: true, pais: 'Brasil' }));
      exterior.forEach((d) => pts.push({
        nome: d.local === '(só o país)' ? d.pais : d.local, onde: d.local === '(só o país)' ? 'cidade não informada' : d.pais,
        pessoas: d.pessoas, lat: d.lat, lon: d.lon, br: false, aprox: d.precisao === 'país', pais: d.pais
      }));
      pts.forEach((d) => { const [px, py] = proj([d.lon, d.lat]); d.px = px; d.py = py; });
      const ordemLbl = pts.slice().sort((a, b) => (a.br === b.br ? b.pessoas - a.pessoas : a.br ? 1 : -1));
      const max = d3.max(pts, (d) => d.pessoas) || 1;
      const rMax = Math.max(12, Math.min(30, w / 34));
      const r = d3.scaleSqrt().domain([0, max]).range([0, rMax]);
      const rad = (d) => Math.max(3, r(d.pessoas));

      const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${w} ${h}`).attr('width', '100%')
        .attr('role', 'img').attr('aria-label', 'Mapa-múndi com os inscritos no Brasil e no exterior, com zoom');
      const gMap = svg.append('g');
      gMap.append('path').datum({ type: 'Sphere' }).attr('class', 'mw-sphere').attr('d', path);
      gMap.selectAll('path.mp-state').data(mundo.features).join('path').attr('class', 'mp-state')
        .classed('mw-br', (f) => f.properties.nome === 'Brazil').attr('d', path);
      const gDots = svg.append('g'), gLabels = svg.append('g'), gLeg = svg.append('g');
      const nivel = nivelZoom(el), tip = criaTooltip(el);

      const dots = gDots.selectAll('circle').data(pts.slice().sort((a, b) => b.pessoas - a.pessoas)).join('circle')
        .attr('class', 'mw-dot').classed('aprox', (d) => d.aprox).attr('r', rad)
        .style('fill', (d) => (d.br ? COR_BRASIL : COR_EXTERIOR)).style('stroke', (d) => (d.br ? COR_BRASIL : COR_EXTERIOR))
        .on('pointerenter pointermove', (ev, d) => tip.show(ev, [
          d.nome + ' (' + d.onde + ')', fmt(d.pessoas) + (d.pessoas === 1 ? ' pessoa' : ' pessoas'),
          d.aprox ? 'Posição aproximada: centro do país' : ''
        ]))
        .on('pointerleave', tip.hide)
        .on('click', (ev, d) => { ev.stopPropagation(); irPara([d]); });

      const render = (t) => {
        gMap.attr('transform', t);
        dots.attr('cx', (d) => t.applyX(d.px)).attr('cy', (d) => t.applyY(d.py));
        const minBr = t.k < 3 ? Infinity : Math.max(1, 200 / t.k);
        rotular(gLabels, ordemLbl.filter((d) => !d.br || d.pessoas >= minBr || d.pessoas >= 150).map((d) => ({
          key: d.nome + '|' + d.onde, x: t.applyX(d.px), y: t.applyY(d.py), rr: rad(d) + 4, text: d.nome + ' ' + fmt(d.pessoas)
        })), w, h, 'mp-label');
        nivel(t.k);
      };
      const zoom = d3.zoom().scaleExtent([1, 80]).translateExtent([[0, 0], [w, h]]).extent([[0, 0], [w, h]])
        .on('start', tip.hide)
        .on('zoom', (ev) => { vista.t = ev.transform; render(ev.transform); });
      svg.call(zoom).on('dblclick.zoom', null);

      function irPara(lista) {
        const xs = lista.map((d) => d.px), ys = lista.map((d) => d.py);
        const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
        const teto = lista.length === 1 ? Math.max(vista.t.k * 2, 12) : 40;
        const k = Math.max(1, Math.min(80, teto, 0.6 / Math.max((x1 - x0) / w, (y1 - y0) / h, 1 / 40)));
        svg.transition().duration(dur(600)).call(zoom.transform, d3.zoomIdentity.translate(w / 2, h / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2));
      }
      mapaMundo.irPara = (pais) => {
        const lista = pts.filter((d) => d.pais === pais);
        if (!lista.length) return;
        irPara(lista);
        el.scrollIntoView({ block: 'nearest', behavior: semMovimento() ? 'auto' : 'smooth' });
      };
      ligaBotoes(el, 'data-zoom-w', svg, zoom);

      const topo = legendaTamanho(gLeg, r, max, h, rMax, 34);
      [[COR_BRASIL, 'No Brasil'], [COR_EXTERIOR, 'No exterior']].forEach(([cor, txt], i) => {
        gLeg.append('circle').attr('cx', topo.x + 6).attr('cy', topo.y + 12 + i * 16).attr('r', 5)
          .style('fill', cor).style('fill-opacity', 0.7).style('stroke', cor);
        gLeg.append('text').attr('class', 'mp-leg-t').attr('x', topo.x + 16).attr('y', topo.y + 16 + i * 16).text(txt);
      });

      const inicio = vista.w === w ? vista.t : d3.zoomIdentity;
      vista.w = w;
      svg.call(zoom.transform, inicio);
    }
    quandoRedimensionar(el, desenhar);
  }

  function tabelaPaises(tb, paises) {
    tb.replaceChildren();
    paises.forEach((r) => {
      const tr = document.createElement('tr');
      [r.pais, fmt(r.pessoas), r.locais].forEach((v, i) => {
        const td = document.createElement('td'); td.textContent = v; if (i === 1) td.className = 'n'; tr.append(td);
      });
      tr.onclick = () => mapaMundo.irPara && mapaMundo.irPara(r.pais);
      tb.append(tr);
    });
  }

  // ---------- inicialização ----------

  const els = {
    cidades: document.getElementById('mapa-cidades'),
    grupos: document.getElementById('mapa-grupos'),
    mundo: document.getElementById('mapa-mundo')
  };
  Object.values(els).forEach((el) => { const p = document.createElement('p'); p.className = 'mp-loading'; p.textContent = 'Carregando…'; el.append(p); });

  Promise.all(['resumo.json', 'cidades.json', 'estados.geojson', 'grupos_geral.json', 'grupos_cidades.json',
    'grupos_resumo.json', 'mundo_resumo.json', 'exterior.json', 'paises.json', 'mundo.geojson'].map(carregar))
    .then(([resumo, cidades, estados, gGeral, gCid, gRes, mResumo, exterior, paises, mundo]) => {
      preencher('data-resumo', resumo);
      const at = document.getElementById('atualizado-em');
      if (at && resumo.atualizado_em) {
        const [d, h] = resumo.atualizado_em.split(' ');
        at.textContent = d.split('-').reverse().join('/') + (h ? ' às ' + h : '');
      }
      preencher('data-geral', gGeral);
      preencher('data-mundo', mResumo);
      mapaCidades(els.cidades, estados, cidades);
      tabelaRanking(document.getElementById('tabela-ranking'), cidades);
      mapaGrupos(els.grupos, estados, gCid);
      tabelaGrupos(document.getElementById('tabela-grupos'), gRes);
      mapaMundo(els.mundo, mundo, cidades, exterior);
      tabelaPaises(document.getElementById('tabela-paises'), paises);
    })
    .catch((err) => {
      console.error(err);
      Object.values(els).forEach((el) => falha(el, 'Falha ao carregar os dados. Abra o site por um servidor web (não direto do arquivo) e confira a pasta data/.'));
    });
})();
