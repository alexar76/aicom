import * as T from './vendor/three.module.min.js';

// A small, self-hosted WebGL sculpture. The narrative remains in ordinary accessible HTML.
class MachineScene extends HTMLElement {
  static observedAttributes = ['stage'];
  connectedCallback() {
    if (this.renderer) return;
    const atlas = this.getAttribute('mode') === 'atlas';
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    let renderer;
    try { renderer = new T.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' }); }
    catch { this.setAttribute('data-fallback', 'true'); return; }
    this.renderer = renderer;
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.6));
    renderer.setClearColor(0x000000, 0);
    renderer.toneMapping = T.ACESFilmicToneMapping;
    renderer.toneMappingExposure = atlas ? 1.5 : 1.35;
    renderer.domElement.setAttribute('aria-hidden', 'true');
    this.append(renderer.domElement);
    renderer.domElement.addEventListener('webglcontextlost', () => {
      this.stop?.(); this.removeAttribute('data-ready'); this.setAttribute('data-fallback', 'true');
      renderer.domElement.style.display = 'none';
    }, { once: true });
    const scene = new T.Scene(); this.scene = scene;
    const camera = new T.PerspectiveCamera(35, 1, .1, 100);
    camera.position.set(11, 9, 14); camera.lookAt(0, .6, 0);
    scene.add(new T.HemisphereLight(atlas ? 0xf3fff9 : 0xc2d7ef, 0x19232a, 2.3));
    const light = new T.DirectionalLight(0xffffff, 4); light.position.set(-5, 10, 6); scene.add(light);
    const rim = new T.PointLight(atlas ? 0x52d3a6 : 0xffb960, 110, 30); rim.position.set(4, 4, -4); scene.add(rim);
    const sculpture = new T.Group(); scene.add(sculpture);
    const metal = new T.MeshStandardMaterial({ color: atlas ? 0x244139 : 0x25323e, metalness: .75, roughness: .26 });
    const silver = new T.MeshStandardMaterial({ color: atlas ? 0xcbd9d1 : 0x8999a3, metalness: .7, roughness: .28 });
    const accent = atlas ? 0x13845f : 0xffb454;
    const glow = new T.MeshStandardMaterial({ color: accent, emissive: accent, emissiveIntensity: 1.6, metalness: .3, roughness: .24 });
    const dark = new T.MeshStandardMaterial({ color: atlas ? 0x4b655c : 0x101b25, metalness: .5, roughness: .4 });
    const mesh = (geometry, material, x=0, y=0, z=0, parent=sculpture) => {
      const m = new T.Mesh(geometry, material); m.position.set(x,y,z); parent.add(m); return m;
    };
    const box = (w,h,d,mat,x=0,y=0,z=0,parent=sculpture) => mesh(new T.BoxGeometry(w,h,d),mat,x,y,z,parent);
    const edge = (m, color=accent, opacity=.45) => {
      const line = new T.LineSegments(new T.EdgesGeometry(m.geometry),new T.LineBasicMaterial({color,transparent:true,opacity}));
      m.add(line);
    };
    const tracks = [], parts = [], pulses = [];
    if (!atlas) {
      // Four separated production decks: plan, code, verification, release.
      for (let level=0; level<4; level++) {
        const deck = new T.Group(); deck.position.y = level*1.14-1.25; sculpture.add(deck); parts.push(deck);
        const slab=box(5.7,.16,4.4,metal,0,0,0,deck); edge(slab,0x88a1b1,.35);
        box(5.2,.035,3.9,dark,0,.12,0,deck);
        for(let s=-1;s<=1;s+=2) {
          box(4.9,.035,.035,glow,0,.14,s*1.95,deck);
          for(let i=0;i<13;i++) box(.16,.07,.035,silver,-2.3+i*.38,-.01,s*2.24,deck);
        }
        for(let i=0;i<5;i++) {
          const chip=box(.62,.26,.85,level===1? silver:metal,-1.9+i*.95,.28,0,deck); edge(chip,0xb4cbda,.3);
          box(.4,.035,.56,glow,-1.9+i*.95,.43,0,deck);
          for(let p=0;p<3;p++)box(.035,.025,.32,silver,-2.08+i*.95+p*.15,.16,.63,deck);
        }
        for(let i=0;i<4;i++) {box(.02,.018,1.2,glow,-1.7+i*1.12,.14,1.15,deck);box(.6,.018,.02,glow,-1.4+i*1.12,.14,1.72,deck);}
        const dot=mesh(new T.SphereGeometry(.07,10,8),glow,0,.23,-1.95,deck); pulses.push({m:dot,level});
      }
      for(const x of [-2.45,2.45])for(const z of [-1.65,1.65]){
        mesh(new T.CylinderGeometry(.065,.065,4.3,12),silver,x,.35,z);
        mesh(new T.CylinderGeometry(.16,.16,.1,16),glow,x,2.48,z);
      }
      const crown=mesh(new T.IcosahedronGeometry(.64,0),silver,0,3.16,0); edge(crown,accent,.8); this.crown=crown;
      const hoop=mesh(new T.TorusGeometry(1.2,.014,8,90),glow,0,3.12,0);hoop.rotation.x=Math.PI/2;
      for(let i=0;i<4;i++){const rail=box(.035,1.2,.035,glow,0,2.45,0);rail.position.x=Math.cos(i*Math.PI/2)*1.17;rail.position.z=Math.sin(i*Math.PI/2)*1.17;}
      const pedestal=box(7,.18,5.8,dark,0,-1.72,0);edge(pedestal,0x718898,.35);
      for(let i=0;i<21;i++){box(.014,.008,5.4,silver,-3.2+i*.32,-1.61,0);}
      // The external specialist sits outside the internal production line.
      const satellite=box(1,.5,1,metal,4,-.7,1.5);edge(satellite,0x7ef0ce,.8);
      box(.7,.07,.7,new T.MeshBasicMaterial({color:0x7ef0ce}),4,-.4,1.5);
      const curve=new T.CatmullRomCurve3([new T.Vector3(2.5,1,0),new T.Vector3(4.3,1,.3),new T.Vector3(4,-.4,1.5)]);
      mesh(new T.TubeGeometry(curve,30,.018,6,false),new T.MeshBasicMaterial({color:0x7ef0ce}));
      tracks.push(curve);
    } else {
      const core=mesh(new T.IcosahedronGeometry(1.42,1),metal,0,.45,0); edge(core,0x78c9ac,.7); this.crown=core;
      const inner=mesh(new T.IcosahedronGeometry(1.04,0),glow,0,.45,0);inner.rotation.z=.3;
      for(let ring=0;ring<3;ring++){
        const orbit=new T.Group();orbit.rotation.set(.5+ring*.65,.3+ring*.6,.3);sculpture.add(orbit);
        mesh(new T.TorusGeometry(3+ring*.8,.012,6,140),silver,0,0,0,orbit);
        for(let n=0;n<7;n++){
          const a=n*Math.PI*2/7+ring*.5,r=3+ring*.8;
          const node=mesh(new T.IcosahedronGeometry(n===0?.28:.16,0),n===0?glow:metal,Math.cos(a)*r,Math.sin(a)*r,0,orbit);
          parts.push(node);edge(node,0x398e71,.5);
        }
      }
      for(let n=0;n<8;n++){
        const a=n*Math.PI/4;
        const curve=new T.CatmullRomCurve3([new T.Vector3(Math.cos(a)*1.2,.45,Math.sin(a)*1.2),new T.Vector3(Math.cos(a)*2.6,1+Math.sin(a*2),Math.sin(a)*2.6),new T.Vector3(Math.cos(a)*4,Math.sin(a*3),Math.sin(a)*4)]);
        mesh(new T.TubeGeometry(curve,28,.01,5,false),silver);tracks.push(curve);
      }
    }
    for(const curve of tracks){const dot=mesh(new T.SphereGeometry(.07,10,8),glow);pulses.push({m:dot,curve});}
    const positions=[];for(let i=0;i<100;i++)positions.push(Math.sin(i*127.1)*8,Math.cos(i*71.7)*5,Math.sin(i*39.2)*7);
    const dustgeo=new T.BufferGeometry();dustgeo.setAttribute('position',new T.Float32BufferAttribute(positions,3));
    const dust=new T.Points(dustgeo,new T.PointsMaterial({color:atlas?0x327e62:0xe3be80,size:.026,transparent:true,opacity:.5}));scene.add(dust);
    let visible=true,frame=0,last=0,elapsed=0,yaw=atlas?-.3:-.18,pitch=0,drag=null;
    const clampPitch=value=>Math.max(-.5,Math.min(.4,value));
    this.onpointerdown=e=>{
      if(!e.isPrimary || e.button!==0)return;
      drag={id:e.pointerId,x:e.clientX,y:e.clientY};
      this.setPointerCapture(e.pointerId);this.setAttribute('data-dragging','');
      this.focus({preventScroll:true});
    };
    this.onpointermove=e=>{
      if(!drag || drag.id!==e.pointerId)return;
      yaw+=(e.clientX-drag.x)*.008;pitch=clampPitch(pitch+(e.clientY-drag.y)*.006);
      drag.x=e.clientX;drag.y=e.clientY;
    };
    const release=e=>{
      if(!drag || drag.id!==e.pointerId)return;
      drag=null;this.removeAttribute('data-dragging');
      if(this.hasPointerCapture(e.pointerId))this.releasePointerCapture(e.pointerId);
    };
    this.onpointerup=release;this.onpointercancel=release;this.onlostpointercapture=release;
    this.onkeydown=e=>{
      if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;
      e.preventDefault();
      if(e.key==='ArrowLeft')yaw-=.2;
      if(e.key==='ArrowRight')yaw+=.2;
      if(e.key==='ArrowUp')pitch=clampPitch(pitch-.12);
      if(e.key==='ArrowDown')pitch=clampPitch(pitch+.12);
    };
    const render=(time=0)=>{
      frame=requestAnimationFrame(render);
      if (!visible || document.hidden || time-last<32) return;
      const dt=Math.min((time-last)/1000,.1);last=time;
      const moving=!reduced.matches;if(moving)elapsed+=dt;
      if(moving&&!drag)yaw+=dt*.2;
      sculpture.rotation.y += (yaw-sculpture.rotation.y)*.16;
      sculpture.rotation.x += (pitch-sculpture.rotation.x)*.16;
      if(this.crown&&moving)this.crown.rotation.y+=dt*.24;
      if(moving)dust.rotation.y+=dt*.014;
      const stage=Number(this.getAttribute('stage')||0);
      parts.forEach((part,i)=>{
        if(!atlas){part.position.y+=(i*1.14-1.25+(i===stage?.17:0)-part.position.y)*.07;part.children[0].material=stage===i?silver:metal;}
      });
      pulses.forEach((p,i)=>{if(p.curve)p.m.position.copy(p.curve.getPoint((elapsed*.18+i*.17)%1));else p.m.position.x=Math.sin(elapsed*1.15+p.level)*2.3;});
      renderer.render(scene,camera);
    };
    const resize=()=>{const w=this.clientWidth,h=this.clientHeight;if(!w||!h)return;renderer.setSize(w,h);camera.aspect=w/h;camera.position.set(atlas?12:11,atlas?8:9,atlas?15:14);camera.zoom=w<500?.92:1.08;camera.updateProjectionMatrix();};
    this.resizeObserver=new ResizeObserver(resize);this.resizeObserver.observe(this);
    this.intersectionObserver=new IntersectionObserver(([e])=>{visible=e.isIntersecting;});this.intersectionObserver.observe(this);
    resize();frame=requestAnimationFrame(render);this.stop=()=>cancelAnimationFrame(frame);
    this.setAttribute('data-ready','true');
  }
  attributeChangedCallback() { /* Attributes are read by the animation loop. */ }
  disconnectedCallback(){
    this.onpointerdown=this.onpointermove=this.onpointerup=this.onpointercancel=this.onlostpointercapture=this.onkeydown=null;
    this.removeAttribute('data-dragging');
    this.stop?.();this.resizeObserver?.disconnect();this.intersectionObserver?.disconnect();
    this.scene?.traverse(o=>{o.geometry?.dispose();if(o.material){for(const m of Array.isArray(o.material)?o.material:[o.material])m.dispose();}});
    this.renderer?.dispose();this.renderer?.domElement.remove();this.renderer=null;
  }
}
if(!customElements.get('machine-scene'))customElements.define('machine-scene',MachineScene);
