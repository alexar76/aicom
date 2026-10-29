"""Self-contained floating AI assistant — factory-style chat, over everything.

Unlike the previous approach (a Streamlit-native chat portaled into ``<body>``
via brittle DOM surgery), this renders one small, self-contained widget into the
parent document: a gradient FAB in the bottom-right that expands a dark-glass
chat panel *over* the page with a smooth open/close animation — the same feel as
the AI-Factory support widget.

The panel talks directly to the SKOPOS API (``/agent/chat``) with a short-lived
HMAC token, so answers stream from the same LLM stack but with the full SKOPOS
knowledge base + live logs/statistics context — without triggering a Streamlit
rerun on every message.
"""

from __future__ import annotations

import json
import os

import streamlit.components.v1 as components

from skopos.agent_token import issue_token
from skopos.i18n import t, t_list
from skopos.themes import Theme, get_active_theme, is_light_theme, theme_surface_bg

# The whole widget (styles + DOM + logic) lives in this one script. It is
# idempotent: re-injecting only refreshes the live config (fresh token, locale).
_WIDGET_JS = r"""
(function () {
  var CFG = __SKOPOS_AGENT_CONFIG__;
  var root, doc;
  try { root = window.parent || window; doc = root.document; } catch (e) { return; }
  if (!doc || !doc.body) return;

  var ROOT_ID = 'skopos-agent-root';
  var STYLE_ID = 'skopos-agent-style';

  function teardownAgent() {
    var el = doc.getElementById(ROOT_ID);
    if (el) el.remove();
    var overlay = doc.getElementById('skopos-agent-fab-overlay');
    if (overlay) overlay.remove();
    doc.querySelectorAll(
      '.skopos-agent-portal, .stats-agent-root, .stats-agent-panel, '
      + '[data-skopos-open="1"], button.skopos-agent-fab'
    ).forEach(function (node) { node.remove(); });
    root.__skoposAgentApplyCfg = null;
    root.__skoposAgentState = null;
  }
  root.__skoposAgentTeardown = teardownAgent;

  // Auth gate: on the login screen (skopos-login-page-marker) strip any leftover
  // widget so the assistant is never visible before authentication.
  if (doc.querySelector('.skopos-login-page-marker')) { teardownAgent(); return; }

  // Re-mount: Streamlit destroys the previous component iframe on every rerun /
  // page navigation, which tears down the JS realm that owns the FAB's click
  // handlers. The widget DOM lives in the *top* document and survives, so reusing
  // it would leave a dead, unclickable FAB. Instead we drop the stale root and
  // rebuild fresh in the CURRENT (live) realm, preserving the conversation +
  // open state on root.__skoposAgentState so nothing visible is lost.
  var stale = doc.getElementById(ROOT_ID);
  if (stale) stale.remove();

  // Full theme palette (fallbacks keep the original dark look if absent).
  var P = CFG.palette || {};
  var TH = CFG.theme || {};
  var AC = P.accent || TH.accent || '#0891b2';
  var AC2 = P.accent2 || TH.accent2 || '#6366f1';

  // Every surface color is a CSS variable set on #skopos-agent-root (see
  // applyPalette), so a theme switch just updates the vars — no re-mount needed.
  var CSS =
    "#skopos-agent-root{position:fixed;bottom:1.25rem;right:1.25rem;z-index:2147483000;"
    + "font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;}"
    + "#skopos-agent-root *{box-sizing:border-box;}"
    + ".skopos-agent-fab{width:56px;height:56px;border-radius:999px;"
    + "border:1px solid color-mix(in srgb,var(--sk-accent) 55%,transparent);"
    + "background:var(--sk-fab-bg);color:var(--sk-fab-icon);display:flex;align-items:center;"
    + "justify-content:center;cursor:pointer;box-shadow:var(--sk-fab-shadow);position:relative;z-index:2;"
    + "transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease;}"
    + ".skopos-agent-fab:hover{transform:translateY(-2px) scale(1.03);"
    + "border-color:color-mix(in srgb,var(--sk-accent) 85%,transparent);}"
    + ".skopos-agent-fab svg{width:24px;height:24px;}"
    + ".skopos-agent-fab .sk-ic-close{display:none;}"
    + "#skopos-agent-root.is-open .skopos-agent-fab .sk-ic-chat{display:none;}"
    + "#skopos-agent-root.is-open .skopos-agent-fab .sk-ic-close{display:block;}"
    + ".skopos-agent-panel{position:absolute;bottom:calc(100% + .75rem);right:0;width:min(380px,calc(100vw - 2rem));"
    + "height:min(560px,calc(100vh - 7rem));display:flex;flex-direction:column;overflow:hidden;border-radius:1rem;"
    + "background:var(--sk-panel-bg);-webkit-backdrop-filter:blur(18px);backdrop-filter:blur(18px);"
    + "border:1px solid var(--sk-panel-border);box-shadow:var(--sk-shadow);color:var(--sk-text);"
    + "opacity:0;visibility:hidden;transform:translateY(14px) scale(.96);transform-origin:bottom right;"
    + "transition:opacity .24s ease,transform .24s cubic-bezier(.16,1,.3,1),visibility .24s;}"
    + "#skopos-agent-root.is-open .skopos-agent-panel{opacity:1;visibility:visible;transform:translateY(0) scale(1);}"
    + ".skopos-agent-head{display:flex;align-items:flex-start;gap:.55rem;padding:.85rem 1rem;"
    + "border-bottom:1px solid var(--sk-head-border);}"
    + ".skopos-agent-head-icon{width:34px;height:34px;flex:none;border-radius:.6rem;"
    + "background:linear-gradient(145deg,color-mix(in srgb,var(--sk-accent) 28%,transparent),color-mix(in srgb,var(--sk-accent2) 32%,transparent));display:flex;align-items:center;"
    + "justify-content:center;color:var(--sk-accent);}"
    + ".skopos-agent-head-icon svg{width:18px;height:18px;}"
    + ".skopos-agent-head-text{flex:1;min-width:0;}"
    + ".skopos-agent-title{font-size:.9rem;font-weight:600;color:var(--sk-title);line-height:1.2;}"
    + ".skopos-agent-sub{font-size:.68rem;color:var(--sk-muted);margin-top:.15rem;line-height:1.35;}"
    + ".skopos-agent-close{flex:none;width:28px;height:28px;border:none;background:transparent;color:var(--sk-muted);"
    + "border-radius:.5rem;cursor:pointer;display:flex;align-items:center;justify-content:center;"
    + "transition:background .15s ease,color .15s ease;}"
    + ".skopos-agent-close svg{width:16px;height:16px;}"
    + ".skopos-agent-close:hover{background:color-mix(in srgb,var(--sk-text) 12%,transparent);color:var(--sk-text);}"
    + ".skopos-agent-body{flex:1;overflow-y:auto;padding:.85rem;display:flex;flex-direction:column;gap:.6rem;"
    + "scrollbar-width:thin;scrollbar-color:var(--sk-scrollbar) transparent;}"
    + ".skopos-agent-body::-webkit-scrollbar{width:6px;}"
    + ".skopos-agent-body::-webkit-scrollbar-thumb{background:var(--sk-scrollbar);border-radius:3px;}"
    + ".skopos-agent-intro{font-size:.76rem;line-height:1.5;color:var(--sk-muted);margin:.1rem 0 .1rem;}"
    + ".skopos-agent-msg{max-width:88%;padding:.55rem .72rem;border-radius:.85rem;font-size:.82rem;line-height:1.5;"
    + "word-wrap:break-word;overflow-wrap:anywhere;}"
    + ".skopos-agent-msg--user{align-self:flex-end;background:linear-gradient(135deg,var(--sk-accent),var(--sk-accent2));color:#fff;"
    + "border-bottom-right-radius:.25rem;}"
    + ".skopos-agent-msg--bot{align-self:flex-start;background:var(--sk-bot-bg);color:var(--sk-bot-text);"
    + "border-bottom-left-radius:.25rem;}"
    + ".skopos-agent-msg--error{align-self:flex-start;background:var(--sk-err-bg);color:var(--sk-err-text);"
    + "border:1px solid var(--sk-err-border);}"
    + ".skopos-agent-msg code{background:var(--sk-code-bg);color:var(--sk-code-text);padding:.05rem .32rem;border-radius:.3rem;font-size:.78em;}"
    + ".skopos-agent-msg a{color:var(--sk-accent);}"
    + ".skopos-agent-navchip{align-self:flex-start;font-size:.68rem;color:var(--sk-accent);"
    + "background:color-mix(in srgb,var(--sk-accent) 12%,transparent);border:1px solid color-mix(in srgb,var(--sk-accent) 35%,transparent);"
    + "border-radius:999px;padding:.22rem .55rem;margin-top:-.15rem;}"
    + ".skopos-agent-typing{align-self:flex-start;display:flex;gap:4px;align-items:center;padding:.6rem .75rem;"
    + "background:var(--sk-bot-bg);border-radius:.85rem;}"
    + ".skopos-agent-typing span{width:6px;height:6px;border-radius:50%;background:var(--sk-muted);"
    + "animation:skAgentBlink 1.2s infinite ease-in-out;}"
    + ".skopos-agent-typing span:nth-child(2){animation-delay:.2s;}"
    + ".skopos-agent-typing span:nth-child(3){animation-delay:.4s;}"
    + "@keyframes skAgentBlink{0%,80%,100%{opacity:.25;transform:translateY(0);}40%{opacity:1;transform:translateY(-3px);}}"
    + ".skopos-agent-chips{display:flex;flex-wrap:wrap;gap:.35rem;padding:0 .85rem .5rem;}"
    + ".skopos-agent-chip{font-size:.7rem;color:var(--sk-chip-text);background:var(--sk-chip-bg);"
    + "border:1px solid var(--sk-chip-border);border-radius:999px;padding:.32rem .6rem;cursor:pointer;text-align:left;"
    + "max-width:100%;line-height:1.35;white-space:normal;overflow:hidden;display:-webkit-box;"
    + "-webkit-line-clamp:2;-webkit-box-orient:vertical;word-break:break-word;"
    + "transition:background .15s ease,border-color .15s ease,color .15s ease;}"
    + ".skopos-agent-chip:hover{background:color-mix(in srgb,var(--sk-accent) 18%,transparent);border-color:color-mix(in srgb,var(--sk-accent) 45%,transparent);color:var(--sk-text);}"
    + ".skopos-agent-foot{border-top:1px solid var(--sk-head-border);padding:.6rem .7rem .55rem;}"
    + ".skopos-agent-inputwrap{display:flex;align-items:flex-end;gap:.4rem;background:var(--sk-input-bg);"
    + "border:1px solid var(--sk-input-border);border-radius:.8rem;padding:.35rem .4rem .35rem .65rem;"
    + "transition:border-color .15s ease;}"
    + ".skopos-agent-inputwrap:focus-within{border-color:color-mix(in srgb,var(--sk-accent) 55%,transparent);}"
    + ".skopos-agent-input{flex:1;resize:none;border:none;background:transparent;color:var(--sk-text);font-size:.82rem;"
    + "line-height:1.4;max-height:96px;outline:none;font-family:inherit;padding:.28rem 0;}"
    + ".skopos-agent-input::placeholder{color:var(--sk-muted);}"
    + ".skopos-agent-send{flex:none;width:34px;height:34px;border:none;border-radius:.6rem;"
    + "background:linear-gradient(135deg,var(--sk-accent),var(--sk-accent2));color:#fff;cursor:pointer;display:flex;align-items:center;"
    + "justify-content:center;transition:opacity .15s ease,transform .15s ease;}"
    + ".skopos-agent-send:hover{transform:scale(1.05);}"
    + ".skopos-agent-send:disabled{opacity:.4;cursor:not-allowed;transform:none;}"
    + ".skopos-agent-send svg{width:16px;height:16px;}"
    + ".skopos-agent-status{font-size:.6rem;color:var(--sk-muted);margin:.4rem 0 0;text-align:center;}"
    + "@media (max-width:640px){#skopos-agent-root{bottom:.85rem;right:.85rem;}"
    + ".skopos-agent-panel{width:calc(100vw - 1.5rem);right:0;height:min(72vh,calc(100vh - 5.5rem));}"
    + ".skopos-agent-fab{width:52px;height:52px;}.skopos-agent-chip{font-size:.65rem;padding:.28rem .5rem;-webkit-line-clamp:3;}}";

  // Map palette → CSS custom properties on the widget root (updatable on theme switch).
  var PALETTE_VARS = {
    '--sk-accent': AC,
    '--sk-accent2': AC2,
    '--sk-panel-bg': P.panelBg || 'rgba(6,11,25,.97)',
    '--sk-panel-border': P.panelBorder || 'rgba(148,163,184,.18)',
    '--sk-head-border': P.headBorder || 'rgba(148,163,184,.14)',
    '--sk-text': P.text || '#e2e8f0',
    '--sk-title': P.title || '#ffffff',
    '--sk-muted': P.muted || '#94a3b8',
    '--sk-bot-bg': P.botBg || 'rgba(148,163,184,.12)',
    '--sk-bot-text': P.botText || '#e2e8f0',
    '--sk-code-bg': P.codeBg || 'rgba(2,6,23,.7)',
    '--sk-code-text': P.codeText || '#e2e8f0',
    '--sk-chip-bg': P.chipBg || 'rgba(148,163,184,.1)',
    '--sk-chip-text': P.chipText || '#cbd5e1',
    '--sk-chip-border': P.chipBorder || 'rgba(148,163,184,.18)',
    '--sk-input-bg': P.inputBg || 'rgba(15,23,42,.65)',
    '--sk-input-border': P.inputBorder || 'rgba(148,163,184,.2)',
    '--sk-scrollbar': P.scrollbar || 'rgba(148,163,184,.4)',
    '--sk-shadow': P.shadow || '0 28px 70px rgba(0,0,0,.55)',
    '--sk-err-bg': P.errBg || 'rgba(220,38,38,.16)',
    '--sk-err-text': P.errText || '#fecaca',
    '--sk-err-border': P.errBorder || 'rgba(248,113,113,.32)',
    '--sk-fab-bg': P.fabBg || 'linear-gradient(145deg,#0f172a,#1e1b4b)',
    '--sk-fab-icon': P.fabIcon || AC,
    '--sk-fab-shadow': P.fabShadow || '0 12px 32px rgba(8,47,73,.45)'
  };
  function applyPalette(node, pal) {
    if (!node) return;
    var vars = pal || PALETTE_VARS;
    for (var k in vars) { if (vars[k]) node.style.setProperty(k, vars[k]); }
  }
  function paletteFromCfg(cfg) {
    var p = (cfg && cfg.palette) || {};
    var ac = p.accent || (cfg && cfg.theme && cfg.theme.accent) || AC;
    var ac2 = p.accent2 || (cfg && cfg.theme && cfg.theme.accent2) || AC2;
    return {
      '--sk-accent': ac, '--sk-accent2': ac2,
      '--sk-panel-bg': p.panelBg, '--sk-panel-border': p.panelBorder,
      '--sk-head-border': p.headBorder, '--sk-text': p.text, '--sk-title': p.title,
      '--sk-muted': p.muted, '--sk-bot-bg': p.botBg, '--sk-bot-text': p.botText,
      '--sk-code-bg': p.codeBg, '--sk-code-text': p.codeText,
      '--sk-chip-bg': p.chipBg, '--sk-chip-text': p.chipText, '--sk-chip-border': p.chipBorder,
      '--sk-input-bg': p.inputBg, '--sk-input-border': p.inputBorder,
      '--sk-scrollbar': p.scrollbar, '--sk-shadow': p.shadow,
      '--sk-err-bg': p.errBg, '--sk-err-text': p.errText, '--sk-err-border': p.errBorder,
      '--sk-fab-bg': p.fabBg, '--sk-fab-icon': p.fabIcon, '--sk-fab-shadow': p.fabShadow
    };
  }

  var IC_CHAT = "<svg class='sk-ic-chat' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M7.9 20A9 9 0 1 0 4 16.1L2 22Z'/></svg>";
  var IC_CLOSE_FAB = "<svg class='sk-ic-close' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><line x1='18' y1='6' x2='6' y2='18'/><line x1='6' y1='6' x2='18' y2='18'/></svg>";
  var IC_CLOSE = "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><line x1='18' y1='6' x2='6' y2='18'/><line x1='6' y1='6' x2='18' y2='18'/></svg>";
  var IC_SHIELD = "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z'/></svg>";
  var IC_SEND = "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M22 2 11 13'/><path d='M22 2 15 22 11 13 2 9z'/></svg>";

  // Quotes too: the link rule below puts captured text inside an attribute, and the
  // assistant's context carries request paths any internet client chose.
  function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
  function fmt(s) {
    var t = esc(s);
    t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
    t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, "<a href='$2' target='_blank' rel='noopener'>$1</a>");
    t = t.replace(/\n/g, '<br>');
    return t;
  }

  // ---- build style + DOM ----
  if (!doc.getElementById(STYLE_ID)) {
    var style = doc.createElement('style');
    style.id = STYLE_ID;
    style.textContent = CSS;
    (doc.head || doc.body).appendChild(style);
  }

  var state = root.__skoposAgentState || { history: [], cfg: CFG };
  state.cfg = CFG;
  root.__skoposAgentState = state;

  var el = doc.createElement('div');
  el.id = ROOT_ID;
  el.innerHTML =
    "<div class='skopos-agent-panel' role='dialog' aria-modal='false'>"
    + "<div class='skopos-agent-head'>"
    + "<div class='skopos-agent-head-icon'>" + IC_SHIELD + "</div>"
    + "<div class='skopos-agent-head-text'><div class='skopos-agent-title'></div>"
    + "<div class='skopos-agent-sub'></div></div>"
    + "<button type='button' class='skopos-agent-close' aria-label='close'>" + IC_CLOSE + "</button>"
    + "</div>"
    + "<div class='skopos-agent-body'></div>"
    + "<div class='skopos-agent-chips'></div>"
    + "<div class='skopos-agent-foot'>"
    + "<div class='skopos-agent-inputwrap'>"
    + "<textarea class='skopos-agent-input' rows='1'></textarea>"
    + "<button type='button' class='skopos-agent-send' aria-label='send'>" + IC_SEND + "</button>"
    + "</div><p class='skopos-agent-status'></p></div>"
    + "</div>"
    + "<button type='button' class='skopos-agent-fab' aria-label='chat'>" + IC_CHAT + IC_CLOSE_FAB + "</button>";
  applyPalette(el, PALETTE_VARS);
  doc.body.appendChild(el);

  var panel = el.querySelector('.skopos-agent-panel');
  var fab = el.querySelector('.skopos-agent-fab');
  var closeBtn = el.querySelector('.skopos-agent-close');
  var body = el.querySelector('.skopos-agent-body');
  var chips = el.querySelector('.skopos-agent-chips');
  var input = el.querySelector('.skopos-agent-input');
  var sendBtn = el.querySelector('.skopos-agent-send');
  var titleEl = el.querySelector('.skopos-agent-title');
  var subEl = el.querySelector('.skopos-agent-sub');
  var statusEl = el.querySelector('.skopos-agent-status');

  function scrollBottom() { body.scrollTop = body.scrollHeight; }

  function appendMessage(role, text) {
    var d = doc.createElement('div');
    d.className = 'skopos-agent-msg skopos-agent-msg--' + role;
    if (role === 'user') { d.textContent = text; } else { d.innerHTML = fmt(text); }
    body.appendChild(d);
    scrollBottom();
    return d;
  }

  function showTyping() {
    var d = doc.createElement('div');
    d.className = 'skopos-agent-typing';
    d.innerHTML = '<span></span><span></span><span></span>';
    body.appendChild(d);
    scrollBottom();
    return d;
  }

  function renderIntro() {
    body.innerHTML = '';
    if (!state.history.length && state.cfg.strings.intro) {
      var p = doc.createElement('p');
      p.className = 'skopos-agent-intro';
      p.textContent = state.cfg.strings.intro;
      body.appendChild(p);
    }
    for (var i = 0; i < state.history.length; i++) {
      appendMessage(state.history[i].role === 'user' ? 'user' : 'bot', state.history[i].content);
    }
  }

  function renderChips() {
    chips.innerHTML = '';
    if (state.history.length) { chips.style.display = 'none'; return; }
    chips.style.display = 'flex';
    var list = state.cfg.suggestions || [];
    for (var i = 0; i < list.length && i < 4; i++) {
      (function (label) {
        var b = doc.createElement('button');
        b.type = 'button';
        b.className = 'skopos-agent-chip';
        b.textContent = label;
        b.addEventListener('click', function () { send(label); });
        chips.appendChild(b);
      })(list[i]);
    }
  }

  function updateSendState() {
    sendBtn.disabled = state.busy || !input.value.trim();
  }

  function autoGrow() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 96) + 'px';
  }

  function runActions(actions) {
    if (!actions || !actions.length) return;
    for (var i = 0; i < actions.length; i++) {
      var a = actions[i] || {};
      if (a.type !== 'navigate' || !a.page) continue;
      (function (page, tab) {
        root.setTimeout(function () {
          var ok = false;
          try {
            if (typeof root.skoposNavigate === 'function') {
              ok = !!root.skoposNavigate(page, tab || null);
            }
          } catch (err) {}
          var chip = doc.createElement('div');
          chip.className = 'skopos-agent-navchip';
          chip.textContent = ok
            ? ('↗ ' + page + (tab ? (' / ' + tab) : ''))
            : ('↗ ' + page + (tab ? (' / ' + tab) : '') + ' (open from sidebar)');
          body.appendChild(chip);
          scrollBottom();
        }, 180 + i * 120);
      })(a.page, a.tab);
    }
  }

  function send(text) {
    text = (text || '').trim();
    if (!text || state.busy) return;
    state.busy = true;
    appendMessage('user', text);
    state.history.push({ role: 'user', content: text });
    renderChips();
    input.value = '';
    autoGrow();
    updateSendState();
    var typing = showTyping();
    var cfg = state.cfg;
    var base = cfg.apiBase || (root.location && root.location.origin) || '';
    fetch(base + '/agent/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + cfg.token },
      body: JSON.stringify({ messages: state.history, page: cfg.page || null, server_name: cfg.serverName || null })
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { return { status: r.status, body: j }; });
    }).then(function (res) {
      if (typing.parentNode) typing.remove();
      if (res.status === 200 && res.body && res.body.reply) {
        appendMessage('bot', res.body.reply);
        state.history.push({ role: 'assistant', content: res.body.reply });
        runActions(res.body.actions || []);
      } else if (res.status === 401) {
        appendMessage('error', cfg.strings.expired);
      } else if (res.status === 503) {
        appendMessage('error', cfg.strings.unavailable);
      } else {
        appendMessage('error', cfg.strings.error);
      }
    }).catch(function () {
      if (typing.parentNode) typing.remove();
      appendMessage('error', state.cfg.strings.error);
    }).then(function () {
      state.busy = false;
      updateSendState();
      scrollBottom();
    });
  }

  function setOpen(on) {
    state.open = on;
    el.classList.toggle('is-open', on);
    fab.setAttribute('aria-label', on ? state.cfg.strings.close : state.cfg.strings.open);
    if (on) { setTimeout(function () { input.focus(); }, 160); }
  }

  fab.addEventListener('click', function () { setOpen(!el.classList.contains('is-open')); });
  closeBtn.addEventListener('click', function () { setOpen(false); });
  input.addEventListener('input', function () { autoGrow(); updateSendState(); });
  input.addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); send(input.value); }
  });
  sendBtn.addEventListener('click', function () { send(input.value); });

  function applyCfg(cfg) {
    state.cfg = cfg;
    applyPalette(el, paletteFromCfg(cfg));
    titleEl.textContent = cfg.strings.title;
    subEl.textContent = cfg.strings.subtitle;
    statusEl.textContent = cfg.strings.status;
    input.placeholder = cfg.strings.placeholder;
    // On a live language switch the panel is re-mounted idempotently; refresh the
    // greeting too (not just chips) so the intro text follows the selected locale.
    if (!state.history.length) { renderIntro(); renderChips(); }
  }
  root.__skoposAgentApplyCfg = applyCfg;

  applyCfg(CFG);
  renderIntro();
  renderChips();
  updateSendState();
  if (state.open) setOpen(true);
})();
"""


