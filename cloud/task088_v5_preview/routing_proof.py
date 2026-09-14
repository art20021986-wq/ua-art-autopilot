"""Exact observed Production redirect proof; never import or execute its WSGI."""
import ast
import re

SOURCE_BINDINGS = {
    'observed_wsgi_config.py':'3067d39ec9c2eb976114afc6744e2c34b088a8414e98eb3e33e0a47c1849e308',
    'analitika_wsgi.py':'a73be46099596322dcd607ecadd56140d45483a5ad38f1c1a0a0e395cfc8bc94',
    'uaart_bridge_wsgi.py':'b0c93d88d67e8c285c1bffb40bd6f2e40c2779af7a01cebd6beab4beda685150',
}
STATIC_MAPPING = [{'url':'/video/','directory':'/home/Carix/video/'}]
PRODUCTION_LOCATION = 'https://www.uaart.com.ua/video/index.html'


def prove_legacy_home_redirect(captured_file, routes, routing_hash):
    # These are the three reviewed source versions. Unknown wrapper changes
    # require fresh route review; a replacement evidence JSON cannot waive it.
    from common import sha
    for name, expected in SOURCE_BINDINGS.items():
        if sha(captured_file(name)) != expected or routes['source_sha256'].get(name) != expected:
            raise ValueError('LEGACY_HOME_REDIRECT_SOURCE_DRIFT:' + name)
    if routes.get('static_mappings') != STATIC_MAPPING:
        raise ValueError('LEGACY_HOME_REDIRECT_STATIC_MAPPING_DRIFT')
    if routes.get('base_response') != {'status':302,'location':PRODUCTION_LOCATION}:
        raise ValueError('LEGACY_HOME_REDIRECT_OBSERVATION_REQUIRED')
    tree = ast.parse(captured_file('observed_wsgi_config.py'))
    cel = [node.value for node in tree.body if isinstance(node,ast.Assign)
           and any(isinstance(target,ast.Name) and target.id=='CEL' for target in node.targets)]
    if len(cel)!=1 or not isinstance(cel[0],ast.Constant) or cel[0].value != PRODUCTION_LOCATION:
        raise ValueError('LEGACY_HOME_REDIRECT_TARGET_DRIFT')
    # The reviewed wrappers pass /site/index.html to the unconditional base
    # redirect. Their exact file pins are part of the proof, not an inferred
    # wildcard rule installed in Preview.
    proof = {'source_sha256':dict(SOURCE_BINDINGS),'static_mappings':STATIC_MAPPING,
             'production_location':PRODUCTION_LOCATION,'routing_evidence_sha256':routing_hash,
             'route':'/site/index.html','classification':'UNSERVED_LEGACY_USES_BASE_WSGI_REDIRECT'}
    validate_legacy_home_redirect(proof)
    return proof


def validate_legacy_home_redirect(proof):
    if (type(proof) is not dict or set(proof) != {'source_sha256','static_mappings','production_location',
            'routing_evidence_sha256','route','classification'}
            or proof['source_sha256'] != SOURCE_BINDINGS or proof['static_mappings'] != STATIC_MAPPING
            or proof['production_location'] != PRODUCTION_LOCATION or proof['route'] != '/site/index.html'
            or proof['classification'] != 'UNSERVED_LEGACY_USES_BASE_WSGI_REDIRECT'
            or not re.fullmatch(r'[0-9a-f]{64}',proof['routing_evidence_sha256'])):
        raise ValueError('EXACT_LEGACY_HOME_REDIRECT_PROOF_REQUIRED')
