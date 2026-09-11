#!/usr/bin/env node
/**
 * AWR/2 §17 CLI adapter for the browser verifier
 * ==============================================
 *
 * `js/verifier.js` is the verifier that runs in the page at
 * verify.modelmarket.dev. It is also a plain CommonJS module, and this file is
 * the §17 command-line contract wrapped around it, so the *same code the page
 * runs* can be driven by `awr/vectors/check_vectors.py` and compared
 * byte-for-byte against the other implementations:
 *
 *     node docs/verifier/js/cli.js verify <file> [--profile L0|L1|L2]
 *                                        [--parents <file>…] [--now <rfc3339>]
 *                                        [--subject <id>]
 *     node docs/verifier/js/cli.js canonicalize <file>
 *     node docs/verifier/js/cli.js digest <file>
 *     node docs/verifier/js/cli.js hashdata <file>
 *
 * Exit codes (§17): 0 = valid / succeeded, 1 = invalid document (a result was
 * produced), 2 = usage or I/O error, 3 = unimplemented subcommand. Only the
 * specified payload goes to stdout; diagnostics go to stderr.
 *
 * `issue` is deliberately **not** implemented and exits 3: the page is a
 * verifier, it holds no private key, and §17 makes `issue` OPTIONAL for
 * verify-only implementations. Nothing else about the verification path is
 * different here — this file adds argument parsing and file I/O and no rules.
 *
 * Run against the vector suite:
 *
 *     PYTHONPATH=awr/reference/python aimarket-hub/.venv/bin/python \
 *       awr/vectors/check_vectors.py --impl "node $PWD/docs/verifier/js/cli.js"
 */
'use strict';

var fs = require('fs');
var AWR = require('./verifier.js');

var EXIT_OK = 0;
var EXIT_INVALID = 1;
var EXIT_USAGE = 2;
var EXIT_UNIMPLEMENTED = 3;

var USAGE = [
  'awr-browser — the verify.modelmarket.dev verifier behind the SPEC.md §17 CLI',
  '',
  'USAGE:',
  '  cli.js verify <file> [--profile L0|L1|L2] [--parents <file>...] [--now <rfc3339>]',
  '                       [--subject <id>] [--skew <seconds>] [--max-depth <n>] [--max-nodes <n>]',
  '                       [--expected-key <did:key|hex>] [--no-legacy]',
  '  cli.js canonicalize <file>',
  '  cli.js digest <file>',
  '  cli.js hashdata <file>',
  '  cli.js issue ...                 (not implemented: verify-only, exits 3)',
  ''
].join('\n');

function fail(message, code) {
  process.stderr.write('awr: ' + message + '\n');
  return code;
}

/** Read a file as text, strictly: invalid UTF-8 is AWR-CANON-005, not U+FFFD. */
function readText(path) {
  var bytes;
  try {
    bytes = fs.readFileSync(path);
  } catch (e) {
    throw { io: true, message: 'cannot read ' + path + ': ' + e.message };
  }
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch (e) {
    throw { code: 'AWR-CANON-005', detail: path + ' is not valid UTF-8' };
  }
}

function toHex(bytes) {
  var out = '';
  for (var i = 0; i < bytes.length; i++) out += ('0' + bytes[i].toString(16)).slice(-2);
  return out;
}

/** §17 `--parents`: each file is one AWR document or a §9 bundle. */
function loadSupporting(paths) {
  var docs = [];
  paths.forEach(function (p) {
    var value = AWR.parseAwrJson(readText(p));
    if (value && typeof value === 'object' && value.awrBundle !== undefined) {
      if (Array.isArray(value.documents)) {
        value.documents.forEach(function (d) { if (d && typeof d === 'object') docs.push(d); });
      }
      return;
    }
    if (Array.isArray(value)) {
      value.forEach(function (d) { if (d && typeof d === 'object') docs.push(d); });
      return;
    }
    if (value && typeof value === 'object') docs.push(value);
  });
  return docs;
}

