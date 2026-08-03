export interface PatientCoverageCreate {
  patient_id?: string | null;
  payer_name: string;
  plan_name?: string | null;
  member_number?: string | null;
  authorization_required?: boolean;
}
