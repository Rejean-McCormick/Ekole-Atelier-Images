'use strict';

const $ = id => document.getElementById(id);
const session = document.querySelector('meta[name="atelier-session"]').content;
let profiles = {};
let engines = {};
let catalogue = null;
let polling = false;
let review = null;
let reviewBusy = false;
const colorFields = ['palette-color-1', 'palette-color-2', 'palette-color-3'];
const formatCount = new Intl.NumberFormat('fr-CA');
const statsColumns = [['total', 'Total'], ['done', 'Générées'], ['pending', 'Restantes']];
let themeStatsRows = new Map();
let themeStatsLayout = '';

async function api(route, body) {
  const options = body === undefined ? {} : {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Atelier-Session': session},
    body: JSON.stringify(body)
  };
  const response = await fetch('/api/' + route, options);
  const payload = await response.json();
  if (!response.ok) throw Error(payload.error);
  return payload;
}

function selection() {
  return {profile: $('profile').value, root: $('root').value,
    theme: $('theme').value, branch: $('branch').value, palette: selectedPalette()};
}

function generationSelection() {
  const refresh = !$('comparison').checked && $('refresh-images').checked;
  if (!$('all-themes').checked) return {...selection(), refresh};
  return {profile: $('profile').value, root: $('root').value, allThemes: true, refresh};
}

function options(select, entries) {
  select.replaceChildren(...entries.map(([value, label]) => new Option(label, value)));
}

function report(error) {
  $('error').hidden = !error;
  $('error').textContent = error ? error.message : '';
}

function action(id, fn, event = 'click') {
  $(id).addEventListener(event, async e => {
    e.preventDefault();
    report();
    try { await fn(); } catch (error) { report(error); }
  });
}

function clearBranch() {
  $('review').hidden = true;
  review = null;
  $('links').hidden = true;
  $('progress').textContent = '';
}

