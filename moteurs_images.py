"""Catalogue des moteurs et des tarifs indicatifs des services cloud."""
from pathlib import Path
from generation import KEY, read_json
from fournisseurs import PRICES

DIRECTORY = Path(__file__).resolve().with_name('moteurs')
BUILTINS = {
    'cloudflare': {'name':'Cloudflare · FLUX.2 Klein 4B (historique)', 'mode':'cloudflare', 'provider':'cloudflare', 'description':'Modèle Cloudflare existant, collection historique conservée. '},
    'cf-klein-9b': {'name':'Cloudflare · FLUX.2 Klein 9B', 'mode':'cloudflare', 'provider':'cloudflare', 'description':'Modèle 9B sur Workers AI, collection distincte.'},
    'replicate-klein-4b': {'name':'Replicate · FLUX.2 Klein 4B', 'mode':'replicate', 'provider':'replicate', 'description':'Compact, économique, facturation estimée par mégapixel.'},
    'replicate-klein-9b': {'name':'Replicate · FLUX.2 Klein 9B', 'mode':'replicate', 'provider':'replicate', 'description':'Plus de capacité, facturation au mégapixel.'},
    'replicate-pro': {'name':'Replicate · FLUX.2 Pro', 'mode':'replicate', 'provider':'replicate', 'description':'Qualité professionnelle sur Replicate.'},
    'bfl-flux3-klein': {'name':'BFL officiel · FLUX 3 Image Klein', 'mode':'bfl', 'provider':'bfl', 'description':'Ce modèle n’a pas de point de terminaison officiel vérifié sur Replicate/Cloudflare : connexion directe à l’API de Black Forest Labs.'},
    'comfy': {'name':'ComfyUI local · Workflow importé', 'mode':'upload', 'provider':'local', 'description':'Workflow API avec {{PROMPT}} et sortie SaveImage.'},
}


def catalogue():
    engines = {k: dict(v) for k,v in BUILTINS.items()}
    for key, (cost, pricing_note) in PRICES.items():
        engines[key]['unit_usd'] = cost
        engines[key]['pricing_note'] = pricing_note
    for profile in sorted(DIRECTORY.glob('*.profil.json')):
        key = profile.name.removesuffix('.profil.json')
        if not KEY.fullmatch(key) or key in engines:
            raise ValueError(f'Identifiant de moteur invalide : {key}')
        data = read_json(profile)
        filename = data['workflow']
        if Path(filename).name != filename or not filename.endswith('.workflow.json'):
            raise ValueError(f'Fichier de workflow invalide pour {key}.')
        engines[key] = {
            'name': data['nom'], 'mode': 'preset', 'provider':'local', 'description': data.get('description', ''),
            'workflow': filename, 'require_lora': data.get('require_lora', True),
        }
    return engines


def public_catalogue(engines):
    return {key: {k: value for k, value in engine.items() if k != 'workflow'}
            for key, engine in engines.items()}


def load_workflow(engine):
    return read_json(DIRECTORY / engine['workflow'])
