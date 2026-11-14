"""Site local de préparation et de génération de visuels."""
import base64
import hashlib
from collections import Counter
from contextlib import closing, nullcontext
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
from threading import Event, Lock, Thread
from urllib.parse import unquote, urlsplit
import webbrowser

import catalogues
from comfy import ComfyGenerator
import generation as gen
import revision
import moteurs_images

BASE = Path(__file__).resolve().parent
DATA = BASE / 'donnees'
WEB = BASE / 'web'
BUDGET = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'Ekole' / 'GenerationImages'
SESSION = secrets.token_urlsafe(32)
RUN_LOCK = Lock()
STOP_REQUESTED = Event()
ALL_THEMES = '.tous-les-themes'
ENGINES = moteurs_images.catalogue()
PALETTES = gen.read_json(BASE / 'palettes.json')
RUN = {'active': False, 'message': '', 'gallery': ''}


def link(path):
    return '/f/' + path.relative_to(DATA).as_posix()


def select_jobs(body, jobs):
    if body.get('allThemes') is True:
        return ALL_THEMES, '', jobs
    theme = body['theme']
    discipline = body.get('branch', '')
    selected = [j for j in jobs if j.theme == theme and (not discipline or j.discipline == discipline)]
    if not selected:
        raise ValueError('Cette branche ne contient aucun visuel.')
    return theme, discipline, selected


def load_jobs(body):
    palette = None if body.get('allThemes') is True else body.get('palette')
    state, themes, _, _, jobs = catalogues.load(body['profile'], body.get('root', ''), palette)
    return state, themes, jobs


def branch(body):
    state, _, jobs = load_jobs(body)
    return state, *select_jobs(body, jobs)


def empty_counts():
    return {'total': 0, 'done': 0, 'pending': 0}


def image_stats(state, themes, jobs):
    stats = {**empty_counts(), 'themes': {}}
    for job in jobs:
        theme = stats['themes'].get(job.theme)
        if theme is None:
            theme = {**empty_counts(), 'name': themes[job.theme]['name'], 'branches': {}}
            stats['themes'][job.theme] = theme
        branch_counts = theme['branches'].get(job.discipline)
        if branch_counts is None:
            branch_counts = theme['branches'][job.discipline] = empty_counts()
        status = 'done' if gen.output_path(state, job).is_file() else 'pending'
        for counts in (stats, theme, branch_counts):
            counts['total'] += 1
            counts[status] += 1
    return stats


def catalogue_stats(body):
    return image_stats(*load_jobs(body))


def info(body):
    state, themes, styles, art, jobs = catalogues.load(body['profile'], body.get('root', ''))
    counts = Counter((j.theme, j.discipline) for j in jobs)
    text_only = catalogues.profiles()[body['profile']]['adapter'] == 'kristals-quebec'
    universes = gen.read_json(BASE / 'univers-visuels-quebec.json') if text_only else {}
    references = {}
    for tid, theme in themes.items():
        colors = catalogues.theme_palette(styles[tid])
        if text_only:
            prompt = catalogues.quebec_direction(theme, styles[tid], universes) + '\n\n' + art
        else:
            reference_style = {**styles[tid], 'palette': ', '.join(colors)}
            reference_style['scene'] = catalogues.without_color_instructions(reference_style['scene'])
            prompt = gen.reference_prompt(catalogues.neutral_theme(theme), reference_style,
                                          catalogues.without_color_instructions(art))
            gen.atomic_write(state / 'references' / f'{tid}.txt', prompt.encode('utf-8'))
        references[tid] = {'prompt': prompt, 'colors': colors, 'branches': {
            discipline: count for (theme_id, discipline), count in counts.items() if theme_id == tid
        }, 'name': theme['name'],
            'ready': any((state / 'references' / (tid + ext)).is_file()
                         for ext in ('.png', '.jpg', '.jpeg', '.webp'))}
    return {'themes': references, 'total': len(jobs), 'textOnly': text_only,
            'palettes': PALETTES, 'stats': image_stats(state, themes, jobs)}