function selectedPalette() {
  const choice = $('palette-choice').value;
  if (choice === 'theme') return catalogue.themes[$('theme').value].colors;
  if (choice.startsWith('preset:')) return catalogue.palettes[choice.slice(7)];

  const colors = colorFields.map(id => $(id).value.trim().toUpperCase()).filter(Boolean);
  if (!colors.length || colors.some(color => !/^#[0-9A-F]{6}$/.test(color))) {
    throw Error('Entre de 1 à 3 couleurs au format #RRGGBB.');
  }
  if (new Set(colors).size !== colors.length) throw Error('Choisis des couleurs différentes.');
  return colors;
}

function previewPalette() {
  $('palette-custom').hidden = $('palette-choice').value !== 'custom';
  const data = catalogue.themes[$('theme').value];
  let colors;
  try { colors = selectedPalette(); } catch (error) {
    $('palette-preview').textContent = error.message;
    $('prompt').value = data.prompt;
    return;
  }
  const codes = colors.join(', ');
  const swatches = colors.map(color => {
    const swatch = document.createElement('span');
    swatch.setAttribute('aria-hidden', 'true');
    Object.assign(swatch.style, {
      display: 'inline-block', width: '1em', height: '1em',
      marginRight: '0.3em', border: '1px solid currentColor', backgroundColor: color
    });
    return swatch;
  });
  $('palette-preview').replaceChildren(...swatches, ' ' + codes);
  $('prompt').value = catalogue.textOnly
    ? data.prompt + ' Palette : ' + codes + '.'
    : data.prompt.replace('Palette dominante : ' + data.colors.join(', ') + '.', 'Palette dominante : ' + codes + '.');
}

function showTheme() {
  const data = catalogue.themes[$('theme').value];
  options($('branch'), [['', 'Toutes les branches'], ...Object.entries(data.branches)
    .map(([branch, count]) => [branch, branch + ' · ' + count + ' images'])]);
  previewPalette();
  $('prompt-label').textContent = catalogue.textOnly ? 'Direction artistique du thème' : 'Prompt à copier dans ChatGPT';
  showEngine();
  $('reference-status').textContent = data.ready ? 'Référence prête.' : 'Ajoute l’image créée dans ChatGPT.';
  clearBranch();
}

function showLinks(data) {
  $('plan-link').href = data.plan;
  $('gallery-link').href = data.gallery;
  $('comparison-links').replaceChildren(...Object.entries(data.comparisons || {}).map(([engine, path]) => {
    const link = document.createElement('a');
    link.id = 'compare-' + engine;
    link.textContent = 'Essai ' + engines[engine].name;
    link.href = path;
    link.target = '_blank';
    link.rel = 'noopener';
    return link;
  }));
  $('links').hidden = false;
}

function showCatalogueStats(stats) {
  for (const [key] of statsColumns) {
    $('stats-' + key).textContent = formatCount.format(stats[key]);
  }
  updateProgress($('stats-progress'), stats);
  showThemeStats(stats.themes);
  $('catalogue-stats').hidden = false;
}

function createProgress(label) {
  const bar = document.createElement('progress');
  bar.setAttribute('aria-label', label);
  return bar;
}

function updateProgress(bar, counts) {
  bar.max = counts.total || 1;
  bar.value = counts.done;
  const percent = counts.total ? Math.floor(100 * counts.done / counts.total) : 0;
  bar.dataset.complete = String(counts.total > 0 && counts.done === counts.total);
  return formatCount.format(percent) + '\u00a0%';
}

function showThemeStats(themes) {
  const layout = JSON.stringify(Object.entries(themes).map(([id, theme]) =>
    [id, theme.name, Object.keys(theme.branches)]));
  if (layout !== themeStatsLayout) {
    themeStatsRows = new Map();
    const sections = Object.entries(themes).map(([id, theme]) => {
      const details = document.createElement('details');
      const summary = document.createElement('summary');
      const name = document.createElement('strong');
      const counts = document.createElement('span');
      const percent = document.createElement('span');
      percent.className = 'theme-percent';
      const bar = createProgress('Progression · ' + theme.name);
      name.textContent = theme.name;
      summary.append(name, percent, bar, counts);
      const table = document.createElement('table');
      table.setAttribute('aria-label', 'Branches · ' + theme.name);
      const heading = table.createTHead().insertRow();
      for (const label of ['Branche', ...statsColumns.map(([, title]) => title), 'Progression']) {
        const cell = document.createElement('th');
        cell.scope = 'col';
        cell.textContent = label;
        heading.append(cell);
      }
      const body = table.createTBody();
      const rows = new Map();
      for (const branch of Object.keys(theme.branches)) {
        const row = body.insertRow();
        const name = document.createElement('th');
        name.scope = 'row';
        name.textContent = branch;
        row.append(name);
        const cells = statsColumns.map(() => row.insertCell());
        const progressCell = row.insertCell();
        progressCell.className = 'branch-progress';
        const branchBar = createProgress('Progression · ' + theme.name + ' · ' + branch);
        const branchPercent = document.createElement('span');
        progressCell.append(branchBar, branchPercent);
        rows.set(branch, {cells, bar: branchBar, percent: branchPercent});
      }
      themeStatsRows.set(id, {counts, rows, bar, percent});
      details.append(summary, table);
      return details;
    });
    $('theme-stats').replaceChildren(...sections);
    themeStatsLayout = layout;
  }
  for (const [id, theme] of Object.entries(themes)) {
    const {counts, rows, bar, percent} = themeStatsRows.get(id);
    percent.textContent = updateProgress(bar, theme);
    counts.textContent = statsColumns.map(([key, label]) =>
      label + ' ' + formatCount.format(theme[key])).join(' · ');
    for (const [branch, values] of Object.entries(theme.branches)) {
      const row = rows.get(branch);
      statsColumns.forEach(([key], index) => {
        row.cells[index].textContent = formatCount.format(values[key]);
      });
      row.percent.textContent = updateProgress(row.bar, values);
    }
  }
}

function setBusy(busy) {
  for (const id of ['profile','root','load','theme','branch','palette-choice', ...colorFields, 'upload','engine','workflow','all-themes','comparison','refresh-images','generate','plan','view-images','approve-images','publish-images','reject-images','delete-images','select-images']) $(id).disabled = busy;
  if (!busy) {
    $('comparison').disabled = $('all-themes').checked;
    $('refresh-images').disabled = $('comparison').checked;
    updateImageSelection();
  }
}

async function monitor() {
  if (polling) return;
  polling = true;
  setBusy(true);
  $('stop').hidden = false;
  try {
    while (true) {
      const status = await api('etat');
      if (status.stats) showCatalogueStats(status.stats);
      $('progress').textContent = status.stopping
        ? 'Arrêt demandé. L’image en cours peut se terminer.'
        : status.message;
      if (status.stopping) $('stop').disabled = true;
      if (!status.active) {
        if (status.plan && status.gallery) showLinks(status);
        break;
      }
      await new Promise(resolve => setTimeout(resolve, 1200));
    }
  } finally {
    polling = false;
    $('stop').hidden = true;
    $('stop').disabled = false;
    setBusy(false);
  }
}

$('profile').addEventListener('change', () => {
  $('root-label').hidden = profiles[$('profile').value].adapter !== 'kristals-quebec';
  $('reference').hidden = $('lot').hidden = true;
  $('catalogue-stats').hidden = true;
  clearBranch();
});
$('root').addEventListener('input', () => {
  $('reference').hidden = $('lot').hidden = true;
  $('catalogue-stats').hidden = true;
  clearBranch();
});
$('theme').addEventListener('change', showTheme);
$('palette-choice').addEventListener('change', () => {
  if ($('palette-choice').value === 'custom' && colorFields.every(id => !$(id).value.trim())) {
    $(colorFields[0]).value = catalogue.themes[$('theme').value].colors[0];
  }
  previewPalette();
  clearBranch();
});
for (const id of colorFields) {
  $(id).addEventListener('input', () => {
    previewPalette();
    clearBranch();
  });
}
$('branch').addEventListener('change', clearBranch);

action('load', async () => {
  setBusy(true);
  try {
    catalogue = await api('charger', {profile: $('profile').value, root: $('root').value});
    options($('palette-choice'), [
      ['theme', 'Palette du thème'],
      ...Object.entries(catalogue.palettes).map(([name, colors]) => ['preset:' + name, name + ' · ' + colors.length]),
      ['custom', 'Palette personnalisée']
    ]);
    colorFields.forEach(id => { $(id).value = ''; });
    options($('theme'), Object.entries(catalogue.themes).map(([id, item]) => [id, item.name]));
    showCatalogueStats(catalogue.stats);
    showTheme();
    $('reference').hidden = $('lot').hidden = false;
  } finally { setBusy(false); }
});

action('copy', async () => {
  await navigator.clipboard.writeText($('prompt').value);
  $('reference-status').textContent = 'Prompt copié.';
});

action('upload', async () => {
  const file = $('upload').files[0];
  if (!file) return;
  if (file.size > 10 * 1024 * 1024) throw Error('Image trop volumineuse. Maximum 10 Mo.');
  const selected = selection();
  const image = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(',')[1]);
    reader.onerror = () => reject(Error('Lecture de l’image impossible.'));
    reader.readAsDataURL(file);
  });
  await api('reference', {...selected, image});
  catalogue.themes[selected.theme].ready = true;
  if ($('theme').value === selected.theme) $('reference-status').textContent = 'Référence enregistrée.';
}, 'change');

