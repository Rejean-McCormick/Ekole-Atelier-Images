"""Client du serveur ComfyUI local et réutilisation d'un workflow de style."""
from copy import deepcopy
import json
from secrets import randbits
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from generation import NoRedirect

MARKER = '{{PROMPT}}'
BASE = 'http://127.0.0.1:8188'
MAX_IMAGE = 16 * 1024 * 1024


class ComfyGenerator:
    def __init__(self, workflow):
        if not isinstance(workflow, dict) or not workflow or not all(
            isinstance(node, dict) and isinstance(node.get('inputs'), dict)
            for node in workflow.values()
        ):
            raise ValueError('Charge un workflow ComfyUI exporté au format API.')
        outputs = [key for key, node in workflow.items() if node.get('class_type') == 'SaveImage']
        if len(outputs) != 1:
            raise ValueError('Le workflow doit contenir une seule sortie SaveImage.')
        self.output = outputs[0]
        connected = set()
        pending = [self.output]
        while pending:
            key = pending.pop()
            if key in connected:
                continue
            connected.add(key)
            pending.extend(value[0] for value in workflow[key]['inputs'].values()
                           if isinstance(value, list) and len(value) == 2
                           and isinstance(value[0], str) and value[0] in workflow
                           and type(value[1]) is int)
        slots = [(key, field) for key in connected for field, value in workflow[key]['inputs'].items()
                 if isinstance(value, str) and MARKER in value]
        if len(slots) != 1:
            raise ValueError('Inscris {{PROMPT}} dans un seul champ de texte relié à SaveImage.')
        if not any('lora' in workflow[key].get('class_type', '').lower()
                   and workflow[key]['inputs'].get('lora_name')
                   and any(workflow[key]['inputs'].get(field, 0) for field in ('strength_model', 'strength_clip'))
                   for key in connected):
            raise ValueError('Relie à la sortie un LoRA de style actif dans le workflow.')
        self.workflow = workflow
        self.slot = slots[0]
        self.connected = connected
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, route, body=None, max_bytes=2 * 1024 * 1024):
        request = Request(BASE + route, data=None if body is None else json.dumps(body).encode('utf-8'),
                          headers={'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=20) as response:
                data = response.read(max_bytes + 1)
        except HTTPError as error:
            error.close()
            raise ValueError(f'ComfyUI a répondu HTTP {error.code}. Vérifie les nœuds et les modèles dans ComfyUI.') from None
        except (URLError, TimeoutError) as error:
            raise ValueError('ComfyUI est inaccessible sur 127.0.0.1:8188. Lance-le et réessaie.') from error
        if len(data) > max_bytes:
            raise ValueError('Réponse ComfyUI trop volumineuse.')
        return data

    def check_assets(self):
        loaders = {
            'CheckpointLoaderSimple': ('ckpt_name',), 'UNETLoader': ('unet_name',),
            'DualCLIPLoader': ('clip_name1', 'clip_name2'), 'CLIPLoader': ('clip_name',),
            'VAELoader': ('vae_name',), 'LoraLoader': ('lora_name',),
            'LoraLoaderModelOnly': ('lora_name',),
        }
        missing = set()
        schema = {}
        for key in self.connected:
            node = self.workflow[key]
            cls = node['class_type']
            if cls not in loaders:
                continue
            if cls not in schema:
                info = json.loads(self.request('/object_info/' + cls)).get(cls)
                if not info:
                    raise ValueError(f'Nœud ComfyUI indisponible : {cls}.')
                schema[cls] = info['input']['required']
            for field in loaders[cls]:
                filename = node['inputs'].get(field)
                definition = schema[cls].get(field, [])
                if definition and isinstance(definition[0], list):
                    if filename not in definition[0]:
                        missing.add(filename)
                elif definition and definition[0] == 'COMBO':
                    options = definition[1].get('options')
                    if isinstance(options, list) and filename not in options:
                        missing.add(filename)
        if missing:
            raise ValueError('Fichiers absents dans ComfyUI : ' + ', '.join(sorted(missing)))

    def __call__(self, prompt):
        workflow = deepcopy(self.workflow)
        node, field = self.slot
        workflow[node]['inputs'][field] = workflow[node]['inputs'][field].replace(MARKER, prompt)
        workflow[self.output]['inputs']['filename_prefix'] = 'atelier-images'
        for key in self.connected:
            inputs = workflow[key]['inputs']
            for name in ('seed', 'noise_seed'):
                if type(inputs.get(name)) is int:
                    inputs[name] = randbits(48)
        submitted = json.loads(self.request('/prompt', {'prompt': workflow}))
        job = submitted.get('prompt_id', '')
        if not isinstance(job, str) or not job or not all(c.isalnum() or c == '-' for c in job):
            raise ValueError('ComfyUI n’a pas accepté le workflow.')
        deadline = monotonic() + 600
        while monotonic() < deadline:
            result = json.loads(self.request('/history/' + job)).get(job, {})
            if result:
                images = result.get('outputs', {}).get(self.output, {}).get('images', [])
                if len(images) != 1 or result.get('status', {}).get('status_str') == 'error':
                    raise ValueError('ComfyUI doit produire une image par scène. Vérifie le lot et les erreurs dans ComfyUI.')
                image = images[0]
                query = urlencode({'filename': image['filename'], 'subfolder': image.get('subfolder', ''),
                                   'type': 'output'})
                return self.request('/view?' + query, max_bytes=MAX_IMAGE)
            sleep(1)
        raise ValueError('ComfyUI n’a pas terminé après 10 minutes. Vérifie sa file avant de relancer.')
