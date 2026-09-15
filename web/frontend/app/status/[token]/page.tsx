import LeadStatusPage from '@/components/LeadStatusPage';

export default async function Page({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <LeadStatusPage token={token} />;
}