/**
 * Flag parsing that matches the reference and the Rust build: `--parents`
 * swallows every following non-flag argument.
 */
function parseArgs(args, multi, known, switches) {
  var out = { positional: [], named: {}, multi: {}, switches: {} };
  switches = switches || [];
  var i = 0;
  while (i < args.length) {
    var a = args[i];
    if (a.slice(0, 2) === '--') {
      var name = a.slice(2);
      if (known.indexOf(name) < 0) throw { usage: true, message: 'unknown option --' + name };
      if (switches.indexOf(name) >= 0) {
        out.switches[name] = true;
        i += 1;
        continue;
      }
      var value = args[i + 1];
      if (value === undefined || value.slice(0, 2) === '--') {
        throw { usage: true, message: '--' + name + ' needs a value' };
      }
      i += 2;
      if (multi.indexOf(name) >= 0) {
        out.multi[name] = out.multi[name] || [];
        out.multi[name].push(value);
        while (i < args.length && args[i].slice(0, 2) !== '--') {
          out.multi[name].push(args[i]);
          i += 1;
        }
      } else {
        out.named[name] = value;
      }
      continue;
    }
    out.positional.push(a);
    i += 1;
  }
  return out;
}

function onlyFile(args, command) {
  if (args.length !== 1 || args[0].slice(0, 2) === '--') {
    throw { usage: true, message: command + ' takes exactly one <file>' };
  }
  return args[0];
}

/** --expected-key: a did:key (fragment tolerated) or 64 hex characters. */
function parseExpectedKey(text) {
  var value = String(text).trim();
  if (value.indexOf('did:key:') === 0) {
    try {
      return AWR.parseDidKey(value.split('#')[0]).publicKey;
    } catch (e) {
      throw { usage: true, message: '--expected-key is not a valid did:key: ' + (e.detail || e.message) };
    }
  }
  if (!/^[0-9a-fA-F]{64}$/.test(value)) {
    throw { usage: true, message: '--expected-key must be a did:key or 64 hex characters' };
  }
  var out = new Uint8Array(32);
  for (var i = 0; i < 32; i++) out[i] = parseInt(value.substr(2 * i, 2), 16);
  return out;
}

function cmdVerify(args) {
  var f = parseArgs(args, ['parents'],
    ['profile', 'parents', 'now', 'subject', 'skew', 'max-depth', 'max-nodes',
     'expected-key', 'no-legacy'],
    ['no-legacy']);
  if (f.positional.length !== 1) throw { usage: true, message: 'verify takes exactly one <file>' };
  var opts = {};
  if (f.named.profile !== undefined) {
    if (['L0', 'L1', 'L2'].indexOf(f.named.profile) < 0) {
      throw { usage: true, message: '--profile must be L0, L1 or L2' };
    }
    opts.profile = f.named.profile;
  }
  if (f.named.now !== undefined) {
    var t = Date.parse(f.named.now);
    if (isNaN(t)) throw { usage: true, message: '--now must be an RFC 3339 date-time' };
    opts.now = t;
  }
  if (f.named.skew !== undefined) opts.clockSkewSeconds = Number(f.named.skew);
  if (f.named['max-depth'] !== undefined) opts.chainMaxDepth = Number(f.named['max-depth']);
  if (f.named['max-nodes'] !== undefined) opts.chainMaxNodes = Number(f.named['max-nodes']);
  if (f.named.subject !== undefined) opts.subjectId = f.named.subject;
  // SPEC section 12.4: an AWR/1 signature checked against a key the document
  // itself carries attests no identity, so every section 12 verifier must let the
  // caller name the key out of band. Section 17 spells it --expected-key: a
  // did:key or 64 hex characters.
  if (f.named['expected-key'] !== undefined) {
    opts.expectedKey = parseExpectedKey(f.named['expected-key']);
  }
  if (f.switches['no-legacy']) opts.noLegacy = true;
  opts.parents = loadSupporting(f.multi.parents || []);

  var text = readText(f.positional[0]);
  return AWR.verify(text, opts).then(function (result) {
    process.stdout.write(JSON.stringify(result, null, 2) + '\n');
    (result.reasons || []).forEach(function (r) {
      process.stderr.write('error ' + r.code + ': ' + r.detail + '\n');
    });
    (result.warnings || []).forEach(function (r) {
      process.stderr.write('warning ' + r.code + ': ' + r.detail + '\n');
    });
    return result.valid ? EXIT_OK : EXIT_INVALID;
  });
}

