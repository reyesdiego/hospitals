export interface PatientCoverageRead {
  id: string;
  patient_id: string;
  payer_name: string;
  plan_name: string | null;
  member_number: string | null;
  authorization_required: boolean;
  created_at: string;
}
