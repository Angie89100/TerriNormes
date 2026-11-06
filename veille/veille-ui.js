/* TerriNormes 1.1 — visualisation de la veille, sans certification juridique. */
(() => {
  'use strict';
  const CSS = `
  .tn-veille { margin-top: 12px; padding: 8px 10px; border-radius: 7px; background: #f1f6fa; color: #153c58; font-size: 11px; border-left: 3px solid #7c9ab3; }
  .tn-veille[data-etat="attention"] { background: #fff5e8; color: #69451e; border-left-color: #ce8b30; }
  .tn-veille[data-etat="indisponible"] { background: #f8f0f1; color: #78434a; border-left-color: #bd767e; }
  .tn-veille-detail { margin: 12px 0; padding: 13px; background: #f4f8fb; border: 1px solid #dae5ed; border-radius: 9px; font-size: 12px; }
  .tn-veille-detail h3 { margin: 0 0 8px; color: #173d60; font-size: 14px; }
  .tn-veille-detail p { margin: 6px 0; }
  .tn-veille-detail a { overflow-wrap: anywhere; }
  .tn-veille-detail .tn-releve { padding: 10px 0; border-top: 1px solid #dce6ef; }
  `;
  const style = document.createElement('style');
  style.textContent = CSS;
  document.head.appendChild(style);

  let feed = { sources: [], last_run_at: null };
  let feedError = null;
  const safeList = () => { try { return typeof items === 'function' ? items() : []; } catch (_) { return []; } };
  const itemById = (id) => safeList().find(d => d.id === id);
  const format = (iso) => iso ? new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' }) : 'Jamais';
  const storedCheck = (id) => { try { return JSON.parse(localStorage.getItem('terrinormes_v1_checks') || '{}')[id] || null; } catch (_) { return null; } };
  const checkTimestamp = (value) => {
    const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(String(value || ''));
    return m ? Date.UTC(Number(m[3]), Number(m[2]) - 1, Number(m[1])) : null;
  };
  function related(d) {
    if (!d || !Array.isArray(d.sourceIds)) return [];
    return (feed.sources || []).filter(s => Array.isArray(s.source_ids) && s.source_ids.some(id => d.sourceIds.includes(id)));
  }
  function state(d) {
    const sources = related(d);
    const check = storedCheck(d.id);
    if (feedError) return { etat: 'indisponible', titre: 'Veille indisponible — consulter les sources', sources, check };
    if (!feed.last_run_at) return { etat: 'indisponible', titre: 'Veille non démarrée — aucun contrôle automatique', sources, check };
    if (!sources.length) return { etat: 'neutre', titre: 'Aucune source de veille liée à cette fiche', sources, check };
    if (sources.some(s => s.status === 'controle_impossible' || !s.last_success_at)) {
      return { etat: 'indisponible', titre: 'Contrôle incomplet — vérification manuelle nécessaire', sources, check };
    }
    const changes = sources.filter(s => s.last_change_at);
    const lastChange = changes.reduce((max, s) => Math.max(max, Date.parse(s.last_change_at) || 0), 0);
    const human = checkTimestamp(check);
    if (lastChange && (human === null || human <= lastChange)) {
      return { etat: 'attention', titre: 'Page source modifiée — examen humain à effectuer', sources, check };
    }
    return { etat: 'neutre', titre: check
      ? 'Sources contrôlées ; vérification humaine déclarée le ' + check
      : 'Sources contrôlées ; vérification humaine non déclarée', sources, check };
  }
  const p = (txt) => { const el = document.createElement('p'); el.textContent = txt; return el; };
  function updateCards() {
    for (const card of document.querySelectorAll('.normcard')) {
      const id = card.querySelector('[data-open]')?.getAttribute('data-open');
      const item = itemById(id);
      if (!item) continue;
      const s = state(item);
      let line = card.querySelector('.tn-veille');
      if (!line) { line = document.createElement('div'); line.className = 'tn-veille'; card.appendChild(line); }
      if (line.textContent !== s.titre) line.textContent = s.titre;
      if (line.dataset.etat !== s.etat) line.dataset.etat = s.etat;
    }
  }
  function updateDrawer() {
    const drawer = document.querySelector('#drawer .drawerbody');
    if (!drawer) return;
    let d = null;
    try { d = (typeof selected !== 'undefined') ? selected : null; } catch (_) { /* pas de fiche */ }
    if (!d) return;
    const status = state(d);
    const fingerprint = JSON.stringify([d.id, status, feed.last_run_at, feedError]);
    let section = drawer.querySelector('#tn-veille-detail');
    if (section?.dataset.version === fingerprint) return;
    if (!section) {
      section = document.createElement('div');
      section.id = 'tn-veille-detail';
      section.className = 'tn-veille-detail';
      drawer.insertBefore(section, drawer.lastElementChild);
    }
    section.dataset.version = fingerprint;
    section.replaceChildren();
    const heading = document.createElement('h3');
    heading.textContent = 'Veille documentaire — état des sources';
    section.appendChild(heading);
    section.appendChild(p(status.titre));
    section.appendChild(p('Dernier lancement : ' + format(feed.last_run_at) + ' · Vérification humaine déclarée : ' + (status.check || 'aucune')));
    section.appendChild(p('Attention : une modification de page ne signifie pas automatiquement une modification du droit.'));
    if (feedError) section.appendChild(p('Lecture du journal impossible : ' + feedError));
    if (!status.sources.length) section.appendChild(p('Cette référence ne possède pas encore de source surveillée automatiquement.'));
    for (const s of status.sources) {
      const sub = document.createElement('div');
      sub.className = 'tn-releve';
      sub.appendChild(p(s.nom + ' — ' + ({ initialisation: 'Empreinte initiale', page_modifiee: 'Page modifiée', sans_nouveau_changement: 'Aucun nouveau changement', controle_impossible: 'Contrôle impossible' }[s.status] || 'Non évalué')));
      sub.appendChild(p('Dernier contrôle réussi : ' + format(s.last_success_at)));
      sub.appendChild(p('Dernière modification détectée : ' + format(s.last_change_at)));
      if (s.last_error) sub.appendChild(p('Incident technique : ' + s.last_error));
      const link = document.createElement('a');
      link.href = s.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = 'Ouvrir la source officielle';
      sub.appendChild(link);
      section.appendChild(sub);
    }
    const link = document.createElement('a');
    link.href = 'data/veille.json';
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Consulter le journal technique et les dates';
    section.appendChild(link);
  }
  function updateWatchPage() {
    const page = document.querySelector('#dynamic .panel');
    if (!page || !page.textContent.includes('Veille juridique et accès intégral aux textes')) return;
    let el = document.querySelector('#tn-veille-page');
    if (!el) { el = document.createElement('div'); el.id = 'tn-veille-page'; el.className = 'tn-veille-detail'; page.prepend(el); }
    const msg = 'Surveillance automatique : ' + (feedError ? 'indisponible (' + feedError + ')' :
      !feed.last_run_at ? 'aucune exécution à ce jour' :
      (feed.sources || []).length + ' pages configurées · dernier contrôle ' + format(feed.last_run_at)) +
      '. Les modifications constatées concernent des pages web, et doivent être qualifiées par une personne.';
    if (el.textContent !== msg) el.textContent = msg;
  }
  let pending = false;
  function scheduleRender() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; updateCards(); updateDrawer(); updateWatchPage(); });
  }
  async function refresh() {
    try {
      const res = await fetch(new URL('data/veille.json', document.baseURI), { cache: 'no-store' });
      if (!res.ok) throw Error('HTTP ' + res.status);
      const value = await res.json();
      if (value.schema !== 1 || !Array.isArray(value.sources)) throw Error('Journal invalide');
      feed = value;
      feedError = null;
    } catch (err) { feedError = err.message || 'Erreur inconnue'; }
    scheduleRender();
  }
  const observer = new MutationObserver(scheduleRender);
  const dynamic = document.getElementById('dynamic');
  const drawer = document.getElementById('drawer');
  if (dynamic) observer.observe(dynamic, { childList: true, subtree: true });
  if (drawer) observer.observe(drawer, { childList: true, subtree: true });
  document.addEventListener('click', e => { if (e.target.closest('#markCheck')) setTimeout(scheduleRender, 0); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  refresh();
})();
