"""Génération de visuels par lots avec compteur local partagé."""
import base64
from contextlib import closing, contextmanager
import csv
from dataclasses import dataclass
import hashlib
import html
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

MODEL = '@cf/black-forest-labs/flux-2-klein-4b'
WIDTH, HEIGHT = 1024, 768
LIMIT = 4800
UNIT_USD = 0.001207  # 4 tuiles de sortie + au plus 1 tuile d'entrée
STYLE = ('Illustration éditoriale aux aplats mats, contours arrondis et léger grain de papier. '
         'Contraste lisible à petite taille, formes simples, lumière douce.')
KEY = re.compile(r'[a-z0-9-]{1,64}')
OVERRIDE_FIELDS = ('theme', 'cours_id', 'slot', 'prompt')


@dataclass(frozen=True)
class Job:
    theme: str
    discipline: str
    course: str
    title: str
    slot: str
    alt: str
    prompt: str
    existing: bool

    @property
    def key(self):
        return f'{self.theme}/{self.discipline}/{self.course}/{self.slot}'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def read_overrides(path):
    if not path.is_file():
        return {}
    with path.open(encoding='utf-8-sig', newline='') as stream:
        sample = stream.readline()
        stream.seek(0)
        rows = csv.DictReader(stream, delimiter=';' if sample.count(';') > sample.count(',') else ',')
        if not set(OVERRIDE_FIELDS).issubset(rows.fieldnames or []):
            raise ValueError(f'{path.name} doit avoir les colonnes ' + ', '.join(OVERRIDE_FIELDS))
        overrides = {}
        for line, row in enumerate(rows, 2):
            theme, course, slot, prompt = ((row.get(field) or '').strip() for field in OVERRIDE_FIELDS)
            key = (theme, course, slot)
            if not all(KEY.fullmatch(part) for part in key) or not prompt or key in overrides:
                raise ValueError(f'{path.name}, ligne {line} : identifiants, doublon ou prompt invalide.')
            overrides[key] = prompt
        return overrides


def make_prompt(theme, palette, scene, style=STYLE, frame=''):
    return (
        f'{style}\nUnivers : {theme["name"]}. {theme.get("intro", "")}\n'
        f'Palette dominante : {palette}.\nScène à illustrer : {scene}\n'
        + (f'Contexte pour les décors et accessoires : {frame}\n' if frame else '')
        + 'Une seule image horizontale 4:3. Sujet dégagé, cadré avec de la marge aux bords. '
          'Personnages fictifs libres de varier. Aucun texte, logo, filigrane, case ni montage.'
    )


def reference_prompt(theme, style, art_direction=STYLE):
    return (
        f'Crée UNE image carrée qui servira de référence de style pour une série d’illustrations. '
        f'Thème « {theme["name"]} ». {style["scene"]} '
        f'Palette dominante : {style["palette"]}. {art_direction} '
        'Composition aérée en trois plans, lumière diffuse, couleurs réparties naturellement, '
        'grandes formes lisibles. Garde le décor vide de personnages afin de servir de référence '
        'pour la palette, la matière et les contours. Une seule illustration, avec du dégagement '
        'aux bords. Aucun texte, chiffre, symbole d’interface, nuancier, logo ni filigrane.'
    )


def output_path(state, job):
    return state / 'lots' / job.theme / job.discipline / job.course / (job.slot + '.webp')


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp-' + secrets.token_hex(6))
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def write_plan(state, theme, discipline, jobs):
    path = state / 'lots' / theme / ('PLAN-' + (discipline or 'toutes') + '.csv')
    stream = StringIO(newline='')
    writer = csv.writer(stream, delimiter=';')
    writer.writerow(['theme', 'discipline', 'cours_id', 'titre', 'slot', 'alt_propose',
                     'image_generique_existante', 'lot_deja_genere', 'sortie', 'prompt_final'])
    for j in jobs:
        dest = output_path(state, j)
        writer.writerow([j.theme, j.discipline, j.course, j.title, j.slot, j.alt, j.existing,
                         dest.is_file(), dest.relative_to(state).as_posix(), j.prompt])
    atomic_write(path, stream.getvalue().encode('utf-8-sig'))
    return path