def save_reference(body):
    state, theme, _, _ = branch(body)
    try:
        from PIL import Image
    except ImportError:
        raise ValueError('Installe Pillow avec py -3 -m pip install Pillow.') from None
    data = base64.b64decode(body['image'], validate=True)
    with Image.open(BytesIO(data)) as image:
        if image.width * image.height > 20_000_000:
            raise ValueError('Référence trop grande. Maximum de 20 mégapixels.')
        image.thumbnail((512, 512), Image.Resampling.LANCZOS)
        buf = BytesIO()
        image.convert('RGB').save(buf, format='JPEG', quality=92)
    folder = state / 'references'
    with RUN_LOCK:
        if RUN['active']:
            raise ValueError('Un lot est déjà en cours.')
        gen.atomic_write(folder / f'{theme}.jpg', buf.getvalue())
        for ext in ('.png', '.jpeg', '.webp'):
            (folder / (theme + ext)).unlink(missing_ok=True)
    return {'saved': True}


def generation_candidates(state, jobs, comparison=False, refresh=False):
    pending = []
    missing = set()
    for job in jobs:
        path = gen.output_path(state, job)
        if not path.is_file():
            missing.add(job.key)
        elif comparison or (refresh and not revision.approval_path(state, job).is_file()):
            try:
                signature = path.with_suffix('.prompt-sha256').read_text(encoding='ascii')
            except (FileNotFoundError, UnicodeError):
                signature = ''
            if signature != hashlib.sha256(job.prompt.encode()).hexdigest():
                pending.append(job)
            continue
        else:
            continue
        pending.append(job)
    return pending, missing


def write_review(state, theme, discipline, jobs, refresh=False):
    comparisons = {}
    if theme != ALL_THEMES:
        for engine in ENGINES:
            sandbox = state / 'comparaisons' / engine
            if any(gen.output_path(sandbox, j).is_file() for j in jobs):
                comparisons[engine] = link(gen.write_gallery(sandbox, theme, discipline, jobs))
    pending, missing = generation_candidates(state, jobs, refresh=refresh)
    return {
        'comparisons': comparisons,
        'plan': link(gen.write_plan(state, theme, discipline, jobs)),
        'gallery': link(gen.write_gallery(state, theme, discipline, jobs)),
        'total': len(jobs),
        'pending': len(missing),
        'refreshable': len(pending) - len(missing)
    }


def plan(body):
    return write_review(*branch(body), refresh=body.get('refresh') is True)


def review_images(body):
    if body.get('allThemes') is True:
        raise ValueError('Choisis un thème pour réviser les images.')
    state, _, _, jobs = branch(body)
    config = catalogues.profiles()[body['profile']]
    root = None
    if config['adapter'] == 'kristals-quebec':
        custom = body.get('root', '').strip()
        root = Path(custom) if custom else BASE.parent / config['source']
    action = body.get('action')
    if action:
        if action not in ('valider', 'integrer', 'ecarter', 'supprimer') or (action == 'integrer' and root is None):
            raise ValueError('Action indisponible pour ce profil.')
        with RUN_LOCK:
            if RUN['active']:
                raise ValueError('Attends la fin du lot en cours.')
            with gen.exclusive_run(BUDGET / 'generation.lock'):
                return revision.apply(state, jobs, body.get('keys'), action, root)
    rows = revision.list_images(state, jobs, root)
    for row in rows:
        row['url'] = link(row.pop('path'))
    return {'images': rows, 'integration': root is not None}


