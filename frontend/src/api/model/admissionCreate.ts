import type { AdmissionConsentCreate } from './admissionConsentCreate';
import type { AdmissionOrigin } from './admissionOrigin';
import type { AdmissionType } from './admissionType';
import type { AuthorizationStatus } from './authorizationStatus';
import type { PatientCoverageCreate } from './patientCoverageCreate';

export interface AdmissionCreate {
  patient_id: string;
  origin: AdmissionOrigin;
  admission_type: AdmissionType;
  identity_validated?: boolean;
  duplicate_checked?: boolean;
  coverage_id?: string | null;
  coverage?: PatientCoverageCreate | null;
  authorization_status?: AuthorizationStatus;
  authorization_number?: string | null;
  responsible_contact_name: string;
  responsible_contact_phone: string;
  responsible_contact_relationship?: string | null;
  admission_reason: string;
  responsible_physician: string;
  requesting_service_id?: string | null;
  presumptive_diagnosis?: string | null;
  requested_bed_id?: string | null;
  consents?: AdmissionConsentCreate[];
  notes?: string | null;
  confirm_admission?: boolean;
}