def write_gallery(state, theme, discipline, jobs):
    path = state / 'lots' / theme / ('REVUE-' + (discipline or 'toutes') + '.html')
    cards = []
    for job in jobs:
        dest = output_path(state, job)
        if not dest.is_file():
            continue
        src = Path(os.path.relpath(dest, path.parent)).as_posix()
        caption = f'{job.course} · {job.slot} · {job.title}'
        if job.theme != theme:
            caption = f'{job.theme} · {caption}'
        caption = html.escape(caption)
        cards.append(f'<figure><a href="{src}"><img loading="lazy" src="{src}" alt="{caption}"></a>'
                     f'<figcaption>{caption}</figcaption></figure>')
    page = ('<!doctype html><html lang="fr"><meta charset="utf-8"><title>Atelier Images · Revue</title>'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<style>body{font:16px system-ui;margin:2rem;background:#faf6ed;color:#183630}'
            'main{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(min(250px,100%),1fr))}'
            'figure{margin:0;background:white;padding:.65rem;border-radius:.5rem}'
            'img{width:100%;height:auto;display:block}figcaption{margin-top:.5rem}</style>'
            f'<h1>Atelier Images · {len(cards)} images à revoir</h1>'
            '<p>Cliquer sur une image pour ouvrir le fichier individuel.</p>'
            '<main>' + ''.join(cards) + '</main></html>')
    atomic_write(path, page.encode('utf-8'))
    return path


@contextmanager
def keep_awake(enabled):
    if not enabled or os.name != 'nt':
        yield
        return

    import ctypes
    set_state = ctypes.windll.kernel32.SetThreadExecutionState
    set_state.argtypes = [ctypes.c_uint]
    set_state.restype = ctypes.c_uint
    continuous = 0x80000000
    applied = set_state(continuous | 0x00000001)
    try:
        yield
    finally:
        if applied:
            set_state(continuous)


@contextmanager
def exclusive_run(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if not stream.tell():
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError('Une génération est déjà ouverte pour cet utilisateur.') from None
        # Fermer le descripteur libère le verrou même après une exception.
        yield


def open_ledger(path):
    db = sqlite3.connect(path)
    db.execute('''CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY, job TEXT NOT NULL, prompt_sha TEXT NOT NULL,
        status TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    return db


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def cloudflare_image(account, token, prompt, reference):
    boundary = 'ekole-' + secrets.token_hex(16)
    parts = []
    for name, value in (('prompt', prompt), ('width', str(WIDTH)), ('height', str(HEIGHT))):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                     f'{value}\r\n'.encode('utf-8'))
    if reference:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="input_image_0"; '
                     f'filename="reference.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode('ascii'))
        parts.extend((reference, b'\r\n'))
    parts.append(f'--{boundary}--\r\n'.encode('ascii'))
    request = Request(f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{MODEL}',
                      data=b''.join(parts), headers={'Authorization': 'Bearer ' + token,
                      'Content-Type': 'multipart/form-data; boundary=' + boundary}, method='POST')
    with build_opener(NoRedirect()).open(request, timeout=120) as response:
        data = response.read(16 * 1024 * 1024 + 1)
        is_json = response.headers.get_content_type() == 'application/json'
    if len(data) > 16 * 1024 * 1024:
        raise ValueError('Réponse image trop volumineuse.')
    if is_json:
        payload = json.loads(data)
        result = payload.get('result') or {}
        if not payload.get('success', True) or not isinstance(result.get('image'), str):
            raise ValueError('Cloudflare n’a pas renvoyé d’image dans la réponse.')
        return base64.b64decode(result['image'], validate=True)
    return data


def prepare_reference(state, theme, image_module):
    ref_dir = state / 'references'
    paths = [ref_dir / (theme + ext) for ext in ('.png', '.jpg', '.jpeg', '.webp')]
    candidates = [path for path in paths if path.is_file()]
    if len(candidates) != 1:
        raise ValueError(f'Dépose exactement une référence {theme}.png, .jpg ou .webp dans {ref_dir}.')
    with image_module.open(candidates[0]) as image:
        if image.width * image.height > 20_000_000:
            raise ValueError('Référence trop grande (20 mégapixels maximum).')
        image.thumbnail((512, 512), image_module.Resampling.LANCZOS)
        encoded = BytesIO()
        image.convert('RGB').save(encoded, format='JPEG', quality=92)
    return encoded.getvalue()


def generate(db, state, jobs, account, token, reference, image_module, progress=print, local_generator=None,
             stop_requested=lambda: False):
    for i, job in enumerate(jobs, 1):
        if stop_requested():
            return False
        progress(f'[{i}/{len(jobs)}] {job.key}')
        prompt = job.prompt
        if reference:
            prompt += ('\nPrendre l’image 0 comme référence pour les contours, '
                       'la texture et la lumière. Composer librement la nouvelle scène.')
        # Réserver avant la requête. Une interruption ou une réponse ambiguë reste comptabilisée.
        if db is not None:
            with db:
                attempt = db.execute('INSERT INTO attempts (job, prompt_sha, status) VALUES (?, ?, ?)',
                                     (job.key, hashlib.sha256(prompt.encode() + (reference or b'')).hexdigest(),
                                      'reserve')).lastrowid
        try:
            data = (local_generator(prompt) if local_generator else
                    cloudflare_image(account, token, prompt, reference))
            with image_module.open(BytesIO(data)) as image:
                if image.size != (WIDTH, HEIGHT):
                    raise ValueError(f'Format image reçu inattendu : {image.width} × {image.height}.')
                webp = BytesIO()
                image.convert('RGB').save(webp, format='WEBP', quality=89)
            path = output_path(state, job)
            atomic_write(path, webp.getvalue())
            atomic_write(path.with_suffix('.prompt-sha256'), hashlib.sha256(job.prompt.encode()).hexdigest().encode('ascii'))
        except HTTPError as error:
            error.close()
            if error.code == 429:
                raise ValueError('Quota ou limite de cadence Cloudflare atteint. Relance le même lot plus tard.') from None
            raise ValueError(f'Cloudflare a répondu HTTP {error.code}. Vérifie le compte et les droits du jeton, '
                             'puis relance le lot.') from None
        if db is not None:
            with db:
                db.execute("UPDATE attempts SET status = 'sauve' WHERE id = ?", (attempt,))
    return True
