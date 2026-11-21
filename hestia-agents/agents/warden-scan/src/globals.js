// Injected into every module of the bundle (esbuild --inject): the names WARDEN's scan uses
// as globals in Node.
export { Buffer, TextDecoder } from "./node-shims.js";
