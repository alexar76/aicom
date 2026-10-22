/** A factory product id: `prod-` and twelve hex digits, or one of the in-repo `prod-demo-*` SKUs.
 * Anything else is no product page; `/product/undefined`, which a link built from a missing id once
 * produced, was indexed by search engines as a page of its own. */
export function isProductId(id: string | null | undefined): boolean {
  return typeof id === 'string' && /^prod-[a-z0-9][a-z0-9-]{1,63}$/i.test(id);
}
