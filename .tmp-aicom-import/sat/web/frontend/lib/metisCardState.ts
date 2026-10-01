/**
 * What the Metis dashboard card should say, derived from the admin status payload.
 *
 * Pure on purpose: the card used to render a flat "No" under "Metis deployed"
 * whenever its health probe failed, including the common case where no Metis URL
 * had been configured at all and the probe hit a localhost fallback. Metis was
 * live and answering at its real address, so the card stated something false about
 * the world. "Not configured" is a statement about us; "not responding" is a
 * statement about Metis. Keeping that decision here, out of JSX, is what makes it
 * testable — the frontend test harness is node-only, with no DOM.
 */

export type MetisEcosystemState = 'deployed' | 'unreachable' | 'unconfigured';

export type MetisBlockedReason = 'gate-disabled' | 'metis-unconfigured' | 'metis-unreachable' | null;

export type MetisStatusInput = {
  status: 'active' | 'inactive' | 'unconfigured';
  ecosystem: {
    deployed: boolean;
    state?: MetisEcosystemState;
    configured?: boolean;
    url: string;
    url_source?: string;
    url_env_vars?: string[];
  };
  factory: { blocked_reason?: MetisBlockedReason };
};

export type MetisCardState = {
  tone: 'ok' | 'warn' | 'off';
  /** i18n key for the badge text. */
  statusKey: string;
  /** i18n key for the "Metis deployed" tile value. */
  deployedKey: string;
  ecosystemState: MetisEcosystemState;
  /** i18n key + interpolation for why the factory is not using Metis, or null. */
  reason: { key: string; vars: Record<string, string> } | null;
  /** Show the address that was actually probed — the single most useful hint. */
  showProbedUrl: boolean;
};

const DEFAULT_ENV_VARS = ['AIFACTORY_METIS_URL', 'METIS_URL'];

export function metisCardState(data: MetisStatusInput): MetisCardState {
  // A backend that has not been updated sends only `deployed`. Treat a failed
  // probe there as "unreachable": it is the weaker claim of the two, and it never
  // asserts that an operator forgot something they may well have configured.
  const ecosystemState: MetisEcosystemState =
    data.ecosystem.state ?? (data.ecosystem.deployed ? 'deployed' : 'unreachable');

  const tone = data.status === 'active' ? 'ok' : ecosystemState === 'unconfigured' ? 'warn' : 'off';

  const statusKey =
    data.status === 'active'
      ? 'dashboard.metis.statusActive'
      : ecosystemState === 'unconfigured'
        ? 'dashboard.metis.statusUnconfigured'
        : 'dashboard.metis.statusInactive';

  const deployedKey =
    ecosystemState === 'deployed'
      ? 'dashboard.metis.yes'
      : ecosystemState === 'unconfigured'
        ? 'dashboard.metis.notConfigured'
        : 'dashboard.metis.notResponding';

  const envVars = (data.ecosystem.url_env_vars ?? DEFAULT_ENV_VARS).join(' / ');
  const blocked = data.factory.blocked_reason ?? null;
  let reason: MetisCardState['reason'] = null;
  if (blocked === 'gate-disabled') {
    reason = { key: 'dashboard.metis.reasonGateDisabled', vars: {} };
  } else if (blocked === 'metis-unconfigured') {
    reason = { key: 'dashboard.metis.reasonUnconfigured', vars: { vars: envVars } };
  } else if (blocked === 'metis-unreachable') {
    reason = { key: 'dashboard.metis.reasonUnreachable', vars: { url: data.ecosystem.url } };
  }

  return {
    tone,
    statusKey,
    deployedKey,
    ecosystemState,
    reason,
    showProbedUrl: ecosystemState !== 'deployed',
  };
}
