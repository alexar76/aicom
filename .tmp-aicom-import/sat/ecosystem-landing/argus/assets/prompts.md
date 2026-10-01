# ARGUS landing — visual asset prompts

The landing ships with self-contained SVG/CSS animation (no external assets needed).
These prompts are **optional upgrades**: generate the still image first, then feed
that image into **Grok Imagine** (image→video) with the matching animation prompt
to produce a `.webm`/`.mp4` loop. Drop results in this `assets/` folder and wire
them in (notes per asset).

Recommended palette to keep on-brand: deep navy `#05060f`, cyan `#36e6ff`,
violet `#a779ff`, pink `#ff5db1`, with neon glow. 16:9 for hero, 1:1 for mascot,
1200×630 for the social card.

---

## 1. Hero background (`hero.webm`)
**Image prompt (Grok Imagine / any T2I):**
> A vast dark-navy cyberpunk data-cosmos, subtle perspective grid floor fading
> into a star field, faint nebula clouds in cyan→violet→magenta, a single
> luminous all-seeing eye-of-Argus motif glowing softly in the upper third,
> thin neon constellation lines connecting drifting nodes, ultra-clean, high
> contrast, no text, 16:9, cinematic, volumetric glow.

**Animation prompt (Grok Imagine, image→video):**
> Slow parallax drift of the star field toward the camera, the nebula breathes
> and shifts hue cyan→violet, the central eye pupil dilates and contracts gently,
> constellation lines pulse with light traveling along them, seamless 8–10s loop,
> no camera cuts, calm and hypnotic.

*Wire-in:* place a fixed full-bleed `<video autoplay muted loop playsinline>` with
`hero.webm` behind `.aura` (z-index 0), keep the canvas star field as fallback.

---

## 2. ARGUS mascot (`mascot.webm` / `mascot.png`)
**Image prompt:**
> A friendly-but-vigilant guardian mascot: a rounded shield shaped like a
> hundred-eyed watcher, one large central glowing eye (iris gradient
> cyan→violet), a few smaller eyes along the rim, holographic neon outline,
> floating, soft inner light, charming and approachable (not scary), 3D glassy
> material, transparent background, 1:1.

**Animation prompt (image→video):**
> The mascot floats and bobs gently, the central eye blinks slowly and looks
> left→right→at the viewer, rim eyes twinkle in sequence, a soft shield-shimmer
> sweeps across the surface, seamless 6s loop, transparent/dark background.

*Wire-in:* swap the inline `.mascot` SVG for this video, or use `mascot.png` as a
crisper still.

---

## 3. "ARGUS vs. that other agent" meme strip (`vs.png`)
**Image prompt:**
> Split-panel cartoon: LEFT — a frazzled generic robot lying on a therapist couch
> overthinking, surrounded by floating dollar/token symbols draining away, dim and
> chaotic; RIGHT — a calm confident ARGUS shield-eye mascot giving a thumbs up,
> tidy neon HUD, a small lock icon and a wallet icon, bright and composed.
> Playful flat-illustration style, on-brand neon palette, no text.

**Animation prompt:**
> Left robot keeps spiraling, tokens drain faster; right ARGUS gives a single
> confident nod and the lock clicks shut with a glint; 4s loop.

*Wire-in:* optional banner above the comparison table.

---

## 4. Social / OG share card (`og.png`, 1200×630)
**Image prompt:**
> A bold social-share banner: the ARGUS hundred-eyed shield mascot on the left
> glowing, big empty space on the right for a title, deep-navy background, neon
> cyan→violet→pink gradient accent bar, subtle grid, premium tech aesthetic,
> 1200×630, leave the right 60% relatively clean for overlaid text.

*Wire-in:* add `<meta property="og:image" content="assets/og.png">` and a Twitter
card meta to `index.html`.

---

## Notes
- Keep everything **self-hostable** — download generated assets into `assets/`; do
  not hot-link external CDNs (the page must work offline / on GitHub Pages).
- Provide `.webm` (VP9) + an `.mp4` (H.264) fallback for Safari if you add video.
- All current animation on the page is pure SVG/CSS/canvas and needs none of the
  above to look great — these are the "turn it to 11" extras.
