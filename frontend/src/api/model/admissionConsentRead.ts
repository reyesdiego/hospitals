import type { ConsentType } from './consentType';

export interface AdmissionConsentRead {
  id: string;
  admission_id: string;
  consent_type: ConsentType;
  signed_by: string;
  signed_at: string | null;
  notes: string | null;
  created_at: string;
}
