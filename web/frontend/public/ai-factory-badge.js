(function () {
  if (typeof document === 'undefined') return;
  if (document.getElementById('aifactory-powered-badge')) return;
  var script = document.currentScript;
  var position = (script && script.getAttribute('data-position')) || 'bottom-right';
  var base =
    (script && script.getAttribute('data-base-url')) ||
    (typeof window !== 'undefined' && window.__AIFACTORY_PUBLIC_SITE_URL__) ||
    '';
  base = (base || '').replace(/\/$/, '');
  if (!base && typeof location !== 'undefined' && location.origin) {
    base = location.origin;
  }
  if (!base) base = 'https://magic-ai-factory.com';
  var badge = document.createElement('a');
  badge.id = 'aifactory-powered-badge';
  badge.href = base;
  badge.target = '_blank';
  badge.rel = 'noopener noreferrer';
  badge.textContent = 'Powered by AI-Factory';
  badge.style.position = 'fixed';
  badge.style.zIndex = '999999';
  badge.style.bottom = '16px';
  badge.style.padding = '8px 12px';
  badge.style.background = 'linear-gradient(135deg, #4f46e5, #9333ea)';
  badge.style.color = '#fff';
  badge.style.borderRadius = '999px';
  badge.style.fontFamily = 'system-ui, -apple-system, Segoe UI, Roboto, sans-serif';
  badge.style.fontSize = '12px';
  badge.style.fontWeight = '600';
  badge.style.boxShadow = '0 10px 25px rgba(79,70,229,0.35)';
  badge.style.textDecoration = 'none';
  if (position === 'bottom-left') {
    badge.style.left = '16px';
  } else {
    badge.style.right = '16px';
  }
  document.body.appendChild(badge);
})();
