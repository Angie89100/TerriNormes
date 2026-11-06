/* TerriNormes 1.2 — tableau de bord de veille documentaire et revue humaine locale. */
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
  .tn-dashboard { margin: 0 0 22px; }
  .tn-dashboard h2 { font-family: Georgia,serif; margin: 16px 0 12px; font-size: 22px; color: #184b70; }
  .tn-dashboard p { line-height: 1.55; }
  .tn-dashboard-kpis { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 10px; margin: 13px 0 18px; }
  .tn-dashboard-kpi { background: #fff; border: 1px solid #d9e4ed; border-radius: 10px; padding: 12px 14px; }
  .tn-dashboard-kpi strong { display:block; color: #164563; font: 700 25px Georgia,serif; }
  .tn-dashboard-kpi span { display:block; font-size: 11px; color: #587085; margin-top: 4px; }
  .tn-intro { background: #f1f6fa; border-left: 4px solid #24628f; border-radius: 9px; padding: 12px 14px; font-size: 12px; }
  .tn-intro strong { color: #163f61; }
  .tn-dashboard .tn-toolbar { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin: 11px 0; }
  .tn-dashboard .tn-toolbar a,.tn-dashboard .tn-toolbar button { font-size:12px; }
  .tn-data-table { width:100%; border-collapse:collapse; font-size:12px; }
  .tn-data-table th { text-align:left; background:#eef4f8; color:#234b69; font-size:11px; }
  .tn-data-table td,.tn-data-table th { padding: 10px; border-bottom: 1px solid #e1e8ef; vertical-align:top; }
  .tn-data-table tr:hover td { background:#fafcfe; }
  .tn-scroll { overflow-x: auto; border: 1px solid #d8e2eb; border-radius:9px; }
  .tn-data-table a { overflow-wrap:anywhere; }
  .tn-status { display: inline-block; border-radius: 999px; padding: 3px 9px; background:#edf3f8; color:#31536e; font-size:11px; font-weight:700; }
  .tn-status[data-state="blocked"],.tn-status[data-state="pending"] { background:#fff0e8; color:#934326; }
  .tn-status[data-state="changed"] { background:#fff2ce; color:#775211; }
  .tn-status[data-state="ok"] { background:#e9f5f0; color:#21624b; }
  .tn-priority { border-left:3px solid #cf9433; padding:9px 12px; background:#fffaf0; margin:8px 0; font-size:12px; border-radius:5px; }
  .tn-priority a { font-weight:600; }
  .tn-empty-note { color:#637689; font-size:12px; }
  .tn-review-form { background:#f7fafc; border:1px solid #d6e3ec; border-radius:10px; padding:14px; }
  .tn-review-form label { display:block; margin:8px 0 5px; font-weight:650; font-size:12px; color:#34526a; }
  .tn-review-form input,.tn-review-form select,.tn-review-form textarea { display:block; width:100%; border:1px solid #cbd9e4; padding:10px; border-radius:7px; background:white; color:#14364c; font:inherit; font-size:12px; }
  .tn-review-form textarea { min-height:80px; }
  .tn-review-grid { display:grid;grid-template-columns:1fr 1fr;gap:12px; }
  .tn-review-form .btn { margin-top:12px; }
  .tn-review-warning { font-size:11px;color:#635544; margin-top:9px; }
  @media(max-width:840px) { .tn-dashboard-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.tn-review-grid{grid-template-columns:1fr} }

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

  // Registre de revue humaine local au navigateur : ne constitue ni un visa juridique ni une validation partagée.
  const REVIEWS_KEY = 'terrinormes_v12_revues_humaines';
  const html = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safeURL = value => { try { const u = new URL(String(value)); return u.protocol === 'https:' ? u.href : ''; } catch (_) { return ''; } };
  function allReviews() {
    try { const data = JSON.parse(localStorage.getItem(REVIEWS_KEY) || '[]');
      return Array.isArray(data) ? data.filter(x => x && typeof x.sourceId === 'string' && typeof x.date === 'string').slice(-500) : [];
    } catch (_) { return []; }
  }
  let reviews = allReviews();
  function lastReview(id) {
    return reviews.filter(x => x.sourceId === id).sort((a,b) => Date.parse(b.date || '') - Date.parse(a.date || ''))[0] || null;
  }
  function reviewedAfterLastChange(s) {
    const review = lastReview(s.id);
    if (!review || review.conclusion !== 'sans_incidence') return false;
    if (!s.last_change_at) return true;
    return Date.parse(review.date) > Date.parse(s.last_change_at);
  }
  function technicalStatus(s) {
    if (s.status === 'controle_impossible' || !s.last_success_at) return ['blocked','Contrôle impossible'];
    if (s.status === 'initialisation') return ['ok','Empreinte initiale'];
    if (s.status === 'page_modifiee') return ['changed','Page modifiée'];
    return ['ok','Contrôle effectué'];
  }
  function requiredAction(s) {
    if (s.status === 'controle_impossible' || !s.last_success_at) {
      return 'Accès automatique impossible : vérifier manuellement la source officielle et rechercher une méthode de collecte autorisée.';
    }
    if (s.last_change_at && !reviewedAfterLastChange(s)) {
      return 'Modification de page signalée : examiner les textes applicables et consigner son incidence éventuelle.';
    }
    const r = lastReview(s.id);
    if (!r) return 'Revue juridique initiale non consignée : déterminer les textes, versions et champs d’application pertinents.';
    if (r.conclusion === 'impact_potentiel') return 'Incidence juridique possible : expertise et décision à documenter.';
    if (r.conclusion === 'a_completer') return 'Revue humaine partielle : contrôle à compléter.';
    return '';
  }
  function dashboardHTML() {
    const sources = Array.isArray(feed.sources) ? feed.sources : [];
    const ok = sources.filter(s => !!s.last_success_at && s.status !== 'controle_impossible').length;
    const blocked = sources.filter(s => s.status === 'controle_impossible' || !s.last_success_at).length;
    const changed = sources.filter(s => !!s.last_change_at && !reviewedAfterLastChange(s) && s.status !== 'controle_impossible').length;
    const todo = sources.filter(s => !!requiredAction(s));
    const summary = feedError ? 'Journal indisponible : ' + feedError :
      (!feed.last_run_at ? 'Aucun contrôle automatique exécuté à ce jour.' :
        'Dernier lancement technique : ' + format(feed.last_run_at) + '. ' + ok + ' source(s) accessibles, ' + blocked + ' contrôle(s) impossible(s).');
    const statusTable = sources.map(s => {
      const [state,label] = technicalStatus(s), link = safeURL(s.url), rv=lastReview(s.id);
      const manual = rv ? 'Revue déclarée le '+format(rv.date)+(rv.reviewer ? ' · '+rv.reviewer : '') : 'Aucune revue consignée';
      const errorText = s.last_error ? '<div style="color:#964d2d;font-size:11px;">'+html(s.last_error)+'</div>': '';
      return '<tr><td><strong>'+html(s.nom)+'</strong><div>'+(link?'<a href="'+html(link)+'" target="_blank" rel="noopener noreferrer">Source officielle ↗</a>':'URL indisponible')+'</div></td>'+ 
        '<td><span class="tn-status" data-state="'+state+'">'+label+'</span>'+errorText+'</td>'+ 
        '<td>'+html(format(s.last_attempt_at))+'</td><td>'+html(format(s.last_success_at))+'</td>'+ 
        '<td>'+html(format(s.last_change_at))+'</td><td>'+html(manual)+'</td>'+ 
        '<td><button type="button" class="btn tiny" data-tn-review-open="'+html(s.id)+'">Consigner une revue</button></td></tr>';
    }).join('');
    const incidentList = todo.map(s => '<div class="tn-priority"><strong>'+html(s.nom)+'</strong> — '+html(requiredAction(s))+'</div>').join('');
    const events = sources.flatMap(s => Array.isArray(s.history) ? s.history.map(h => ({
      date:h.date, source:s.nom, event:h.evenement
    })) : []).sort((a,b) => (Date.parse(b.date)||0)-(Date.parse(a.date)||0)).slice(0,15);
    const eventLabels = {'premiere_empreinte':'Première empreinte enregistrée','page_modifiee':'Modification de page détectée','sans_nouveau_changement':'Aucun changement détecté'};
    const eventRows = events.map(e=>'<tr><td>'+html(format(e.date))+'</td><td>'+html(e.source)+'</td><td>'+html(eventLabels[e.event] || e.event || 'Événement technique')+'</td></tr>').join('');
    const reviewsRows = reviews.slice().sort((a,b) => (Date.parse(b.date)||0)-(Date.parse(a.date)||0)).slice(0,12).map(r => {
      const source = sources.find(s=>s.id===r.sourceId);
      const label = {sans_incidence:'Aucune incidence relevée (déclaratif)',impact_potentiel:'Incidence possible',a_completer:'À compléter'}[r.conclusion] || 'Conclusion non précisée';
      return '<tr><td>'+html(format(r.date))+'</td><td>'+html(source?.nom || r.sourceId)+'</td><td>'+html(r.reviewer || '')+'</td><td>'+html(label)+'</td><td>'+html(r.scope || '')+'</td></tr>';
    }).join('');
    const reviewOptions = sources.map(s=>'<option value="'+html(s.id)+'">'+html(s.nom)+'</option>').join('');
    return '<div class="tn-dashboard" aria-label="Tableau de bord de veille">'+
      '<div class="tn-intro"><strong>Surveillance technique partielle — pas de mise à jour automatique du droit.</strong> '+html(summary)+
      ' Une modification de page ne prouve pas une évolution de la réglementation ; un contrôle humain documenté reste nécessaire.</div>'+ 
      '<div class="tn-dashboard-kpis">'+
      '<div class="tn-dashboard-kpi"><strong>'+sources.length+'</strong><span>Sources configurées</span></div>'+ 
      '<div class="tn-dashboard-kpi"><strong>'+ok+'</strong><span>Contrôles accessibles</span></div>'+ 
      '<div class="tn-dashboard-kpi"><strong>'+blocked+'</strong><span>Contrôles impossibles</span></div>'+ 
      '<div class="tn-dashboard-kpi"><strong>'+todo.length+'</strong><span>Actions humaines ou techniques à traiter</span></div></div>'+ 
      '<div class="tn-toolbar"><button id="tn-refresh" class="btn tiny" type="button">Actualiser les résultats</button>'+ 
      '<a class="btn tiny" target="_blank" rel="noopener noreferrer" href="data/veille.json">Journal technique JSON ↗</a>'+ 
      '<button id="tn-export-reviews" type="button" class="btn tiny">Exporter les revues humaines (JSON)</button></div>'+ 
      '<h2>État des sources surveillées</h2>'+ 
      '<div class="tn-scroll"><table class="tn-data-table"><thead><tr><th scope="col">Source</th><th scope="col">Contrôle technique</th>'+ 
      '<th scope="col">Dernière tentative</th><th scope="col">Dernier succès</th><th scope="col">Changement détecté</th>'+ 
      '<th scope="col">Revue humaine (locale)</th><th scope="col">Action</th></tr></thead><tbody>'+ 
      (statusTable || '<tr><td colspan="7">Aucune source chargée.</td></tr>')+'</tbody></table></div>'+ 
      '<h2>Vérifications et incidents à traiter</h2>'+ 
      (incidentList || '<p class="tn-empty-note">Aucune action identifiée dans les données disponibles. Ce résultat ne garantit pas la conformité juridique.</p>')+ 
      (changed ? '<p class="tn-empty-note">'+changed+' source(s) avec changement détecté non clôturé(s) par une revue « sans incidence ».</p>':'')+ 
      '<h2>Historique des événements techniques</h2>'+ 
      '<div class="tn-scroll"><table class="tn-data-table"><thead><tr><th>Date</th><th>Source</th><th>Événement</th></tr></thead><tbody>'+ 
      (eventRows || '<tr><td colspan="3">Aucun événement enregistré.</td></tr>')+'</tbody></table></div>'+ 
      '<p class="tn-empty-note">L’historique répertorie les événements consignés par le robot, pas nécessairement chaque contrôle sans changement.</p>'+ 
      '<h2>Historique des revues humaines consignées ici</h2>'+ 
      '<div class="tn-scroll"><table class="tn-data-table"><thead><tr><th>Date</th><th>Source</th><th>Déclarant</th><th>Conclusion</th><th>Périmètre vérifié</th></tr></thead><tbody>'+ 
      (reviewsRows || '<tr><td colspan="5">Aucune revue humaine enregistrée dans ce navigateur.</td></tr>')+'</tbody></table></div>'+ 
      '<h2>Consigner une revue humaine</h2>'+ 
      '<form id="tn-review-form" class="tn-review-form">'+ 
      '<div class="tn-review-grid"><div><label for="tn-review-source">Source concernée *</label><select id="tn-review-source" required>'+reviewOptions+'</select></div>'+ 
      '<div><label for="tn-review-author">Contrôle effectué par (nom ou fonction) *</label><input id="tn-review-author" required maxlength="100" placeholder="Ex. : référent commande publique"></div></div>'+ 
      '<label for="tn-review-scope">Textes, articles, version et date d’application vérifiés *</label><textarea id="tn-review-scope" required minlength="10" maxlength="2000" placeholder="Citer les références précises et la date d’effet"></textarea>'+ 
      '<label for="tn-review-conclusion">Conclusion de la revue *</label><select id="tn-review-conclusion" required>'+ 
      '<option value="a_completer">Vérification à compléter</option>'+ 
      '<option value="impact_potentiel">Incidence juridique possible — à examiner</option>'+ 
      '<option value="sans_incidence">Aucune incidence juridique relevée sur le périmètre contrôlé</option></select>'+ 
      '<label for="tn-review-comments">Observations complémentaires</label><textarea id="tn-review-comments" maxlength="2000" placeholder="Méthode, points de vigilance, actions à engager"></textarea>'+ 
      '<button class="btn primary" type="submit">Enregistrer la revue dans ce navigateur</button>'+ 
      '<p class="tn-review-warning">Attention : déclaration locale, non authentifiée, non partagée entre agents et sans valeur de visa juridique officiel. Ne saisissez pas de données confidentielles. Sauvegardez régulièrement le JSON des revues.</p>'+ 
      '<div id="tn-review-notice" role="status" aria-live="polite"></div></form>'+ 
      '</div>';
  }

  function updateWatchPage() {
    const page = document.querySelector('#dynamic .panel');
    if (!page || !page.textContent.includes('Veille juridique et accès intégral aux textes')) return;
    let el = document.querySelector('#tn-veille-page');
    if (!el) { el = document.createElement('div'); el.id = 'tn-veille-page'; page.prepend(el); }
    const version = JSON.stringify([feed,feedError,reviews]);
    if (el.dataset.version === version) return;
    el.dataset.version = version;
    el.innerHTML = dashboardHTML();
  }
  function updateMentions() {
    const sidebar = document.querySelector('.sidebottom');
    if (sidebar && sidebar.dataset.tnVersion !== '1.2') {
      sidebar.innerHTML = 'Édition documentaire du 04/11/2026.<br>Veille technique partielle (4 pages configurées), sans mise à jour ni validation juridique automatique.<br><b>Notes et revues :</b> stockage dans ce navigateur.';
      sidebar.dataset.tnVersion = '1.2';
    }
    const footer = document.querySelector('.footer');
    if (footer && footer.dataset.tnVersion !== '1.2') {
      footer.textContent = 'TerriNormes · Référentiel documentaire 04/11/2026 · Module de veille technique 1.2 · Validation juridique humaine à documenter · Non affilié aux organismes officiels.';
      footer.dataset.tnVersion = '1.2';
    }
  }
  document.addEventListener('click', event => {
    const action = event.target.closest('[data-tn-review-open]');
    if (action) {
      const form = document.querySelector('#tn-review-form');
      if (!form) return;
      const sel = form.querySelector('#tn-review-source');
      if (sel) sel.value = action.getAttribute('data-tn-review-open');
      form.scrollIntoView({behavior:'smooth',block:'start'});
      form.querySelector('#tn-review-author')?.focus({preventScroll:true});
    }
    if (event.target.closest('#tn-refresh')) refresh();
    if (event.target.closest('#tn-export-reviews')) {
      const data = JSON.stringify({app:'TerriNormes',type:'revues_humaines_locales',version:'1.2',exported_at:new Date().toISOString(),reviews},null,2);
      const obj = URL.createObjectURL(new Blob([data],{type:'application/json;charset=utf-8'}));
      const link = document.createElement('a');
      link.href = obj;link.download = 'TerriNormes_revues_humaines_'+new Date().toISOString().slice(0,10)+'.json';
      document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(obj),1500);
    }
  });
  document.addEventListener('submit', event => {
    if (event.target.id !== 'tn-review-form') return;
    event.preventDefault();
    const form = event.target;
    if (!form.reportValidity()) return;
    const sourceId=form.querySelector('#tn-review-source').value;
    if (!(feed.sources || []).some(s=>s.id===sourceId)) return;
    const reviewer=form.querySelector('#tn-review-author').value.trim();
    const scope=form.querySelector('#tn-review-scope').value.trim();
    if (!reviewer || scope.length < 10) return;
    const entry={
      sourceId, date:new Date().toISOString(), reviewer, scope,
      conclusion:form.querySelector('#tn-review-conclusion').value,
      comments:form.querySelector('#tn-review-comments').value.trim()
    };
    const next=[...reviews,entry].slice(-500);
    try { localStorage.setItem(REVIEWS_KEY,JSON.stringify(next)); reviews=next; scheduleRender(); }
    catch (_) { const el=form.querySelector('#tn-review-notice'); if(el)el.textContent='Stockage impossible : activez le stockage local de ce navigateur.'; }
  });
  let pending = false;
  function scheduleRender() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; updateCards(); updateDrawer(); updateWatchPage(); updateMentions(); });
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