def _resolve_api_base() -> str:
    """Same-origin by default; env override for split-host dev (e.g. :8502)."""
    return (os.environ.get("SKOPOS_AGENT_API_BASE", "") or "").strip().rstrip("/")


def _agent_palette(theme: Theme) -> dict[str, str]:
    """Full widget color gamma derived from the active dashboard theme.

    Uses ``color-mix`` against the theme's own text/accent/surface so it adapts
    to every light/dark theme without per-theme branches. The floating panel
    should feel like part of the selected theme, not a fixed dark overlay.
    """
    th = theme
    light = is_light_theme(th.id)
    surface = theme_surface_bg(th)
    return {
        "accent": th.accent,
        "accent2": th.accent2,
        "panelBg": f"color-mix(in srgb, {surface} 97%, transparent)",
        "panelBorder": th.card_border,
        "headBorder": f"color-mix(in srgb, {th.text} 14%, transparent)",
        "text": th.text,
        "title": th.text,
        "muted": th.text_muted,
        "botBg": f"color-mix(in srgb, {th.text} 8%, transparent)",
        "botText": th.text,
        "codeBg": f"color-mix(in srgb, {th.text} 14%, transparent)",
        "codeText": th.text,
        "chipBg": f"color-mix(in srgb, {th.accent} 12%, transparent)",
        "chipText": th.text,
        "chipBorder": f"color-mix(in srgb, {th.accent} 26%, transparent)",
        "inputBg": f"color-mix(in srgb, {th.text} 6%, transparent)",
        "inputBorder": th.border,
        "scrollbar": f"color-mix(in srgb, {th.text_muted} 45%, transparent)",
        "shadow": (
            "0 24px 60px rgba(15,23,42,.18)" if light else "0 28px 70px rgba(0,0,0,.55)"
        ),
        "errBg": th.sec_crit_bg,
        "errText": th.sec_crit_text,
        "errBorder": th.sec_crit_border,
        "fabBg": f"linear-gradient(145deg, {th.accent}, {th.accent2})",
        "fabIcon": "#ffffff",
        "fabShadow": (
            f"0 12px 32px color-mix(in srgb, {th.accent} 45%, transparent)"
            if not light
            else f"0 12px 30px color-mix(in srgb, {th.accent} 32%, transparent)"
        ),
    }


