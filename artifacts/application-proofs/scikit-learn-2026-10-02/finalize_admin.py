import json,sys
sys.path.insert(0,'/tmp')
from pathlib import Path
import importlib.util
spec=importlib.util.spec_from_file_location('experiment','/tmp/openclass-real-issue-triage.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
manifest=m.load('manifest.json');ws=manifest['workspace']['id'];auth=m.token();out={}
for short,conf in manifest['projects'].items():
 base=f'/workspaces/{ws}/projects/{conf["project"]["id"]}'
 classifiers=m.control('GET',base+'/classifiers',auth=auth)
 if not classifiers:
  classifiers=[m.control('POST',base+'/classifiers',{'name':'Real maintainer issue taxonomy','slug':'real-maintainer-'+short,'description':m.INSTRUCTIONS,'unknown_fallback':True,'classes':[{'canonical_name':x['key'].lower(),'display_name':x['label']} for x in m.CHOICES]},auth=auth)]
 configs=m.control('GET',base+'/providers',auth=auth)['configs']
 if not configs:
  configs=[m.control('POST',base+'/providers',{'type':'openai-compatible','endpoint_ref':'OPENCLASS_DISCOVERY_BASE_URL','model':conf['model'],'timeout_seconds':60,'is_default':False},auth=auth)]
 out[short]={'classifiers':classifiers,'provider_cards':configs}
m.dump('admin-final-state.json',out)
print(json.dumps({'projects':list(out),'classifiers_present':all(x['classifiers'] for x in out.values()),'provider_cards_present':all(x['provider_cards'] for x in out.values())}))
