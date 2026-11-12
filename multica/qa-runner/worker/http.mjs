/** Bounded HTTP/1.1 status probe. Bodies, headers and error text never leave this module. */
import net from 'node:net';
import tls from 'node:tls';

const MAX_HEADER_BYTES = 8192;

function validTarget(hostname, port, path) {
  return typeof hostname === 'string' && /^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$/.test(hostname)
    && Number.isInteger(port) && port >= 1 && port <= 65535
    && typeof path === 'string' && path.startsWith('/') && !/[\r\n\0]/.test(path) && path.length <= 1024;
}

/** Targets are supplied only by the fixed job definition; no caller URL is accepted by the smoke CLI. */
export function getStatus({ hostname, port = 80, path = '/', secure = false, proxy, timeoutMs = 3000 }) {
  if (!validTarget(hostname, port, path) || !Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 3000
      || (proxy && !validTarget(proxy.hostname, proxy.port, '/'))) return Promise.resolve(0);
  return new Promise(resolve => {
    const sockets = new Set();
    let finished = false;
    const finish = status => {
      if (finished) return;
      finished = true;
      clearTimeout(deadline);
      for (const socket of sockets) socket.destroy();
      resolve(Number.isInteger(status) && status >= 100 && status <= 599 ? status : 0);
    };
    // One deadline covers lookup, TCP, CONNECT, TLS and response headers together.
    const deadline = setTimeout(() => finish(0), timeoutMs);
    const track = socket => {
      sockets.add(socket);
      socket.on('error', () => finish(0));
      return socket;
    };
    const readStatus = (socket, request, next) => {
      let response = '';
      const onEnd = () => finish(0);
      const onData = chunk => {
        response += chunk.toString('latin1');
        const boundary = response.indexOf('\r\n\r\n');
        if (boundary < 0) {
          if (response.length > MAX_HEADER_BYTES) finish(0);
          return;
        }
        // The same packet can contain a large body. Only headers consume the header budget.
        if (boundary > MAX_HEADER_BYTES) { finish(0); return; }
        socket.removeListener('data', onData);
        socket.removeListener('end', onEnd);
        const status = Number(/^HTTP\/1\.[01] ([1-5]\d{2})(?:[ \t]|\r\n)/.exec(response)?.[1] ?? 0);
        next(status);
      };
      socket.on('data', onData);
      socket.once('end', onEnd);
      socket.write(request);
    };
    const sendGet = socket => readStatus(socket,
      `GET ${path} HTTP/1.1\r\nHost: ${hostname}${port === 80 || port === 443 ? '' : ':' + port}\r\nConnection: close\r\nAccept: */*\r\n\r\n`, finish);
    const startRequest = socket => {
      if (!secure) { sendGet(socket); return; }
      const encrypted = track(tls.connect({
        socket, servername: hostname, rejectUnauthorized: true,
        checkServerIdentity: tls.checkServerIdentity, ca: tls.rootCertificates,
        ALPNProtocols: ['http/1.1'], minVersion: 'TLSv1.2',
      }));
      encrypted.once('secureConnect', () => {
        if (!encrypted.authorized) { finish(0); return; }
        sendGet(encrypted);
      });
    };
    const socket = track(net.createConnection({ host: proxy?.hostname ?? hostname, port: proxy?.port ?? port }));
    socket.once('connect', () => {
      if (finished) return;
      if (!proxy) { startRequest(socket); return; }
      readStatus(socket, `CONNECT ${hostname}:${port} HTTP/1.1\r\nHost: ${hostname}:${port}\r\n\r\n`, status => {
        // A proxy refusal is not an HTTP status from the intended HTTPS service.
        if (status !== 200) { finish(0); return; }
        startRequest(socket);
      });
    });
  });
}