action('plan', async () => {
  const data = await api('plan', generationSelection());
  showLinks(data);
  $('progress').textContent = data.pending + ' images manquantes'
    + (data.refreshable ? ' · ' + data.refreshable + ' images à refaire.' : '.');
});

action('stop', async () => {
  $('stop').disabled = true;
  try {
    const status = await api('arreter', {});
    if (status.stopping) $('progress').textContent = 'Arrêt demandé. L’image en cours peut se terminer.';
  } catch (error) {
    $('stop').disabled = false;
    throw error;
  }
});

function updateImageSelection() {
  const boxes = [...document.querySelectorAll('#image-grid input[type="checkbox"]')];
  const count = boxes.filter(box => box.checked).length;
  $('select-images').disabled = polling || reviewBusy || !boxes.length;
  $('select-images').textContent = count && count === boxes.length
    ? 'Désélectionner tout' : 'Tout sélectionner dans cette vue';
  $('delete-images').disabled = polling || reviewBusy || !count;
  $('delete-images').textContent = count
    ? 'Supprimer ' + count + (count === 1 ? ' image' : ' images')
    : 'Supprimer la sélection';
}

const statusLabels = {nouvelle: 'Nouvelle', validee: 'Validée', integree: 'Intégrée'};

function renderImages() {
  const filter = $('image-filter').value;
  const rows = review.images.filter(row => !filter || row.status === filter);
  $('publish-images').hidden = !review.integration;
  $('reject-images').hidden = !rows.some(row => row.status === 'nouvelle');
  $('delete-images').hidden = !rows.length;
  $('review-status').textContent = rows.length + ' images dans cette vue.';
  $('image-grid').replaceChildren(...rows.map(row => {
    const card = document.createElement('article');
    const preview = document.createElement('a');
    preview.href = row.url;
    preview.target = '_blank';
    preview.rel = 'noopener';
    const image = new Image();
    image.src = row.url;
    image.alt = row.titre;
    image.loading = 'lazy';
    preview.append(image);
    const label = document.createElement('label');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.value = row.key;
    checkbox.addEventListener('change', updateImageSelection);
    label.append(checkbox, ' ' + row.titre + ' · ' + row.slot);
    const state = document.createElement('small');
    state.textContent = row.cours + ' · ' + statusLabels[row.status];
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'Prompt pour une prochaine génération';
    const prompt = document.createElement('p');
    prompt.style.whiteSpace = 'pre-wrap';
    prompt.textContent = row.prompt;
    details.append(summary, prompt);
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.textContent = 'Supprimer cette image';
    remove.addEventListener('click', async () => {
      report();
      try { await changeImages('supprimer', [row.key]); } catch (error) { report(error); }
    });
    card.append(preview, label, state, details, remove);
    return card;
  }));
  updateImageSelection();
}

