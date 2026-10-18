// n8n Code node, "Run Once for All Items". Fixtures, not live inventory.
const input = $input.first().json.body;
function bad(message) {
  return [{json: {statusCode: 422, body: {error: 'invalid_input', message}}}];
}
if (!input || typeof input !== 'object' || Array.isArray(input) ||
    Object.keys(input).some(k => k !== 'items') || !Array.isArray(input.items) ||
    input.items.length < 1 || input.items.length > 20) {
  return bad('Provide items: an array of 1–20 {sku, quantity} objects.');
}
const quantities = new Map();
for (const item of input.items) {
  if (!item || typeof item !== 'object' || Array.isArray(item) ||
      Object.keys(item).some(k => !['sku', 'quantity'].includes(k)) ||
      typeof item.sku !== 'string' || !/^[A-Z0-9-]{1,40}$/.test(item.sku) ||
      !Number.isInteger(item.quantity) || item.quantity < 1 || item.quantity > 100) {
    return bad('Each item requires an uppercase SKU and an integer quantity from 1 to 100.');
  }
  const quantity = (quantities.get(item.sku) || 0) + item.quantity;
  if (quantity > 100) return bad('Combined quantity for one SKU must not exceed 100.');
  quantities.set(item.sku, quantity);
}
// Replace ONLY this data-source stage with the operator's authorised catalogue.
const catalog = {
  'BEANS-250': {name: 'Coffee beans, 250 g', unit_price_minor: 1290, available: 12},
  'MUG-BLUE': {name: 'Blue mug', unit_price_minor: 850, available: 3},
  'FILTER-100': {name: 'Paper filters, 100 pcs', unit_price_minor: 490, available: 0},
};
const lines = [...quantities].map(([sku, quantity]) => {
  const product = Object.hasOwn(catalog, sku) ? catalog[sku] : null;
  if (!product) return {sku, quantity, status: 'unknown_sku', line_total_minor: null};
  return {sku, quantity, ...product,
    status: quantity <= product.available ? 'available' : 'insufficient_stock',
    line_total_minor: quantity * product.unit_price_minor};
});
const unknown = lines.some(l => l.status === 'unknown_sku');
const ready = lines.every(l => l.status === 'available');
return [{json: {statusCode: 200, body: {
  kind: 'order_check', schema_version: 1, demo: true, data_source: 'workshop_fixture_v1',
  currency: 'USD', evaluated_at: new Date().toISOString(),
  status: unknown ? 'unknown_items' : ready ? 'ready' : 'insufficient_stock',
  can_fulfill: ready, lines,
  subtotal_minor: unknown ? null : lines.reduce((sum, l) => sum + l.line_total_minor, 0),
  tax_minor: null, shipping_minor: null, grand_total_minor: null,
  reservation_created: false, order_created: false,
  notice: 'Synthetic catalogue. Indicative goods subtotal only; tax and shipping are not calculated. No stock reserved and no order placed.'
}}}];
