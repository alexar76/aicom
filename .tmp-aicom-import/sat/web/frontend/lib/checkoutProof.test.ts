/**
 * The checkout caches the buyer's ownership signature so polling for confirmations does
 * not ask them to sign again. It used to keep that cache after the server refused the
 * signature too, so a buyer who signed with the wrong account, switched accounts and
 * pressed "Try Again" resent the same refused signature until they reloaded the page.
 */

import { describe, expect, it } from 'vitest';

import { ApiRequestError, keepPaymentProofAfterError, paymentRecoveryHint } from './api';

const endpoint = '/payment/confirm/pay-1';

describe('checkout ownership proof after a failed confirm', () => {
  it('is kept only while the transfer awaits confirmations', () => {
    const pending = new ApiRequestError('awaiting', {
      status: 409, endpoint, detailPayload: { status: 'pending_confirmation' },
    });
    expect(keepPaymentProofAfterError(pending)).toBe(true);
  });

  it('is dropped when the server refused the signature or anything else', () => {
    const refused = new ApiRequestError('Payer signature does not authorize this checkout', {
      status: 403, endpoint, detailPayload: { recovery: 'Sign with the wallet that sent it' },
    });
    const used = new ApiRequestError('used', { status: 409, endpoint, detailPayload: { message: 'used' } });
    expect(keepPaymentProofAfterError(refused)).toBe(false);
    expect(keepPaymentProofAfterError(used)).toBe(false);
    expect(keepPaymentProofAfterError(new Error('network'))).toBe(false);
  });

  it("surfaces the server's recovery steps", () => {
    const refused = new ApiRequestError('refused', {
      status: 403, endpoint, detailPayload: { recovery: 'contact support with payment pay-1' },
    });
    expect(paymentRecoveryHint(refused)).toBe('contact support with payment pay-1');
    expect(paymentRecoveryHint(new Error('x'))).toBe('');
  });
});
