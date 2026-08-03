import type { AdmissionConsentRead } from './admissionConsentRead';
import type { AdmissionRead } from './admissionRead';
import type { EpisodeRead } from './episodeRead';
import type { PatientCoverageRead } from './patientCoverageRead';
import type { PatientRead } from './patientRead';

export interface AdmissionDashboardRead extends AdmissionRead {
  patient: PatientRead;
  episode: EpisodeRead | null;
  coverage: PatientCoverageRead | null;
  consents: AdmissionConsentRead[];
}