def _build_config(
    *,
    locale: str,
    page: str | None,
    server_name: str | None,
    theme: Theme | None = None,
) -> dict:
    th = theme or get_active_theme()
    suggestions = [s for s in (t_list("agent.suggestions", locale) or []) if s][:4]
    return {
        "apiBase": _resolve_api_base(),
        "token": issue_token(),
        "page": page,
        "serverName": server_name,
        "theme": {"accent": th.accent, "accent2": th.accent2},
        "palette": _agent_palette(th),
        "suggestions": suggestions,
        "strings": {
            "title": t("agent.panel_title", locale),
            "subtitle": t("agent.panel_subtitle", locale),
            "intro": t("agent.panel_intro", locale),
            "placeholder": t("agent.placeholder", locale),
            "status": t("agent.footer_status", locale),
            "open": t("agent.open", locale),
            "close": t("agent.close", locale),
            "error": t("agent.error", locale),
            "unavailable": t("agent.unavailable", locale),
            "expired": t("agent.expired_session", locale),
        },
    }


def render_floating_agent(
    *,
    locale: str = "en",
    page: str | None = None,
    server_name: str | None = None,
    theme: Theme | None = None,
) -> None:
    """Inject the self-contained floating assistant into the parent document."""
    cfg = _build_config(locale=locale, page=page, server_name=server_name, theme=theme)
    script = _WIDGET_JS.replace("__SKOPOS_AGENT_CONFIG__", json.dumps(cfg, ensure_ascii=True))
    components.html(f"<script>{script}</script>", height=0, width=0)