function cmdCanonicalize(args) {
  var value = AWR.parseAwrJson(readText(onlyFile(args, 'canonicalize')));
  // §17: the canonical bytes, no trailing newline.
  process.stdout.write(Buffer.from(AWR.jcsCanonicalizeBytes(value)));
  return Promise.resolve(EXIT_OK);
}

function cmdDigest(args) {
  var value = AWR.parseAwrJson(readText(onlyFile(args, 'digest')));
  return AWR.sriOfDocument(value).then(function (sri) {
    process.stdout.write(sri + '\n');
    return EXIT_OK;
  });
}

function cmdHashdata(args) {
  var doc = AWR.parseAwrJson(readText(onlyFile(args, 'hashdata')));
  if (!doc || typeof doc !== 'object' || Array.isArray(doc)) {
    throw { usage: true, message: 'hashdata expects a JSON object' };
  }
  var proof = Array.isArray(doc.proof) ? doc.proof[0] : doc.proof;
  if (proof === undefined) {
    throw { code: 'AWR-PROOF-001', detail: 'proof missing, so there are no proof options to hash' };
  }
  return AWR.computeHashData(doc, proof).then(function (h) {
    process.stdout.write(toHex(h.proofConfigHash) + '\n' +
                         toHex(h.transformedDocumentHash) + '\n' +
                         toHex(h.hashData) + '\n');
    return EXIT_OK;
  });
}

var COMMANDS = {
  verify: cmdVerify,
  canonicalize: cmdCanonicalize,
  canonicalise: cmdCanonicalize,
  digest: cmdDigest,
  hashdata: cmdHashdata
};

function main() {
  var argv = process.argv.slice(2);
  if (argv.length === 0) {
    process.stderr.write(USAGE);
    return Promise.resolve(EXIT_USAGE);
  }
  var command = argv[0];
  if (command === '-h' || command === '--help' || command === 'help') {
    process.stdout.write(USAGE);
    return Promise.resolve(EXIT_OK);
  }
  if (command === 'issue') {
    process.stderr.write('awr: `issue` is not implemented: this is the browser verifier, it holds ' +
      'no private key. §17 makes issue OPTIONAL for verify-only implementations.\n');
    return Promise.resolve(EXIT_UNIMPLEMENTED);
  }
  var handler = COMMANDS[command];
  if (!handler) {
    process.stderr.write('awr: unimplemented subcommand `' + command + '`\n');
    process.stderr.write(USAGE);
    return Promise.resolve(EXIT_UNIMPLEMENTED);
  }
  return Promise.resolve()
    .then(function () { return handler(argv.slice(1)); })
    .catch(function (e) {
      if (e && e.usage) return fail(e.message, EXIT_USAGE);
      if (e && e.io) return fail(e.message, EXIT_USAGE);
      // A parse or canonicalization failure is an invalid *document* with a
      // reason code, which §17 maps to exit 1, not to a usage error.
      if (e && e.code) {
        process.stderr.write('error ' + e.code + ': ' + (e.detail || e.message) + '\n');
        return EXIT_INVALID;
      }
      process.stderr.write('awr: ' + ((e && e.stack) || e) + '\n');
      return EXIT_USAGE;
    });
}

main().then(function (code) { process.exitCode = code; }, function (e) {
  process.stderr.write('awr: ' + ((e && e.stack) || e) + '\n');
  process.exitCode = EXIT_USAGE;
});
