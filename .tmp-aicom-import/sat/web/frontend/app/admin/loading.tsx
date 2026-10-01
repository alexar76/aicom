import { AdminAuthGate } from '@/components/admin/AdminAuthGate';

export default function AdminLoading() {
  return <AdminAuthGate locale="en" label="Opening admin…" />;
}