def generation_worker(state, theme, discipline, jobs, limit, account, token, reference,
                      image_module, local_generator, comparison, engine, catalogue_jobs, catalogue_themes,
                      refresh=False):
    output = state / 'comparaisons' / engine if comparison else state
    candidates = jobs[:limit] if comparison else jobs
    message = 'Lot terminé.'

    def count_saved(job):
        if job.key not in missing:
            return
        with RUN_LOCK:
            stats = RUN['stats']
            theme_counts = stats['themes'][job.theme]
            branch_counts = theme_counts['branches'][job.discipline]
            for counts in (stats, theme_counts, branch_counts):
                counts['done'] += 1
                counts['pending'] -= 1

    try:
        with gen.exclusive_run(BUDGET / 'generation.lock'), gen.keep_awake(theme == ALL_THEMES):
            ledger = nullcontext(None) if local_generator else closing(gen.open_ledger(BUDGET / 'budget.sqlite3'))
            with ledger as db:
                left = len(jobs) if db is None else max(0, gen.LIMIT - db.execute('SELECT count(*) FROM attempts').fetchone()[0])
                pending, missing = generation_candidates(output, candidates, comparison, refresh)
                selected = pending[:min(limit or len(pending), left)]
                if selected and ENGINES[engine]['mode'] == 'preset':
                    local_generator.check_assets()
                completed = gen.generate(db, output, selected, account, token, reference, image_module,
                             progress=lambda msg: RUN.update(message=msg),
                             local_generator=local_generator, stop_requested=STOP_REQUESTED.is_set,
                             on_saved=None if comparison else count_saved)
                if not completed:
                    message = 'Lot arrêté. Les images terminées sont disponibles dans la galerie.'
                elif not left:
                    message = 'Plafond local de 4 800 appels atteint.'
                elif not pending:
                    message = 'Toutes les images de cette branche sont déjà présentes.'
                elif len(selected) == left and len(selected) < len(pending):
                    message = 'Lot partiel. Plafond local atteint.'
    except (OSError, ValueError) as error:
        message = str(error)
    except Exception as error:
        message = 'La génération a été interrompue (' + type(error).__name__ + ').'
    finally:
        try:
            RUN.update(write_review(state, theme, discipline, jobs, refresh))
        finally:
            stats = image_stats(state, catalogue_themes, catalogue_jobs)
            with RUN_LOCK:
                RUN.update(active=False, message=message, stats=stats)


def start(body):
    state, catalogue_themes, catalogue_jobs = load_jobs(body)
    theme, discipline, jobs = select_jobs(body, catalogue_jobs)
    limit = body['limit']
    comparison = body.get('comparison', False)
    refresh = body.get('refresh') is True and not comparison
    engine = body.get('engine', 'cloudflare')
    if engine not in ENGINES:
        raise ValueError('Moteur de génération inconnu.')
    account = token = ''
    local_generator = None
    if type(limit) is not int or not 0 <= limit <= gen.LIMIT:
        raise ValueError('Limite du lot invalide.')
    if comparison and not 1 <= limit <= 24:
        raise ValueError('Choisis entre 1 et 24 images en mode comparaison.')
    mode = ENGINES[engine]['mode']
    if theme == ALL_THEMES and (mode == 'cloud' or comparison):
        raise ValueError('Le lot de tous les thèmes utilise un moteur local hors mode comparaison.')
    if mode == 'preset':
        local_generator = ComfyGenerator(moteurs_images.load_workflow(ENGINES[engine]))
    elif mode == 'upload':
        local_generator = ComfyGenerator(body.get('workflow'))
    else:
        account, token = body['account'].strip(), body['token'].strip()
        if not re.fullmatch(r'[a-fA-F0-9]{32}', account):
            raise ValueError('L’identifiant Cloudflare doit avoir 32 caractères hexadécimaux.')
        if not token or len(token) > 512 or '\n' in token or '\r' in token:
            raise ValueError('Jeton Cloudflare invalide.')
    try:
        from PIL import Image
    except ImportError:
        raise ValueError('Installe Pillow avec py -3 -m pip install Pillow.') from None
    with RUN_LOCK:
        if RUN['active']:
            raise ValueError('Un lot est déjà en cours.')
        text_only = catalogues.profiles()[body['profile']]['adapter'] == 'kristals-quebec'
        reference = None if local_generator or text_only or body.get('withoutReference') else gen.prepare_reference(state, theme, Image)
        STOP_REQUESTED.clear()
        RUN.update(active=True, message='Préparation du lot…', gallery='', plan='', comparisons={},
                   stats=image_stats(state, catalogue_themes, catalogue_jobs))
        Thread(target=generation_worker,
               args=(state, theme, discipline, jobs, limit, account, token, reference, Image,
                     local_generator, comparison, engine, catalogue_jobs, catalogue_themes, refresh),
               daemon=True).start()
    return {'started': True}


