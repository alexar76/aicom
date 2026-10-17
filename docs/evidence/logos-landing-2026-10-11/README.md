# LOGOS landing — Observatory design

Published on 2026-10-11 at https://logos.modelmarket.dev/landing/.
The working analytics application remains at https://logos.modelmarket.dev/.

The standalone landing now uses the application's Inter / Space Grotesk / JetBrains Mono typography, restrained jade palette and consistent outline SVG icons. Emoji were removed from both the default HTML and all localized strings. A clearer introduction leads to the live product; the analytical features, NEXUS, assistant, consumption explanation, repository and documentation links remain. The ecosystem links now lead to `ecosystem.modelmarket.dev`.

All four feature section anchors and all seven feature card headings were retained. The 3D scene retains automatic rotation, pointer orbit and zoom; its bloom and colors now match the Observatory design. Keyboard focus and orbit controls are available. Reduced-motion preferences are respected without adding a pause button. The illustrative scene is labeled as a federation model; live measurements belong to the working dashboard. Static, stale endpoint/test counts were replaced with durable read-only and open-source attributes.

Three.js and local fonts are served from the same origin. `logos/scripts/build-landing.sh` rebuilds `scene.bundle.js` from `scene.js` using the frontend's locked dependencies; Three.js licensing is included. Existing Pages packaging still accepts this directory, but **nothing was pushed to or published on GitHub**. The GitHub Pages URL in the user's screenshot therefore still requires a separately authorized publication. The updated landing sources and README destination are part of the Gitea monorepo.

## Verification

- JavaScript syntax, shell syntax and `git diff --check` passed; the 3D bundle built successfully.
- Desktop 1280×800 and mobile 390×844 inspected in the browser. EN/RU/ES/FR/ZH switching preserves all 24 SVG icons. No body horizontal overflow in any of the five languages; English is the default unless an explicit saved or URL language is supplied.
- Pointer drag visibly changes the 3D orientation; automatic animation continues. No pause control was introduced.
- NEXUS anchor navigation reaches the section and updates the active navigation state.
- No captured browser console errors. Screenshots are English.
- All 21 requested published HTML/CSS/JS/icon/font files matched the local bytes. See `production-checks.json` for hashes.
- `/landing` redirects to `/landing/`; the original dashboard entry asset remains `index-BIVBYaWC.js`; backend health is OK.

## Publication

Release directory: `/var/www/logos-landing-20261011/landing` on the existing LOGOS host. Only the `/landing` redirect and `/landing/` static location were added to its nginx vhost. No backend restart or container replacement occurred. The existing container ID matched before and after. The repository nginx template includes the same separate route.

The immediate request following nginx reload initially reached an old worker and returned the dashboard HTML; a subsequent request returned the correct byte-identical landing. `deploy.sh` now waits for the expected HTML rather than assuming the reload is instantaneous.

Remote workspace: `/root/logos-landing-20261011`, including the original vhost backup. To remove the new route, run `bash /root/logos-landing-20261011/rollback.sh` on that host. This restores the preceding vhost without restarting LOGOS.
