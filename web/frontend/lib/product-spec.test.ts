import { describe, expect, it } from 'vitest';
import {
  formatDataModelFields,
  formatDataModelRelationships,
} from './product-spec';

describe('formatDataModelFields', () => {
  it('joins string field names', () => {
    expect(formatDataModelFields(['id (UUID, PK)', 'email'])).toBe('id (UUID, PK), email');
  });

  it('formats object field entries', () => {
    expect(
      formatDataModelFields([
        { name: 'id', type: 'UUID', description: 'Primary key' },
        { name: 'patient_id', type: 'UUID', fk: 'Patient.id' },
      ]),
    ).toBe('id: UUID (Primary key), patient_id: UUID → Patient.id');
  });
});

describe('formatDataModelRelationships', () => {
  it('joins string relationships', () => {
    expect(formatDataModelRelationships(['belongs to User'])).toBe('belongs to User');
  });

  it('formats object relationship entries', () => {
    expect(
      formatDataModelRelationships([
        { name: 'appointments', type: 'one-to-many', to: 'Appointment' },
      ]),
    ).toBe('appointments (one-to-many) → Appointment');
  });
});
