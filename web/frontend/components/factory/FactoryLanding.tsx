'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import Script from 'next/script';
import { ArrowUpRight, ArrowDown, ArrowRight, Box, Code2, Layers3, Check, Plus } from 'lucide-react';
import { factoryCopy } from '@/components/factory/copy';
import { type SiteLocale } from '@/lib/siteLocale';
import { saveMarketingLocale } from '@/lib/marketing';
import '@/app/factory.css';

const languages: [SiteLocale,string][] = [['en','EN'],['ru','RU'],['es','ES'],['fr','FR'],['zh','中文']];
const factory = 'https://magic-ai-factory.com';

export default function FactoryLanding({ initialLocale }: { initialLocale: SiteLocale }) {
  const locale=initialLocale;
  const factoryEntry = `${factory}/?lang=${locale}`;
  const generator = `${factory}/landing-page-generation/?lang=${locale}`;
  const outputs = [`${factoryEntry}#products`, `${factory}/agents`, generator];
  const [stage,setStage]=useState(1);
  const c=factoryCopy[locale];
  const ecosystem = `https://ecosystem.modelmarket.dev/${locale === 'en' ? '' : locale + '/'}`;
  useEffect(()=>{document.documentElement.lang=locale;},[locale]);
  const changeLocale=(l:SiteLocale)=>{saveMarketingLocale(l);window.location.assign(l==='en'?'/':`/${l}/`);};
  const docLocale=locale==='en'?'':`.${locale}`;
  return <main className="factory-page" lang={locale}>
    <Script src="/factory/scene.js?v=20261011-rotate" type="module" strategy="afterInteractive" />
    <a href="#factory-content" className="f-skip">{c.skip}</a>
    <header className="f-header">
      <Link className="f-brand" href={locale === 'en' ? '/' : `/${locale}/`} aria-label="AICOM"><span className="f-logo"><i/><i/><i/></span>AICOM<span className="f-brand-tag">FACTORY</span></Link>
      <nav className="f-nav" aria-label={c.nav[0]}><a href="#inside">{c.nav[0]}</a><a href="#outputs">{c.nav[1]}</a><a href="#specialists">{c.nav[2]}</a></nav>
      <div className="f-header-end"><label className="f-language"><span className="sr-only">{c.language}</span><select value={locale} onChange={e=>changeLocale(e.target.value as SiteLocale)}>{languages.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label><a className="f-ecosystem-link" href={ecosystem}>{c.ecosystem}</a></div>
    </header>
    <section className="f-hero f-wrap" id="factory-content">
      <div className="f-hero-copy"><p className="f-eyebrow"><span className="f-status-dot"/>{c.eyebrow}</p>
        <h1>{c.title.map((line,i)=><React.Fragment key={line}><span className={i===2?'f-accent':''}>{line}</span>{i<2&&<br/>}</React.Fragment>)}</h1>
        <p className="f-promise">{c.story.promise}</p>
        <p className="f-intro">{c.intro}</p>
        <div className="f-actions"><Link href={factoryEntry} className="f-button">{c.start}<ArrowUpRight size={19}/></Link><a href="#specialists" className="f-text-link">{c.story.caseLink}<ArrowDown size={16}/></a></div>
        <a href="https://github.com/alexar76/aicom" className="f-open"><span>⌘</span>{c.open}</a>
      </div>
      <div className="f-visual" aria-label={c.scene}>
        <div className="f-scene-top"><span>F / 01</span><span>{c.scene}</span></div>
        {React.createElement('machine-scene',{mode:'factory',stage:String(stage),tabIndex:0,role:'group','aria-label':c.scene,'aria-describedby':'factory-scene-hint',className:'f-machine'},<div className="f-scene-fallback" aria-hidden="true"><span/><span/><span/><span/></div>)}
        <div className="f-scene-label f-label-a"><span>01—04</span><strong>AICOM</strong><small>INTERNAL TEAM</small></div><div className="f-scene-label f-label-b"><i/><strong>AIMarket</strong><small>EXTERNAL SPECIALIST</small></div>
        <div className="f-scene-bottom" id="factory-scene-hint"><span className="f-cross">+</span>{c.sceneNote}<span>↗ XYZ</span></div>
      </div>
      <div className="f-stage-control"><div role="group" aria-label={c.scene}>{c.stages.map((name,i)=><button key={name} aria-pressed={stage===i} className={stage===i?'selected':''} onClick={()=>setStage(i)}><span>0{i+1}</span>{name}<span className="f-step-dot"/></button>)}</div><p aria-live="polite">{c.stageText[stage]}</p></div>
    </section>
    <div className="f-proof-strip f-wrap">{c.strip.map(text=><span key={text}><Check size={14}/>{text}</span>)}</div>
    <section id="outputs" className="f-section f-wrap"><div className="f-section-head"><div><p className="f-eyebrow">{c.buildEyebrow}</p><h2>{c.buildTitle}</h2></div><p>{c.buildIntro}</p></div>
      <div className="f-output-grid">{c.builds.map(([title,description,link],i)=>{const Icon=[Layers3,Code2,Box][i];return <a className="f-output" href={outputs[i]} key={title}><div className={`f-output-art art-${i}`} aria-hidden="true"><Icon size={50} strokeWidth={1}/><span/><i/><b/></div><div className="f-output-body"><span className="f-mono">0{i+1} /</span><h3>{title}</h3><p>{description}</p><span className="f-card-link">{link}<ArrowUpRight size={18}/></span></div></a>;})}</div>
    </section>
    <section id="inside" className="f-process"><div className="f-wrap f-section"><div className="f-section-head"><div><p className="f-eyebrow">{c.processEyebrow}</p><h2>{c.processTitle}</h2></div><p>{c.processIntro}</p></div>
      <div className="f-workflow">{c.roles.map((role,i)=><div className={i===2?'active':''} key={role}><span className="f-role-no">0{i+1}</span><span className="f-role-symbol">{i===2?<Code2/>:i===3?<Check/>:i===4?<Box/>:<Plus/>}</span><strong>{role}</strong>{i<4&&<ArrowRight className="f-role-arrow" size={16}/>}</div>)}</div>
      <div className="f-guardrails"><h3>{c.control}</h3><ul>{c.controls.map(t=><li key={t}><Check size={15}/>{t}</li>)}</ul></div>
    </div></section>
    <section id="specialists" className="f-section f-wrap f-subcontract">
      <div><p className="f-eyebrow">{c.subEyebrow}</p><h2>{c.subTitle}</h2><p className="f-section-text">{c.subIntro}</p></div>
      <div className="f-sub-panel">
        <div className="f-sub-network" aria-hidden="true"><span className="f-sub-company"><Box size={27}/>AICOM</span><span className="f-exchange-line"><i/><small>AIMarket</small><ArrowRight size={15}/></span><span className="f-sub-specialist"><Code2 size={27}/>{c.subSteps[2]}</span></div>
        <p className="f-case-outcome">{c.story.outcome}</p>
      </div>
      <div className="f-case">
        <div className="f-case-brief"><div><p className="f-eyebrow">{c.story.briefLabel}</p><h3>{c.story.brief}</h3></div><p>{c.story.context}</p></div>
        <ol className="f-case-steps">{c.story.steps.map(([title,description],i)=><li key={title}><span className="f-role-no">0{i+1}</span><h4>{title}</h4><p>{description}</p></li>)}</ol>
        <p className="f-case-limits">{c.subLimit}</p>
        <details className="f-case-proof"><summary>{c.subStatus}</summary><p>{c.story.proof}</p><a className="f-text-link" download href={`/factory/docs/factory-subcontracting${docLocale}.md`}>{c.subLink}</a></details>
      </div>
    </section>
    <section className="f-economy"><div className="f-wrap f-section"><p className="f-eyebrow">{c.economyEyebrow}</p><div className="f-section-head"><h2>{c.economyTitle}</h2><p>{c.economyIntro}</p></div><div className="f-economy-roles">{c.economyRoles.map(([name,role],i)=><a href={[ factory,'https://modelmarket.dev/',ecosystem][i]} key={name}><span>0{i+1}</span><strong>{name}</strong><p>{role}</p><ArrowUpRight size={20}/></a>)}</div><a href={ecosystem} className="f-text-link">{c.map}</a></div></section>
    <section className="f-final f-wrap"><span className="f-eyebrow">NEXT /</span><h2>{c.finalTitle}</h2><p>{c.finalText}</p><Link className="f-button" href={factoryEntry}>{c.start}<ArrowUpRight size={20}/></Link><a className="f-try" href={generator}>{c.try}</a></section>
    <footer className="f-footer f-wrap"><div><a className="f-brand" href="#factory-content">AICOM<span className="f-brand-tag">FACTORY</span></a><p>{c.footer}</p></div><nav><Link href={`${factory}/docs`}>{c.docs}</Link><Link href={`${factoryEntry}#products`}>{c.catalog}</Link><a href="https://github.com/alexar76/aicom">GitHub ↗</a><Link href={`${factory}/privacy`}>{c.privacy}</Link><Link href={`${factory}/terms`}>{c.terms}</Link></nav><span className="f-mono">BUILD. VERIFY. CREATE.</span></footer>
  </main>;
}
