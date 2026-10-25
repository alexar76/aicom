// Route this private production seller through the user's SSH tunnel.
// x402 payment terms and signatures remain unchanged; only the HTTP transport changes.
export const SELLER = "https://esim.modelmarket.dev/stand";
const seller = new URL(SELLER);
const tunnel = "http://127.0.0.1:19489";
const nativeFetch = globalThis.fetch;

globalThis.fetch = (input, init) => {
  const request = new Request(input, init);
  const url = new URL(request.url);
  if (url.origin === seller.origin && (url.pathname === seller.pathname || url.pathname.startsWith(seller.pathname + "/"))) {
    const target = tunnel + (url.pathname.slice(seller.pathname.length) || "/") + url.search;
    return nativeFetch(new Request(target, request));
  }
  return nativeFetch(request);
};
