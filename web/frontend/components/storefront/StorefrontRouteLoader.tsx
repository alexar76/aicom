import { Loader2 } from 'lucide-react';

export function StorefrontRouteLoader({
  label = 'Loading product…',
}: {
  label?: string;
}) {
  return (
    <div
      className="min-h-[60vh] flex items-center justify-center px-4"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="text-center">
        <Loader2 className="h-12 w-12 animate-spin text-indigo-400 mx-auto mb-4" aria-hidden />
        <p className="text-gray-400 text-sm">{label}</p>
      </div>
    </div>
  );
}
