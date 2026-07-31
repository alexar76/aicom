import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

import { applySecurityHeaders } from './lib/securityHeaders';

export function proxy(_request: NextRequest) {
  const response = NextResponse.next();
  applySecurityHeaders(response.headers);
  return response;
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|icons/).*)'],
};
