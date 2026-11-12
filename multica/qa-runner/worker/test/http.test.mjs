import { test } from 'node:test';
import assert from 'node:assert/strict';
import net from 'node:net';
import tls from 'node:tls';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { getStatus } from '../http.mjs';

async function listen(server, host = '127.0.0.1') {
  const sockets = new Set();
  server.on('connection', socket => { sockets.add(socket); socket.on('close', () => sockets.delete(socket)); });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, host, resolve); });
  return { port: server.address().port, close: () => new Promise(resolve => { for (const socket of sockets) socket.destroy(); server.close(resolve); }) };
}

test('GET parses bounded headers even when a large body arrives in the same packet', async () => {
  const server = await listen(net.createServer(socket => socket.once('data', request => {
    assert.match(request.toString(), /^GET \/health HTTP\/1\.1\r\n/);
    socket.end('HTTP/1.1 200 OK\r\nContent-Length: 20000\r\nX-Private: hidden-test-value\r\n\r\n' + 'x'.repeat(20000));
  })));
  try { assert.equal(await getStatus({ hostname: '127.0.0.1', port: server.port, path: '/health' }), 200); }
  finally { await server.close(); }
});

test('500 is retained as a failure status, not promoted to healthy', async () => {
  const server = await listen(net.createServer(socket => socket.once('data', () => socket.end('HTTP/1.1 500 Failed\r\nContent-Length: 0\r\n\r\n'))));
  try { assert.equal(await getStatus({ hostname: '127.0.0.1', port: server.port }), 500); }
  finally { await server.close(); }
});

test('malformed or oversized response headers and premature EOF fail closed', async () => {
  for (const response of ['HTTP/1.1 999 Invalid\r\n\r\n', 'HTTP/1.1 200 OK\r\nX: ' + 'x'.repeat(9000) + '\r\n\r\n', 'HTTP/1.1 200 OK\r\n']) {
    const server = await listen(net.createServer(socket => socket.once('data', () => socket.end(response))));
    try { assert.equal(await getStatus({ hostname: '127.0.0.1', port: server.port }), 0); }
    finally { await server.close(); }
  }
});

test('one end-to-end deadline defeats a continuously active incomplete response', async () => {
  const server = await listen(net.createServer(socket => socket.once('data', () => {
    socket.write('HTTP/1.1 200 OK\r\nX-Progress: ');
    const timer = setInterval(() => socket.write('x'), 10);
    socket.once('close', () => clearInterval(timer));
  })));
  const started = performance.now();
  try {
    assert.equal(await getStatus({ hostname: '127.0.0.1', port: server.port, timeoutMs: 100 }), 0);
    assert.ok(performance.now() - started < 1500);
  } finally { await server.close(); }
});

test('an unreachable TCP endpoint returns only zero', async () => {
  const fixture = await listen(net.createServer());
  const port = fixture.port;
  await fixture.close();
  assert.equal(await getStatus({ hostname: '127.0.0.1', port, timeoutMs: 1000 }), 0);
});

test('a proxy-generated 403 cannot masquerade as the intended HTTPS service', async () => {
  const server = await listen(net.createServer(socket => socket.once('data', request => {
    assert.match(request.toString(), /^CONNECT example\.test:443 HTTP\/1\.1/);
    assert.doesNotMatch(request.toString(), /Authorization|Cookie|token/i);
    socket.end('HTTP/1.1 403 Filtered\r\n\r\n');
  })));
  try { assert.equal(await getStatus({ hostname: 'example.test', port: 443, secure: true, proxy: { hostname: '127.0.0.1', port: server.port } }), 0); }
  finally { await server.close(); }
});

test('TLS certificate verification cannot be disabled by the environment', async () => {
  const folder = await mkdtemp(join(tmpdir(), 'secretless-qa-tls-'));
  let server;
  const previous = process.env.NODE_TLS_REJECT_UNAUTHORIZED;
  try {
    await promisify(execFile)('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', join(folder, 'key.pem'), '-out', join(folder, 'cert.pem'), '-subj', '/CN=localhost', '-days', '1'], { timeout: 15000 });
    let requests = 0;
    const listener = tls.createServer({ key: await readFile(join(folder, 'key.pem')), cert: await readFile(join(folder, 'cert.pem')) }, socket => socket.on('data', () => { requests++; socket.end('HTTP/1.1 200 OK\r\n\r\n'); }));
    listener.on('tlsClientError', () => {});
    server = await listen(listener, 'localhost');
    process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';
    assert.equal(await getStatus({ hostname: 'localhost', port: server.port, secure: true, timeoutMs: 1000 }), 0);
    assert.equal(requests, 0);
  } finally {
    if (previous === undefined) delete process.env.NODE_TLS_REJECT_UNAUTHORIZED;
    else process.env.NODE_TLS_REJECT_UNAUTHORIZED = previous;
    await server?.close();
    await rm(folder, { recursive: true, force: true });
  }
});

test('URL schemes and header-injection arguments are refused without networking', async () => {
  assert.equal(await getStatus({ hostname: 'https://example.test', port: 443 }), 0);
  assert.equal(await getStatus({ hostname: 'example.test', path: '/\r\nAuthorization: injected' }), 0);
  assert.equal(await getStatus({ hostname: 'example.test', timeoutMs: 3001 }), 0);
});
