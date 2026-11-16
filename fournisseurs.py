"""Fournisseurs FLUX. Prix INDICATIFS en USD à ~1 MP, sans références.

Aucune clé API n'est persistée. Chaque téléchargement est limité à un hôte reconnu.
"""
import json
import re
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler

from generation import NoRedirect, cloudflare_image

PRICES = {
    # Hypothèses ~1 MP, génération texte seule. Estimation sans forfait/taxes.
    'cloudflare': (0.001148, 'Cloudflare : 4 tuiles de 512 px × 0,000287 $ (1024×768).'),
    'cf-klein-9b': (0.015, 'Cloudflare : 0,015 $ / premier mégapixel.'),
    'replicate-klein-4b': (0.001, 'Replicate : 0,001 $ / MP de sortie, sans référence.'),
    'replicate-klein-9b': (0.015, 'Replicate : 0,015 $ / MP de sortie, sans référence.'),
    'replicate-pro': (0.03, 'Replicate : 0,015 $ par appel + 0,015 $ / MP de sortie.'),
    'bfl-flux3-klein': (0.009, 'API BFL officielle : 0,009 $ par image au palier 1K.'),
}

REPLICATE_INPUTS = {
    'replicate-klein-4b': ('flux-2-klein-4b', {'output_megapixels': '1'}),
    'replicate-klein-9b': ('flux-2-klein-9b', {'output_megapixels': '1'}),
    'replicate-pro': ('flux-2-pro', {'resolution': '1 MP'}),
}
MAX_BYTES = 16 * 1024 * 1024
OPENER = build_opener(ProxyHandler({}), NoRedirect())


def request(url, token, *, provider, payload=None, timeout=120, max_bytes=MAX_BYTES):
    body = None if payload is None else json.dumps(payload).encode('utf-8')
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json'} if provider == 'replicate' else {'x-key': token}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    if provider == 'replicate' and body is not None:
        headers['Prefer'] = 'wait=60'
    try:
        with OPENER.open(Request(url, data=body, headers=headers), timeout=timeout) as r:
            data = r.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError('Réponse du fournisseur trop volumineuse.')
        return json.loads(data)
    except HTTPError as e:
        code = e.code
        e.close()
        raise ValueError(f'{provider} : erreur HTTP {code}. Vérifie le jeton, le crédit et les droits du modèle.') from None
    except (URLError, TimeoutError) as e:
        raise ValueError(f'{provider} est inaccessible : {e.reason if isinstance(e, URLError) else "délai dépassé"}.') from e


def download(url, provider):
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or parsed.username or parsed.password:
        raise ValueError('Lien de sortie du fournisseur non sûr.')
    if provider == 'replicate':
        allowed = host == 'replicate.delivery' or host.endswith('.replicate.delivery') or host == 'stream.replicate.com'
    else:
        allowed = (host.endswith('.bfl.ai') or host == 'bfl.ai' or host.endswith('.bfl-cdn.ai')
                   or host == 'bfl-cdn.ai' or (host.startswith('bfldelivery') and host.endswith('.blob.core.windows.net')))
    if not allowed:
        raise ValueError('Hôte de téléchargement non autorisé : ' + host)
    try:
        with OPENER.open(Request(url), timeout=90) as r:
            data = r.read(MAX_BYTES + 1)
    except (HTTPError, URLError) as e:
        raise ValueError(f'Impossible de télécharger l’image ({type(e).__name__}).') from e
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Image vide ou supérieure à 16 Mo.')
    return data


def replicate_image(engine, token, prompt, reference=None):
    slug, config = REPLICATE_INPUTS[engine]
    inp = {'prompt': prompt, 'aspect_ratio': '4:3', 'output_format': 'webp', **config}
    if reference:
        import base64
        # Les modèles officiels acceptent les références dans un tableau, pas via URL externe.
        field = 'input_images' if engine == 'replicate-pro' else 'images'
        inp[field] = ['data:image/jpeg;base64,' + base64.b64encode(reference).decode('ascii')]
    url = 'https://api.replicate.com/v1/models/black-forest-labs/' + slug + '/predictions'
    prediction = request(url, token, provider='replicate', payload={'input': inp})
    ident = prediction.get('id')
    if not isinstance(ident, str) or not re.fullmatch('[a-z0-9]{12,50}', ident):
        raise ValueError('Replicate : identifiant de prédiction manquant.')
    deadline = monotonic() + 900
    while monotonic() < deadline:
        status = prediction.get('status')
        output = prediction.get('output')
        if output:
            url = output[0] if isinstance(output, list) and len(output) == 1 else output
            if not isinstance(url, str):
                raise ValueError('Replicate : réponse image inattendue.')
            return download(url, 'replicate')
        if status in ('failed', 'canceled'):
            raise ValueError('Replicate : génération interrompue : ' + str(prediction.get('error', 'échec'))[:200])
        sleep(2)
        prediction = request('https://api.replicate.com/v1/predictions/' + ident, token, provider='replicate')
    raise ValueError('Replicate : génération non terminée après 15 minutes.')


def bfl_image(token, prompt, reference=None):
    import base64
    inp = {'prompt': prompt, 'aspect_ratio': '4:3', 'resolution': '1k', 'output_format': 'jpeg'}
    if reference:
        inp['images'] = [base64.b64encode(reference).decode('ascii')]
    prediction = request('https://api.bfl.ai/v1/flux-3-image-klein', token, provider='bfl', payload=inp)
    ident = prediction.get('id')
    if not isinstance(ident, str) or not re.fullmatch('[a-zA-Z0-9-]{8,100}', ident):
        raise ValueError('BFL : identifiant de génération manquant.')
    poll = prediction.get('polling_url')
    parsed = urlsplit(poll) if isinstance(poll, str) else None
    if not parsed or parsed.scheme != 'https' or parsed.hostname not in ('api.bfl.ai', 'api.us.bfl.ai', 'api.eu.bfl.ai'):
        raise ValueError('BFL : adresse de suivi invalide.')
    deadline = monotonic() + 900
    while monotonic() < deadline:
        sleep(2)
        result = request(poll, token, provider='bfl')
        if result.get('status') == 'Ready':
            url = (result.get('result') or {}).get('sample')
            if not isinstance(url, str):
                raise ValueError('BFL : adresse d’image absente.')
            return download(url, 'bfl')
        if result.get('status') in ('Error', 'Failed', 'Request Moderated', 'Content Moderated'):
            raise ValueError('BFL : tâche échouée : ' + str(result.get('status')))
    raise ValueError('BFL : génération non terminée après 15 minutes.')


def generate_cloud(engine, account, token, prompt, reference):
    if engine == 'cloudflare':
        return cloudflare_image(account, token, prompt, reference)
    if engine == 'cf-klein-9b':
        return cloudflare_image(account, token, prompt, reference, model='@cf/black-forest-labs/flux-2-klein-9b')
    if engine in REPLICATE_INPUTS:
        return replicate_image(engine, token, prompt, reference)
    if engine == 'bfl-flux3-klein':
        return bfl_image(token, prompt, reference)
    raise ValueError('Modèle cloud inconnu.')
