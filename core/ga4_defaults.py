"""Default GA4 measurement id and head snippet for production / docs."""

from __future__ import annotations

GA4_MEASUREMENT_ID = "G-67NJ81W2YY"

GA4_HEAD_SNIPPET = f"""<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id={GA4_MEASUREMENT_ID}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{GA4_MEASUREMENT_ID}');
</script>"""
