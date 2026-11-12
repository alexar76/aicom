import net from 'node:net';
import tls from 'node:tls';
import dns from 'node:dns/promises';
import { pathToFileURL } from 'node:url';

const TIMEOUT = 3000;

export function tcpConnect(host, port, timeout = TIMEOUT) {
  return new Promise(resolve => {
    const socket = net.createConnection({ host, port });
    const finish = reachable => { socket.destroy(); resolve(reachable); };
    socket.setTimeout(timeout, () => finish(false));
    socket.once('connect', () => finish(true));
    socket.once('error', () => finish(false));
  });
}

function header(socket, request) {
  return new Promise((resolve, reject) => {
    let response = '';
    const failed = () => { socket.destroy(); reject(new Error('probe connection failed')); };
    socket.setTimeout(TIMEOUT, failed);
    socket.once('error', failed);
    socket.on('data', chunk => {
      response += chunk.toString('latin1');
      const boundary = response.indexOf('\r\n\r\n');
      if (boundary >= 0) {
        if (boundary > 8192) { failed(); return; }
        socket.removeAllListeners('data');
        socket.removeListener('error', failed);
        socket.setTimeout(0);
        resolve(Number(/^HTTP\/1\.[01] (\d{3})\b/.exec(response)?.[1] ?? 0));
      } else if (response.length > 8192) failed();
    });
    socket.once('end', () => { if (!response.includes('\r\n\r\n')) failed(); });
    socket.write(request);
  });
}

async function tunnel(proxy, hostname, port) {
  const socket = net.createConnection({ host: proxy.hostname, port: Number(proxy.port || 80) });
  const status = await header(socket, `CONNECT ${hostname}:${port} HTTP/1.1\r\nHost: ${hostname}:${port}\r\n\r\n`);
  return { socket, status };
}

export async function proxyStatus(proxyUrl, hostname, port = 443) {
  try {
    const result = await tunnel(new URL(proxyUrl), hostname, port);
    result.socket.destroy();
    return result.status;
  } catch { return 0; }
}

export async function plainProxyStatus(proxyUrl, hostname, port) {
  const proxy = new URL(proxyUrl);
  const socket = net.createConnection({ host: proxy.hostname, port: Number(proxy.port || 80) });
  try {
    return await header(socket, `GET http://${hostname}:${port}/ HTTP/1.1\r\nHost: ${hostname}:${port}\r\nConnection: close\r\n\r\n`);
  } catch { return 0; } finally { socket.destroy(); }
}

async function httpsStatus(proxyUrl, urlText) {
  const url = new URL(urlText);
  let socket;
  try {
    const result = await tunnel(new URL(proxyUrl), url.hostname, 443);
    socket = result.socket;
    if (result.status !== 200) return 0;
    socket = tls.connect({ socket, servername: url.hostname, rejectUnauthorized: true });
    return await header(socket, `GET ${url.pathname} HTTP/1.1\r\nHost: ${url.hostname}\r\nConnection: close\r\n\r\n`);
  } catch { return 0; } finally { socket?.destroy(); }
}

async function httpStatus(urlText) {
  const url = new URL(urlText);
  const socket = net.createConnection({ host: url.hostname, port: Number(url.port || 80) });
  try {
    return await header(socket, `GET ${url.pathname} HTTP/1.1\r\nHost: ${url.hostname}\r\nConnection: close\r\n\r\n`);
  } catch { return 0; } finally { socket.destroy(); }
}

export async function runProbes(config) {
  const checks = [];
  const add = (name, pass) => checks.push({ name, pass });
  add('proxy rejects unknown host', await proxyStatus(config.proxy, 'example.invalid') === 403);
  add('proxy rejects CONNECT to SSH port', await proxyStatus(config.proxy, new URL(config.allowUrl).hostname, 22) === 403);
  // A connect counts as failure even if a receiver never sends an HTTP reply.
  add('host-gateway receiver blocked', !await tcpConnect(config.receiverIp, config.receiverPort));
  add('direct public IPv4 bypass blocked', !await tcpConnect(config.directIp, config.directPort));
  add('direct SSH bypass blocked', !await tcpConnect(config.directIp, 22));
  if (config.ipv6) add('direct IPv6 bypass blocked', !await tcpConnect(config.ipv6, config.directPort));
  const allowedStatus = await httpsStatus(config.proxy, config.allowUrl);
  add('approved HTTPS endpoint reachable without credentials', allowedStatus >= 200 && allowedStatus < 500);
  add('backend health reachable without proxy', await httpStatus(config.backendUrl) === 200);
  // Make these endpoints operator-controlled and known listening before running the probe.
  for (const port of [80, 8443]) {
    const status = await plainProxyStatus(config.proxy, config.portTestHost, port);
    add(`plain HTTP proxy cannot reach port ${port}`, status === 403 || status === 502 || status === 503 || status === 504);
  }
  const randomName = `${config.dnsNonce}.example.com`;
  const resolver = new dns.Resolver({ timeout: TIMEOUT, tries: 1 });
  resolver.setServers([config.externalDns]);
  let dnsReached = true;
  try { await resolver.resolve4(randomName); } catch (error) {
    // NXDOMAIN proves the resolver answered and therefore the DNS channel exists.
    dnsReached = !['ETIMEOUT', 'ECONNREFUSED', 'ENETUNREACH', 'EHOSTUNREACH'].includes(error.code);
  }
  add('direct external DNS blocked', !dnsReached);
  return { passed: checks.every(check => check.pass), checks };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const result = await runProbes(JSON.parse(process.argv[2]));
    console.log(JSON.stringify(result));
    if (!result.passed) process.exitCode = 1;
  }
  catch { console.log(JSON.stringify({ passed: false, error: 'probe execution failed' })); process.exitCode = 2; }
}
