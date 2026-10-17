"""Read-only checks of the deployed visitor routes. Run after cutover."""
import concurrent.futures, json, pathlib, urllib.request
locales={'en':'What will you create?', 'ru':'Что создадим?', 'es':'¿Qué vas a crear?', 'fr':'Que souhaitez-vous créer ?', 'zh':'你想创建什么？'}
def check(lang):
    path='/' if lang=='en' else '/'+lang+'/'
    checks=[]
    urls=[('factory','https://magic-ai-factory.com/?lang='+lang,locales[lang]),
          ('marketing','https://modeldev.modelmarket.dev'+path,'https://magic-ai-factory.com/?lang='+lang),
          ('ecosystem','https://ecosystem.modelmarket.dev'+path,'https://edu.modelmarket.dev'+path+'ai-pays-ai/'),
          ('generator','https://magic-ai-factory.com/landing-page-generation/?lang='+lang,'journeyNext')]
    for role,url,expected in urls:
        with urllib.request.urlopen(url,timeout=90) as r:
            body=r.read().decode(); assert expected in body,(role,lang)
            checks.append({'role':role,'locale':lang,'url':url,'status':r.status,'content_ok':True})
    with urllib.request.urlopen('https://magic-ai-factory.com/landing-page-generation/api/config?lang='+lang,timeout=30) as r:
        cfg=json.load(r); assert cfg['ui_locale']==lang and cfg['strings']['next'] and cfg['llm_ready'] and not cfg['demo_mode']
        checks.append({'role':'generator-config','locale':lang,'llm_ready':True,'demo_mode':False})
    return checks
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    results=[item for group in pool.map(check,locales) for item in group]
pathlib.Path(__file__).with_name('live-checks.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print('PASS: 20 production pages and 5 real-generator configurations')
