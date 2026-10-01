import type { Metadata } from 'next';
import { FactoryAgentsRosterClient } from '@/components/agents/FactoryAgentsRosterClient';
import { listFactoryAgents } from '@/lib/server-api';

export const dynamic = 'force-dynamic';

export const metadata: Metadata = {
  title: { absolute: 'Factory agents — mesh participants · AI-Factory' },
  description:
    'Autonomous agents the factory built and shipped. SDK, capabilities invoked on the mesh, spend and invoke counters.',
};

export default async function FactoryAgentsPage() {
  const initial = await listFactoryAgents();
  return <FactoryAgentsRosterClient initial={initial} />;
}
