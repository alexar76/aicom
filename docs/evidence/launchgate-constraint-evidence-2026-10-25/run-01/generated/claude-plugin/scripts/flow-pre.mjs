#!/usr/bin/env node
// WARDEN flow guard, PreToolUse: asks or denies a call that could send data out after the session read
// outside text. Logic lives in flow-guard.mjs (generated from the package). Never blocks on its own failure.
import { flowGuardMain } from './flow-guard.mjs';
try { flowGuardMain(['pre']); } catch { /* decide nothing */ }