def stop_generation(_body):
    with RUN_LOCK:
        if RUN['active']:
            STOP_REQUESTED.set()
        return {'stopping': RUN['active']}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def send(self, status, mime, data):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; img-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def json(self, status, obj):
        self.send(status, 'application/json; charset=utf-8', json.dumps(obj, ensure_ascii=False).encode())

    def local(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

    def do_GET(self):
        if not self.local():
            return self.json(403, {'error': 'Accès local uniquement.'})
        route = urlsplit(self.path).path
        if route == '/':
            text = (WEB / 'index.html').read_text(encoding='utf-8').replace('SESSION_TOKEN', SESSION)
            return self.send(200, 'text/html; charset=utf-8', text.encode())
        if route == '/api/profils':
            return self.json(200, {key: {'name': config['nom'], 'adapter': config['adapter']}
                                   for key, config in catalogues.profiles().items()})
        if route == '/api/moteurs':
            return self.json(200, moteurs_images.public_catalogue(ENGINES))
        if route == '/api/etat':
            with RUN_LOCK:
                status = deepcopy(RUN)
                status['stopping'] = status['active'] and STOP_REQUESTED.is_set()
            return self.json(200, status)
        if route in ('/app.js', '/style.css'):
            path = WEB / route[1:]
        elif route.startswith('/f/'):
            path = (DATA / unquote(route[3:])).resolve()
            if not path.is_relative_to(DATA.resolve()):
                return self.json(404, {'error': 'Fichier absent.'})
            parts = path.relative_to(DATA.resolve()).parts
            production = len(parts) >= 4 and parts[1] == 'lots'
            comparison = (len(parts) >= 6 and parts[1] == 'comparaisons'
                          and parts[2] in ENGINES and parts[3] == 'lots')
            if path.suffix.lower() not in ('.webp', '.csv', '.html') or not (production or comparison):
                return self.json(404, {'error': 'Fichier absent.'})
        else:
            return self.json(404, {'error': 'Page absente.'})
        if not path.is_file():
            return self.json(404, {'error': 'Fichier absent.'})
        mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        self.send(200, mime + ('; charset=utf-8' if path.suffix in ('.html', '.js', '.css', '.csv') else ''),
                  path.read_bytes())

    def do_POST(self):
        if (not self.local()
                or self.headers.get('Origin') != f'http://127.0.0.1:{self.server.server_port}'
                or not secrets.compare_digest(self.headers.get('X-Atelier-Session', ''), SESSION)):
            return self.json(403, {'error': 'Ouvre l’interface depuis le lanceur local.'})
        try:
            size = int(self.headers.get('Content-Length', 0))
            if not 0 < size <= 16 * 1024 * 1024:
                raise ValueError('Taille de requête invalide.')
            body = json.loads(self.rfile.read(size))
            operations = {'/api/charger': info, '/api/reference': save_reference,
                          '/api/plan': plan, '/api/generer': start,
                          '/api/revision': review_images, '/api/arreter': stop_generation,
                          '/api/statistiques': catalogue_stats}
            operation = operations.get(self.path)
            if not operation:
                return self.json(404, {'error': 'Action inconnue.'})
            self.json(200, operation(body))
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.json(400, {'error': str(error)})


if __name__ == '__main__':
    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        url = f'http://127.0.0.1:{server.server_port}/'
        print('Atelier Images ·', url, flush=True)
        webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
