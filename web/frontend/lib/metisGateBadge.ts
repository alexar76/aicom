/** Factory pipeline Metis confidence-gate snapshot (`product.metis_gate` from pipeline_worker). */

export type MetisGatePayload = {
  stage?: string;
  ok?: boolean;
  status?: string;
  verify_score?: number;
  verified?: boolean;
  route?: string;
  blocked?: boolean;
  at?: number;
};

export type MetisGateBadgeVariant = 'success' | 'warning' | 'error' | 'default';

export function resolveMetisGateBadge(gate?: MetisGatePayload | null): {
  used: boolean;
  variant: MetisGateBadgeVariant;
  labelKey: 'pipeline.metis.used' | 'pipeline.metis.flagged' | 'pipeline.metis.pending';
  titleParts: string[];
} {
  if (!gate || typeof gate !== 'object' || gate.at == null) {
    return {
      used: false,
      variant: 'default',
      labelKey: 'pipeline.metis.pending',
      titleParts: [],
    };
  }

  const parts: string[] = [];
  if (gate.stage) parts.push(`stage: ${gate.stage}`);
  if (gate.route) parts.push(`route: ${gate.route}`);
  if (typeof gate.verify_score === 'number') {
    parts.push(`score: ${gate.verify_score.toFixed(2)}`);
  }
  if (gate.status) parts.push(`status: ${gate.status}`);

  if (gate.ok === false) {
    return {
      used: true,
      variant: gate.blocked ? 'error' : 'warning',
      labelKey: 'pipeline.metis.flagged',
      titleParts: parts,
    };
  }

  return {
    used: true,
    variant: 'success',
    labelKey: 'pipeline.metis.used',
    titleParts: parts,
  };
}
