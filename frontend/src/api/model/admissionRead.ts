import type { AdmissionOrigin } from './admissionOrigin';
import type { AdmissionStatus } from './admissionStatus';
import type { AdmissionType } from './admissionType';
import type { AuthorizationStatus } from './authorizationStatus';

export interface AdmissionRead {
  id: string;
  patient_id: string;
  episode_id: string | null;
  hospitalization_id: string | null;
  coverage_id: string | null;
  requesting_service_id: string | null;
  requested_bed_id: string | null;
  origin: AdmissionOrigin;
  admission_type: AdmissionType;
  status: AdmissionStatus;
  identity_validated: boolean;
  duplicate_checked: boolean;
  authorization_status: AuthorizationStatus;
  authorization_number: string | null;
  responsible_contact_name: string;
  responsible_contact_phone: string;
  responsible_contact_relationship: string | null;
  admission_reason: string;
  responsible_physician: string;
  presumptive_diagnosis: string | null;
  notes: string | null;
  admitted_at: string | null;
  administrative_discharged_at: string | null;
  created_at: string;
}
