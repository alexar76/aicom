"""Fresh public gameplay, without admin login, SSH or existing player tokens.

The honest Playwright user-agent is classified by the game's existing
automationReason function and excluded from its player conversion funnel.
"""
from pathlib import Path
import asyncio, base64, hashlib, json, os, subprocess, time
from playwright.async_api import async_playwright

A=Path(__file__).resolve().parent
P=A.parents[2]/'PromoMaterials/blip/youtube-season-something-pinged'
R=P/'v17-fresh-gameplay'
M=R/'capture'
Q=A/'qa/capture'
G='https://pingblip.com'
SESSION=Path('/private/tmp/pingblip-fresh-filming-20261031.json')

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
        ua=f'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/{browser.version} Safari/537.36 Playwright PingBlipFilming/2026-10-31'
        context=await browser.new_context(viewport={'width':360,'height':640},device_scale_factor=3,is_mobile=True,has_touch=True,locale='en-US',color_scheme='dark',user_agent=ua)
        # Do not make any administrator request or use a pre-existing player.
        await context.route('**/api/admin/**',lambda route:route.abort())
        await context.route('**/api/auth/admin**',lambda route:route.abort())
        session=await context.request.post(G+'/api/session',data={'attribution':{'utm_source':'internal','utm_medium':'filming','utm_campaign':'fresh-2026-10-31'}})
        assert session.status==200
        save(Q/'session-created.json',{'at':time.time(),'httpStatus':session.status,'body':await session.json()})
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
        async def action(button,endpoint,name,require_ok=True):
            await button.scroll_into_view_if_needed();await page.wait_for_timeout(2000)
            await shot(name+'_before');mark(name+'_click')
            async with page.expect_response(lambda r:r.url.endswith(endpoint) and r.request.method=='POST',timeout=120000) as pending:
                await button.click(no_wait_after=True,timeout=30000)
            response=await pending.value;result=await response.json()
            save(Q/(name+'-result.json'),{'recordedAt':time.time(),'httpStatus':response.status,'result':result})
            mark(name+'_result');await context.storage_state(path=str(SESSION));os.chmod(SESSION,0o600)
            if require_ok:assert response.status==200 and result.get('ok'),(name,result.get('error'))
            else:assert response.status==200 and 'roster' in result,(name,result)
            await page.wait_for_timeout(6500);await shot(name+'_after')
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
            return data
        async def catch_city(city,lat,lon):
            await page.goto(G+'/map?lang=en',wait_until='domcontentloaded',timeout=90000)
            await page.wait_for_timeout(2500)
            try:await page.get_by_role('button',name='got it',exact=False).first.click(timeout=1200,no_wait_after=True)
            except Exception:pass
            fields=page.locator('input[type="number"]')
            await fields.nth(0).fill(str(lat));await fields.nth(1).fill(str(lon));await shot(city+'_coordinates')
            result=await action(page.get_by_role('button',name='scan',exact=False).first,'/api/scan',city+'_scan',False)
            candidate=next((row for row in result['roster'] if not row['owned']),None)
            assert candidate,'No unowned creature in this scan; keep the truthful result'
            card=page.locator('div.border').filter(has=page.locator('p.font-display',has_text=candidate['name'])).last
            button=card.get_by_role('button',name='catch',exact=False).first
            await button.scroll_into_view_if_needed();await page.wait_for_timeout(3500);await shot(city+'_candidate')
            caught=await action(button,'/api/catch',city+'_catch')
            assert not caught.get('already')
            await bench(city+'_bench');await page.wait_for_timeout(3000)
            return caught
        await cdp.send('Emulation.setDeviceMetricsOverride',{'width':360,'height':640,'deviceScaleFactor':3,'mobile':True})
        await cdp.send('Page.startScreencast',{'format':'jpeg','quality':92,'maxWidth':1080,'maxHeight':1920,'everyNthFrame':1})
        success=False
        try:
            await page.goto(G+'/?lang=en',wait_until='domcontentloaded',timeout=90000);await page.wait_for_timeout(3000)
            await shot('home')
            hatch=await action(page.get_by_role('button',name='get your pet',exact=False),'/api/hatch','hatch')
            assert not hatch.get('already')
            meet=page.locator('.pingblip-overlay').get_by_role('button',name='meet and feed',exact=False)
            await meet.wait_for(timeout=60000);await shot('hatch_reveal');await page.wait_for_timeout(4000)
            await meet.click(no_wait_after=True);await page.wait_for_url('**/bench**',timeout=30000)
            await bench('starter_bench')
            fed=await action(page.get_by_role('button',name='feed',exact=False).first,'/api/feed','starter_feed')
            assert fed['creature']['feedCount']==1
            await bench('starter_fed_bench')
            await action(page.get_by_role('button',name='claim house',exact=False).first,'/api/credits','house_claim')
            await bench('house_bench')
            caught=await catch_city('amsterdam',52.3676,4.9041)
            fed=await action(page.get_by_role('button',name='feed',exact=False).first,'/api/feed','caught_feed')
            assert fed['creature']['id']==caught['creature']['id'] and fed['creature']['feedCount']==1
            await bench('caught_fed_bench')
            await catch_city('tokyo',35.6762,139.6503)
            final=await bench('final_bench');assert len(final['creatures'])==3
            await page.wait_for_timeout(4500);success=True
        except Exception as exc:
            save(Q/'capture-error.json',{'type':type(exc).__name__,'message':str(exc)[:1000]})
            await page.screenshot(path=str(M/'error.png'))
            raise
        finally:
            mark('end');await cdp.send('Page.stopScreencast')
            if tasks:await asyncio.gather(*tasks,return_exceptions=True)
            await browser.close()
            save(Q/'capture-summary.json',{'completed':success,'recordedAtUtc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'frames':len(frames),'freshSession':True,'noAdminAccess':True})
            if frames:encode()

if __name__=='__main__':asyncio.run(main())
