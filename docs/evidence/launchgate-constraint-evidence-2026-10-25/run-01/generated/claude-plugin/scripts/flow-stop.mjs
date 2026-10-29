#!/usr/bin/env node
// WARDEN flow guard, Stop: tells the user which outside text the answer drew on. Never blocks.
import { flowGuardMain } from './flow-guard.mjs';
try { flowGuardMain(['stop']); } catch { /* say nothing */ }
