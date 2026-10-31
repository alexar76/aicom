# Local deepmerge security backport

Derived from MIT-licensed TehShrike/deepmerge 4.3.1 (bundled CJS entrypoint).
The original license is retained. This is a local first-party fork, not an upstream release.

Both target-copy and source-copy loops reject `__proto__`, `constructor`, and `prototype`.
Writes define own data properties, never invoke the prototype setter. The upstream API,
array merging, symbols, custom merge functions and clone controls are preserved.
Regression tests cover the null-prototype, null-placeholder, own-key and nested cases.
Tracking: https://github.com/TehShrike/deepmerge/issues/273 (upstream disputes the advisory).
