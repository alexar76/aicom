/** Browser WebAuthn helpers for admin passkey login / registration. */

function b64urlToBuffer(b64url: string): ArrayBuffer {
  const pad = '='.repeat((4 - (b64url.length % 4)) % 4);
  const b64 = (b64url + pad).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(b64);
  const buf = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) buf[i] = raw.charCodeAt(i);
  return buf.buffer;
}

function bufferToB64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function decodeCreationOptions(publicKey: Record<string, unknown>): PublicKeyCredentialCreationOptions {
  const pk = { ...publicKey } as Record<string, unknown>;
  if (typeof pk.challenge === 'string') pk.challenge = b64urlToBuffer(pk.challenge);
  const user = pk.user as Record<string, unknown> | undefined;
  if (user && typeof user.id === 'string') {
    user.id = b64urlToBuffer(user.id);
  }
  const exclude = pk.excludeCredentials as Array<Record<string, unknown>> | undefined;
  if (exclude) {
    pk.excludeCredentials = exclude.map((c) => ({
      ...c,
      id: typeof c.id === 'string' ? b64urlToBuffer(c.id) : c.id,
    }));
  }
  return pk as unknown as PublicKeyCredentialCreationOptions;
}

function decodeRequestOptions(publicKey: Record<string, unknown>): PublicKeyCredentialRequestOptions {
  const pk = { ...publicKey } as Record<string, unknown>;
  if (typeof pk.challenge === 'string') pk.challenge = b64urlToBuffer(pk.challenge);
  const allow = pk.allowCredentials as Array<Record<string, unknown>> | undefined;
  if (allow) {
    pk.allowCredentials = allow.map((c) => ({
      ...c,
      id: typeof c.id === 'string' ? b64urlToBuffer(c.id) : c.id,
    }));
  }
  return pk as unknown as PublicKeyCredentialRequestOptions;
}

export function credentialToJson(cred: PublicKeyCredential): Record<string, unknown> {
  const response = cred.response as AuthenticatorAttestationResponse | AuthenticatorAssertionResponse;
  const out: Record<string, unknown> = {
    id: cred.id,
    rawId: bufferToB64url(cred.rawId),
    type: cred.type,
    response: {
      clientDataJSON: bufferToB64url(response.clientDataJSON),
    },
  };
  if ('attestationObject' in response) {
    (out.response as Record<string, unknown>).attestationObject = bufferToB64url(
      (response as AuthenticatorAttestationResponse).attestationObject
    );
  }
  if ('authenticatorData' in response) {
    (out.response as Record<string, unknown>).authenticatorData = bufferToB64url(
      (response as AuthenticatorAssertionResponse).authenticatorData
    );
  }
  if ('signature' in response) {
    (out.response as Record<string, unknown>).signature = bufferToB64url(
      (response as AuthenticatorAssertionResponse).signature
    );
  }
  return out;
}

export async function createPasskey(publicKey: Record<string, unknown>): Promise<Record<string, unknown>> {
  if (!window.PublicKeyCredential) {
    throw new Error('WebAuthn is not supported in this browser');
  }
  const cred = (await navigator.credentials.create({
    publicKey: decodeCreationOptions(publicKey),
  })) as PublicKeyCredential | null;
  if (!cred) throw new Error('Passkey registration was cancelled');
  return credentialToJson(cred);
}

export async function getPasskeyAssertion(
  publicKey: Record<string, unknown>
): Promise<Record<string, unknown>> {
  if (!window.PublicKeyCredential) {
    throw new Error('WebAuthn is not supported in this browser');
  }
  const cred = (await navigator.credentials.get({
    publicKey: decodeRequestOptions(publicKey),
  })) as PublicKeyCredential | null;
  if (!cred) throw new Error('Passkey sign-in was cancelled');
  return credentialToJson(cred);
}
