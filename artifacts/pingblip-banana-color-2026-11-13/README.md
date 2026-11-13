# Bruised Banana: evolution color on Bench

The banana's peel and bruises use glTF vertex colors. Evolution used the
material's uniform base color (white) as the emissive color, clipping the
evolved peel on desktop and bleaching it on mobile. The evolved renderer now
uses the painted diffuse color for the glow and gives it a lower intensity.
The GLB and the aura are unchanged.

The Game release overlays only `SculptedModel.tsx` onto the current Game
image, rebuilds it in an isolated container, and retains the preceding image
for rollback. The switch script verifies the deployed image, the browser
shader chunk, and the unchanged model hash. Forge, World, and PostgreSQL are
outside this release.

The first switch rolled back when the existing startup sequence exceeded the
HTTP readiness window. The preceding image returned HTTP 200 after rollback.
The second switch allowed up to four minutes for readiness and completed at
20:39:24 UTC on 2026-11-13. See `deployment.txt` and `switch-retry.log`.

The visual check opens the real Bench page and loads its production JavaScript
and GLB. A browser fixture supplies an evolved Bruised Banana and intercepts
player API calls. The before and after runs use the same GLB and check desktop
and an emulated iPhone viewport. Pixel ratios use the full canvas (including
the background and rings) and serve as a check alongside visual inspection.
