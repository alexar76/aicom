"use client";
import { useState } from "react";
import { BlipCanvas } from "@/components/three/BlipCanvas";
import { speciesById } from "@pingblip/shared/species";
export default function Review() {
  const [evolved, setEvolved] = useState(true);
  const [burst, setBurst] = useState(0);
  const species = speciesById("liq-snake");
  return <main style={{maxWidth:650,margin:"0 auto"}}>
    <div style={{padding:12,display:"flex",gap:24}}>
      <button onClick={()=>setEvolved(v=>!v)}>{evolved ? "Evolved" : "Normal"}</button>
      <button onClick={()=>{setEvolved(true);setBurst(v=>v+1)}}>Evolution burst</button>
    </div>
    <style>{`.ticket-review-stage{position:relative;height:min(36vh,18rem)}@media(min-width:760px){.ticket-review-stage{height:85vh}}`}</style>
    <div className="ticket-review-stage">
      <BlipCanvas speciesId="liq-snake" sceneId={species?.sceneId} evolved={evolved} burst={burst} spinning={false} className="absolute inset-0" />
    </div>
  </main>;
}
