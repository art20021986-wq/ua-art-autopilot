"""Build the narrow adapter from an exact local/private runtime source."""
import argparse,hashlib,pathlib
EXPECTED='6c750d0ffcfd3959413120905e46b8765049a2a207b77741d7fc5721a225c134'
def build(source,out):
 raw=pathlib.Path(source).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=EXPECTED:raise ValueError('Live source changed; re-read and review before building')
 text=raw.decode();anchor='        digest = hashlib.sha256(expected).digest()'
 if text.count(anchor)!=1:raise ValueError('Ambiguous insertion point')
 candidate=text.replace(anchor,"        from public_fields import verify_core_fields\n        verify_core_fields(fragment, card, catalog=(name == 'katalog.html'))\n        if name != 'katalog.html':\n            from public_media import verify_photo_structure\n            verify_photo_structure(fragment, card)\n"+anchor)
 compile(candidate,str(out),'exec')
 out=pathlib.Path(out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(candidate)
 return hashlib.sha256(candidate.encode()).hexdigest()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('output');a=p.parse_args();print(build(a.source,a.output))
