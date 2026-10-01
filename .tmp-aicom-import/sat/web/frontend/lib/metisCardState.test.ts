import { describe, expect, it } from 'vitest';
import { metisCardState, type MetisStatusInput } from './metisCardState';

function payload(over: Partial<MetisStatusInput> = {}): MetisStatusInput {
  return {
    status: 'inactive',
    ecosystem: {
      deployed: false,
      url: 'http://127.0.0.1:8080',
      url_source: 'default',
      url_env_vars: ['AIFACTORY_METIS_URL', 'METIS_URL'],
      configured: false,
      ...(over.ecosystem ?? {}),
    },
    factory: { blocked_reason: null, ...(over.factory ?? {}) },
    ...(over.status ? { status: over.status } : {}),
  } as MetisStatusInput;
}

describe('metisCardState', () => {
  it('says "not configured", not "no", when no Metis URL was ever set', () => {
    const s = metisCardState(
      payload({
        status: 'unconfigured',
        ecosystem: {
          deployed: false,
          state: 'unconfigured',
          configured: false,
          url: 'http://127.0.0.1:8080',
          url_source: 'default',
          url_env_vars: ['AIFACTORY_METIS_URL', 'METIS_URL'],
        },
        factory: { blocked_reason: 'metis-unconfigured' },
      }),
    );

    expect(s.deployedKey).toBe('dashboard.metis.notConfigured');
    expect(s.statusKey).toBe('dashboard.metis.statusUnconfigured');
    expect(s.tone).toBe('warn');
    expect(s.reason?.key).toBe('dashboard.metis.reasonUnconfigured');
    // The operator must be told which variable to set.
    expect(s.reason?.vars.vars).toContain('AIFACTORY_METIS_URL');
    expect(s.showProbedUrl).toBe(true);
  });

  it('says "not responding" when a configured Metis did not answer', () => {
    const s = metisCardState(
      payload({
        status: 'inactive',
        ecosystem: {
          deployed: false,
          state: 'unreachable',
          configured: true,
          url: 'https://metis.example.invalid',
          url_source: 'AIFACTORY_METIS_URL',
        },
        factory: { blocked_reason: 'metis-unreachable' },
      }),
    );

    expect(s.deployedKey).toBe('dashboard.metis.notResponding');
    expect(s.statusKey).toBe('dashboard.metis.statusInactive');
    expect(s.tone).toBe('off');
    expect(s.reason?.key).toBe('dashboard.metis.reasonUnreachable');
    expect(s.reason?.vars.url).toBe('https://metis.example.invalid');
  });

  it('names the gate when Metis is up but the factory is not using it', () => {
    const s = metisCardState(
      payload({
        status: 'inactive',
        ecosystem: { deployed: true, state: 'deployed', configured: true, url: 'https://metis.example.invalid' },
        factory: { blocked_reason: 'gate-disabled' },
      }),
    );

    expect(s.deployedKey).toBe('dashboard.metis.yes');
    expect(s.reason?.key).toBe('dashboard.metis.reasonGateDisabled');
    expect(s.showProbedUrl).toBe(false);
  });

  it('is clean when Metis is deployed and used', () => {
    const s = metisCardState(
      payload({
        status: 'active',
        ecosystem: { deployed: true, state: 'deployed', configured: true, url: 'https://metis.example.invalid' },
        factory: { blocked_reason: null },
      }),
    );

    expect(s.tone).toBe('ok');
    expect(s.statusKey).toBe('dashboard.metis.statusActive');
    expect(s.deployedKey).toBe('dashboard.metis.yes');
    expect(s.reason).toBeNull();
    expect(s.showProbedUrl).toBe(false);
  });

  it('degrades to "not responding" against a backend that sends no state', () => {
    // Never invent "not configured" from a payload that cannot express it: that
    // would accuse the operator of forgetting something they may have set.
    const s = metisCardState({
      status: 'inactive',
      ecosystem: { deployed: false, url: 'https://metis.example.invalid' },
      factory: {},
    });

    expect(s.ecosystemState).toBe('unreachable');
    expect(s.deployedKey).toBe('dashboard.metis.notResponding');
    expect(s.reason).toBeNull();
  });
});
