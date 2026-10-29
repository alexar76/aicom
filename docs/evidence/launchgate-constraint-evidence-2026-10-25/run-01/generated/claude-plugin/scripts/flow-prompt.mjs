#!/usr/bin/env node
// WARDEN flow guard, UserPromptSubmit: remembers what the user asked for. A destination the user named
// (an address, a host, a recipient) may be reached later even after the session read outside text.
import { flowGuardMain } from './flow-guard.mjs';
try { flowGuardMain(['prompt']); } catch { /* record nothing */ }
