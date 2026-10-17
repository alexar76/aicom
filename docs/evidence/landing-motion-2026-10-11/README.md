# Production 3D motion — 2026-10-11

Both factory and machine-economy models rotate as complete structures, retain internal animation, and support pointer dragging and arrow keys. Pause/play controls were removed. Reduced-motion preference suppresses automatic animation but preserves manual control; offscreen/background rendering is suspended.

Validation: TypeScript passed, Next production build passed, standalone atlas validation passed for EN/RU/ES/FR/ZH. Both production renderers are byte-identical. HTTP checks passed for five factory locales and guides, five atlas pages, API health, lead/docs routes and scene assets. Security headers were preserved; atlas legacy sections and sitemap URLs were compared before its atomic switch. The backend was not restarted by this frontend rollout.

Browser: both WebGL canvases became ready with no console errors; full-model motion and dragging were visually verified. Factory stage 03 changed the explanation; atlas trade filtering returned one project and resetting returned nine. Arrow-key handling was exercised. At a 390 px viewport neither page overflowed horizontally. Mouse dragging was also checked in that layout; a physical touchscreen was not tested.

Deployment: factory container `aicom-frontend-motion-20261011`, image `ai-factory-frontend:motion-20261011`, loopback 9087. Atlas `/var/www/modeldev.modelmarket.dev` points to `/var/www/modeldev-atlas-motion-20261011`. Protected release `/root/motion-release-20261011/` contains backups and separate `rollback-factory.sh` / `rollback-atlas.sh`. Previous releases remain available. No GitHub push.

Screenshots: `factory.png`, `atlas.png`, `atlas-drag.png`, `atlas-mobile.png`. These are still frames; live motion was checked in the browser. Procurement evidence is in `../procurement-production-2026-10-11/`.
