import { test } from 'node:test';
import assert from 'node:assert/strict';
import net from 'node:net';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { tcpConnect, proxyStatus, plainProxyStatus } from '../probe.mjs';

async function server(handler) {
  const listener = net.createServer(handler);
  await new Promise(resolve => listener.listen(0, '127.0.0.1', resolve));
  return { listener, port: listener.address().port, close: () => new Promise(resolve => listener.close(resolve)) };
}

test('a receiver accepting TCP but never replying is reachable, not a successful deny', async () => {
  const fixture = await server(socket => socket.on('data', () => {}));
  try { assert.equal(await tcpConnect('127.0.0.1', fixture.port), true); }
  finally { await fixture.close(); }
});

test('proxy refusals require a parsed HTTP status, not an arbitrary connection failure', async () => {
  const fixture = await server(socket => socket.once('data', request => {
    assert.match(request.toString(), /^CONNECT example\.invalid:443 HTTP\/1\.1/);
    socket.end('HTTP/1.1 403 Filtered\r\nContent-Length: 0\r\n\r\n');
  }));
  try { assert.equal(await proxyStatus(`http://127.0.0.1:${fixture.port}`, 'example.invalid'), 403); }
  finally { await fixture.close(); }
});

test('ordinary HTTP proxy probes retain the explicit forbidden destination port', async () => {
  const fixture = await server(socket => socket.once('data', request => {
    assert.match(request.toString(), /^GET http:\/\/dev\.example\.com:8443\//);
    socket.end('HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n');
  }));
  try { assert.equal(await plainProxyStatus(`http://127.0.0.1:${fixture.port}`, 'dev.example.com', 8443), 502); }
  finally { await fixture.close(); }
});

test('a coalesced response body does not consume the bounded header budget', async () => {
  const fixture = await server(socket => socket.once('data', () => {
    socket.end('HTTP/1.1 403 Filtered\r\nContent-Length: 16384\r\n\r\n' + 'x'.repeat(16384));
  }));
  try { assert.equal(await proxyStatus(`http://127.0.0.1:${fixture.port}`, 'example.invalid'), 403); }
  finally { await fixture.close(); }
});

test('standalone CLI exits nonzero when a receiver is reachable', async () => {
  const fixture = await server(socket => socket.once('data', () => socket.end('HTTP/1.1 403 Filtered\r\nContent-Length: 0\r\n\r\n')));
  try {
    const config = { proxy: `http://127.0.0.1:${fixture.port}`, receiverIp: '127.0.0.1', receiverPort: fixture.port,
      directIp: '127.0.0.1', directPort: fixture.port, externalDns: '127.0.0.1', allowUrl: 'https://localhost/',
      portTestHost: 'localhost', backendUrl: `http://127.0.0.1:${fixture.port}/health`, dnsNonce: 'local-test' };
    await assert.rejects(promisify(execFile)(process.execPath, [fileURLToPath(new URL('../probe.mjs', import.meta.url)), JSON.stringify(config)]), error => {
      assert.equal(error.code, 1);
      assert.equal(JSON.parse(error.stdout).passed, false);
      return true;
    });
  } finally { await fixture.close(); }
});
