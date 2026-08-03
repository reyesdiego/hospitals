import type { ConsentType } from './consentType';

export interface AdmissionConsentCreate {
  consent_type: ConsentType;
  signed_by: string;
  signed_at?: string | null;
  notes?: string | null;
}
