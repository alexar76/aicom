"""Fresh public gameplay, using only our own previously created public filming profile.

The honest Playwright user-agent is classified by the game's existing
automationReason function and excluded from its player conversion funnel.
"""
from pathlib import Path
import asyncio, base64, hashlib, json, os, subprocess, time
from playwright.async_api import async_playwright

A=Path(__file__).resolve().parent
P=A.parents[2]/'PromoMaterials/blip/youtube-season-something-pinged'
R=P/'v19-next-meals'
M=R/'capture-scan'
Q=A/'qa/capture-scan'
G='https://pingblip.com'
ORIGINAL_SESSION=Path('/private/tmp/pingblip-fresh-filming-20261102-b.json')
SESSION=Path('/private/tmp/pingblip-fresh-filming-20261102-scan.json')

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')

def encode():
    marks=json.loads((Q/'marks-absolute.json').read_text())
    frames=[json.loads(line) for line in (Q/'frame-times.jsonl').read_text().splitlines()]
    frames=sorted((f for f in frames if f['timestamp']<=marks['end']),key=lambda x:x['timestamp'])
    assert frames
    start=frames[0]['timestamp']
    save(Q/'marks.json',{k:round(v-start,3) for k,v in marks.items()})
    lines=['ffconcat version 1.0']
    for i,f in enumerate(frames):
        end=frames[i+1]['timestamp'] if i+1<len(frames) else marks['end']
        lines.extend([f"file '{M/'frames'/f['file']}'",f'duration {max(.001,end-f["timestamp"]):.4f}'])
    lines.append(f"file '{M/'frames'/frames[-1]['file']}'")
    concat=Q/'frames.ffconcat';concat.write_text('\n'.join(lines)+'\n')
    subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(concat),'-vf','scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p','-c:v','libx264','-crf','16','-preset','veryfast','-threads','2',str(M/'raw-vertical.mp4')],check=True)
    print('ENCODED',len(frames),'fresh frames',flush=True)