async function refreshImages() {
  const selected = selection();
  const data = await api('revision', selected);
  if (JSON.stringify(selected) !== JSON.stringify(selection())) return;
  review = data;
  renderImages();
  $('review').hidden = false;
}

async function changeImages(action, explicitKeys) {
  if (reviewBusy || polling) return;
  const keys = explicitKeys || Array.from(document.querySelectorAll('#image-grid input:checked'), input => input.value);
  if (!keys.length) throw Error('Sélectionne au moins une image.');
  if (action === 'supprimer' && !confirm(
    'Supprimer définitivement ' + keys.length + ' image(s) de l’atelier ? Les copies publiées dans Ekole restent disponibles.'
  )) return;
  if (action === 'ecarter' && !confirm('Écarter les nouvelles images sélectionnées ? Elles pourront être régénérées.')) return;
  if (action === 'integrer' && !confirm('Publier les images validées sélectionnées dans Ekole pour ce thème ?')) return;
  reviewBusy = true;
  setBusy(true);
  try {
    const selected = selection();
    const data = await api('revision', {...selected, action, keys});
    if (action === 'supprimer' || action === 'ecarter') {
      showCatalogueStats(await api('statistiques', {profile: selected.profile, root: selected.root}));
    }
    if (action !== 'supprimer') $('image-filter').value = ({valider: 'validee', integrer: 'integree', ecarter: 'nouvelle'})[action];
    await refreshImages();
    $('review-status').textContent = data.done + ({valider: ' images validées.', integrer: ' images intégrées.', ecarter: ' images écartées.', supprimer: ' images supprimées.'})[action];
    if (data.errors.length) throw Error(data.errors.join(' | '));
  } finally { reviewBusy = false; setBusy(false); }
}

