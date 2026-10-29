#!/usr/bin/env node
// WARDEN flow guard, PostToolUse: records outside text and fingerprints of private data the result brought in.
import { flowGuardMain } from './flow-guard.mjs';
try { flowGuardMain(['post']); } catch { /* record nothing */ }