async def main():
    assert not M.exists(),'Preserve existing footage; inspect before resuming'
    (M/'frames').mkdir(parents=True);Q.mkdir(parents=True)
    marks,frames,tasks={},[],set()
    def mark(name):
        marks[name]=time.time();save(Q/'marks-absolute.json',marks)
    async with async_playwright() as p:
        browser=await p.chromium.launch(channel='chrome',headless=True,args=['--force-device-scale-factor=3'])
        ua=f'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/{browser.version} Safari/537.36 Playwright PingBlipFilming/2026-11-02'
        context=await browser.new_context(viewport={'width':360,'height':640},device_scale_factor=3,is_mobile=True,has_touch=True,locale='en-US',color_scheme='dark',user_agent=ua,storage_state=str(ORIGINAL_SESSION))
        # Only resume our own documented public filming profile; never obtain admin credentials.
        await context.route('**/api/admin/**',lambda route:route.abort())
        await context.route('**/api/auth/admin**',lambda route:route.abort())
        initial_response=await context.request.get(G+'/api/bench')
        assert initial_response.status==200
        initial=await initial_response.json()
        prior=json.loads((A/'qa/capture/final_bench.json').read_text())
        assert not initial.get('anonymous') and {c['id'] for c in initial['creatures']}=={c['id'] for c in prior['creatures']},'Not our documented filming bench'
        save(Q/'initial-owned.json',initial)
        session=await context.request.post(G+'/api/session',data={'attribution':{'utm_source':'internal','utm_medium':'filming','utm_campaign':'fresh-2026-11-02'}})
        assert session.status==200
        save(Q/'session-resumed.json',{'at':time.time(),'httpStatus':session.status,'ownDocumentedProfile':True,'newProfileCreated':False})
        source=A.parents[1]/'pingblip/web/src/lib/player-event-core.ts'
        save(Q/'automation-classification.json',{'userAgent':ua,'expectedClass':'automation-ua','source':str(source),'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'method':'Existing public session endpoint records recognized HeadlessChrome / Playwright UA; no signed test/admin marker is used.'})
        await context.storage_state(path=str(SESSION));os.chmod(SESSION,0o600)
        page=await context.new_page();cdp=await context.new_cdp_session(page)
        async def on_frame(ev):
            ts=ev['metadata'].get('timestamp') or time.time();path=M/'frames'/f'{len(frames):06d}.jpg'
            path.write_bytes(base64.b64decode(ev['data']));frames.append((ts,path))
            with (Q/'frame-times.jsonl').open('a') as out:out.write(json.dumps({'timestamp':ts,'file':path.name})+'\n')
            try:await cdp.send('Page.screencastFrameAck',{'sessionId':ev['sessionId']})
            except Exception:pass
        def dispatch(ev):
            task=asyncio.create_task(on_frame(ev));tasks.add(task);task.add_done_callback(tasks.discard)
        cdp.on('Page.screencastFrame',dispatch)
        async def shot(name):
            mark(name);await page.screenshot(path=str(M/(name+'.png')))
        async def action(button,endpoint,name,require_ok=True,method='POST'):
            await button.scroll_into_view_if_needed();await page.wait_for_timeout(2000)
            await shot(name+'_before');mark(name+'_click')
            async with page.expect_response(lambda r:r.url.endswith(endpoint) and r.request.method==method,timeout=120000) as pending:
                await button.click(no_wait_after=True,timeout=30000)
            response=await pending.value;result=await response.json()
            save(Q/(name+'-result.json'),{'recordedAt':time.time(),'httpStatus':response.status,'result':result})
            mark(name+'_result');await context.storage_state(path=str(SESSION));os.chmod(SESSION,0o600)
            if require_ok:assert response.status==200 and result.get('ok'),(name,result.get('error'))
            else:assert response.status==200 and 'roster' in result,(name,result)
            await page.wait_for_timeout(3500 if method=='PATCH' else 6500);await shot(name+'_after')
            print('RECORDED',name,result.get('species',{}).get('name',''),flush=True)
            return result
        async def bench(name):
            await page.goto(G+'/bench?lang=en',wait_until='domcontentloaded',timeout=90000)
            await page.locator('canvas').first.wait_for(timeout=60000)
            await page.wait_for_timeout(5500)
            try:await page.get_by_role('button',name='got it',exact=False).first.click(timeout=1200,no_wait_after=True)
            except Exception:pass
            await shot(name)
            data=await (await context.request.get(G+'/api/bench')).json();save(Q/(name+'.json'),data)
            await page.wait_for_timeout(4500)
            return data
        async def select_and_feed(key,species_id):
            pet=next(c for c in initial['creatures'] if c['speciesId']==species_id)
            assert pet['feedReady']
            await action(page.get_by_role('button',name=pet['species']['name'],exact=True),'/api/bench',key+'_select',method='PATCH')
            await page.locator('h1').scroll_into_view_if_needed();await page.wait_for_timeout(2000)
            await shot(key+'_bench_before')
            before=await (await context.request.get(G+'/api/bench')).json()
            prev=next(c for c in before['creatures'] if c['id']==pet['id']);save(Q/(key+'-before.json'),prev)
            await page.wait_for_timeout(4000)
            fed=await action(page.get_by_role('button',name='feed',exact=False).first,'/api/feed',key+'_feed')
            assert fed['creature']['id']==pet['id'] and fed['creature']['feedCount']==prev['feedCount']+1
            await page.locator('h1').scroll_into_view_if_needed();await page.wait_for_timeout(1800)
            after=await (await context.request.get(G+'/api/bench')).json();pet_after=next(c for c in after['creatures'] if c['id']==pet['id'])
            assert not pet_after['asleep'];save(Q/(key+'-after.json'),pet_after)
            await shot(key+'_bench_after');await page.wait_for_timeout(4500)
        async def catch_city(city,lat,lon):
            await page.goto(G+'/map?lang=en',wait_until='domcontentloaded',timeout=90000);await page.wait_for_timeout(2500)
            try:await page.get_by_role('button',name='got it',exact=False).first.click(timeout=2500,no_wait_after=True)
            except Exception:pass
            fields=page.locator('input[type="number"]');await fields.nth(0).fill(str(lat));await fields.nth(1).fill(str(lon));await shot(city+'_coordinates')
            candidate=None
            for layer in ['weather','air']:
                if layer!='weather':await page.get_by_role('button',name=layer,exact=True).click()
                key=city+'_scan_'+layer
                result=await action(page.get_by_role('button',name='scan',exact=False).first,'/api/scan',key,False)
                candidate=next((row for row in result['roster'] if not row['owned']),None)
                if candidate:break
            assert candidate,'No unowned creature in two real scans; preserve outcomes before choosing another scene'
            save(Q/(city+'-choice.json'),{'scanKey':key,'layer':layer,'speciesId':candidate['id'],'name':candidate['name']})
            card=page.locator('div.border').filter(has=page.locator('p.font-display',has_text=candidate['name'])).last
            button=card.get_by_role('button',name='catch',exact=False).first
            await button.scroll_into_view_if_needed();await page.wait_for_timeout(3500);await shot(city+'_candidate')
            caught=await action(button,'/api/catch',city+'_catch');assert not caught.get('already')
            await bench(city+'_bench')
            return caught
        await cdp.send('Emulation.setDeviceMetricsOverride',{'width':360,'height':640,'deviceScaleFactor':3,'mobile':True})
        await cdp.send('Page.startScreencast',{'format':'jpeg','quality':92,'maxWidth':1080,'maxHeight':1920,'everyNthFrame':1})
        success=False
        try:
            mark('recording_start')
            await page.goto(G+'/map?lang=en',wait_until='domcontentloaded',timeout=90000)
            await page.wait_for_timeout(2500)
            fields=page.locator('input[type="number"]')
            await fields.nth(0).fill('41.3874');await fields.nth(1).fill('2.1686')
            await shot('barcelona_coordinates')
            result=await action(page.get_by_role('button',name='scan',exact=False).first,'/api/scan','barcelona_scan_weather',False)
            candidate=next((r for r in result['roster'] if not r['owned']),result['roster'][0])
            card=page.locator('div.border').filter(has=page.locator('p.font-display',has_text=candidate['name'])).last
            await card.scroll_into_view_if_needed();await page.wait_for_timeout(3500)
            await shot('barcelona_roster_visible');await page.wait_for_timeout(9500)
            final=await bench('final_bench');assert len(final['creatures'])==5
            await page.wait_for_timeout(4500);success=True
        except Exception as exc:
            save(Q/'capture-error.json',{'type':type(exc).__name__,'message':str(exc)[:1000]})
            await page.screenshot(path=str(M/'error.png'))
            raise
        finally:
            mark('end');await cdp.send('Page.stopScreencast')
            if tasks:await asyncio.gather(*tasks,return_exceptions=True)
            await browser.close()
            save(Q/'capture-summary.json',{'completed':success,'recordedAtUtc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'frames':len(frames),'freshSession':True,'resumedOwnFilmingProfile':True,'newProfileCreated':False,'recordingStartUnix':marks['recording_start'],'noAdminAccess':True})
            if frames:encode()

if __name__=='__main__':asyncio.run(main())
