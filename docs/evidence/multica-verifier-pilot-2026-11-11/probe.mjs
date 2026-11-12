import { registerHooks } from 'node:module';

const probeUrl = new URL(import.meta.url);
const smokeUrl = new URL('../../../multica/qa-runner/worker/smoke.mjs', probeUrl);
const modelMarketStatus = Number(probeUrl.searchParams.get('modelmarket'));
if (modelMarketStatus !== 200 && modelMarketStatus !== 503) {
  throw new Error('Expected a fixed fixture status (200 or 503)');
}

// Replace only the worker's transport dependency. The actual CLI parses its own
// arguments, executes runSmoke, writes the report, and sets the exit status.
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (context.parentURL === smokeUrl.href && specifier === './http.mjs') {
      return { url: probeUrl.href, shortCircuit: true };
    }
    if (/^(?:node:)?(?:http|https|net|tls|dns|dgram|http2)(?:\/|$)/.test(specifier)) {
      throw new Error('Network modules are unavailable in the fixture');
    }
    return nextResolve(specifier, context);
  },
});

export function getStatus(request) {
  if (request.hostname === 'backend' && request.path === '/health') return 200;
  if (request.hostname === 'modelmarket.dev' && request.path === '/') return modelMarketStatus;
  if (request.hostname === 'hub.attestedmemory.net' && request.path === '/') return 200;
  throw new Error('Unexpected target for the fixed smoke job');
}