action('view-images', refreshImages);
$('image-filter').addEventListener('change', () => { if (review) renderImages(); });
action('select-images', () => {
  const boxes = [...document.querySelectorAll('#image-grid input[type="checkbox"]')];
  const allChecked = boxes.every(box => box.checked);
  boxes.forEach(box => { box.checked = !allChecked; });
  updateImageSelection();
});
action('reject-images', () => changeImages('ecarter'));
action('delete-images', () => changeImages('supprimer'));
action('approve-images', () => changeImages('valider'));
action('publish-images', () => changeImages('integrer'));

function showEngine() {
  const engine = engines[$('engine').value];
  const local = engine.mode !== 'cloud';
  const upload = engine.mode === 'upload';
  $('all-themes-field').hidden = !local;
  if (!local) {
    $('all-themes').checked = false;
    $('comparison').disabled = false;
  }
  $('engine-description').textContent = engine.description || '';
  $('workflow-field').hidden = !upload;
  $('workflow').required = upload;
  $('account-field').hidden = $('token-field').hidden = local;
  $('account').required = $('token').required = !local;
  $('reference-controls').hidden = $('reference-mode').hidden = local || !!catalogue?.textOnly;
}

$('engine').addEventListener('change', showEngine);
$('all-themes').addEventListener('change', () => {
  const allThemes = $('all-themes').checked;
  $('comparison').disabled = allThemes;
  if (allThemes) {
    $('comparison').checked = false;
    $('refresh-images').disabled = false;
    $('limit').value = '0';
  }
  clearBranch();
});
$('comparison').addEventListener('change', () => {
  $('refresh-images').disabled = $('comparison').checked;
  if ($('comparison').checked) $('limit').value = '6';
});

action('generation', async () => {
  const selected = generationSelection();
  const limit = Number($('limit').value);
  const engine = $('engine').value;
  const mode = engines[engine].mode;
  const comparison = $('comparison').checked;
  if (comparison && !(limit >= 1 && limit <= 24)) throw Error('Choisis entre 1 et 24 images pour comparer.');
  const data = await api('plan', selected);
  const available = comparison ? data.total : data.pending + data.refreshable;
  const count = limit ? Math.min(limit, available) : available;
  if (!count) { showLinks(data); $('progress').textContent = 'Les images de ce lot sont déjà présentes.'; return; }
  const cost = mode === 'cloud'
    ? ' Estimation Cloudflare : ' + (count * 0.001207).toFixed(3) + ' $ US hors forfait et taxes.'
    : ' Calcul sur ton ordinateur via ComfyUI.';
  const target = selected.allThemes ? ' pour tous les thèmes' : '';
  if (!window.confirm('Générer au plus ' + count + ' images' + target + ' ?' + cost)) return;
  const body = {...selected, limit, engine, comparison};
  if (mode === 'upload') {
    const file = $('workflow').files[0];
    if (!file || file.size > 1024 * 1024) throw Error('Choisis un workflow JSON de 1 Mo maximum.');
    body.workflow = JSON.parse(await file.text());
  } else if (mode === 'cloud') {
    body.account = $('account').value;
    body.token = $('token').value;
    body.withoutReference = catalogue.textOnly || $('without-reference').checked;
    $('token').value = '';
  }
  await api('generer', body);
  await monitor();
  if (!comparison && !selected.allThemes) await refreshImages();
}, 'submit');

(async () => {
  try {
    [profiles, engines] = await Promise.all([api('profils'), api('moteurs')]);
    options($('engine'), Object.entries(engines).map(([id, engine]) => [id, engine.name]));
    options($('profile'), Object.entries(profiles).map(([id, config]) => [id, config.name]));
    if ('ecole-quebec' in profiles) $('profile').value = 'ecole-quebec';
    $('profile').dispatchEvent(new Event('change'));
    if ((await api('etat')).active) await monitor();
  } catch (error) { report(error); }
})();
