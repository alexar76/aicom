/** Resume an admin tab after login without accepting external or nested redirects. */
export function adminReturnPath(candidate: string | null): string {
  return candidate && /^\/admin(?:[?#]|$)/.test(candidate) && !/[\\\u0000-\u001f\u007f]/.test(candidate)
    ? candidate
    : '/admin?tab=dashboard';
}

export function adminLoginPath(returnTo: string): string {
  return `/admin/login?next=${encodeURIComponent(adminReturnPath(returnTo))}`;
}
