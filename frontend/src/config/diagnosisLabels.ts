import type { DiagnosisRole, DiagnosisStage } from '@/api/model';

export const DIAGNOSIS_ROLE_LABELS: Record<DiagnosisRole, string> = {
  PRINCIPAL: 'Principal',
  SECONDARY: 'Secundario',
  COMORBIDITY: 'Comorbilidad',
  COMPLICATION: 'Complicacion',
};

export const DIAGNOSIS_ROLE_COLORS: Record<DiagnosisRole, string> = {
  PRINCIPAL: 'bg-teal-50 text-teal-700',
  SECONDARY: 'bg-slate-100 text-slate-600',
  COMORBIDITY: 'bg-amber-50 text-amber-700',
  COMPLICATION: 'bg-red-50 text-red-600',
};

export const DIAGNOSIS_STAGE_LABELS: Record<DiagnosisStage, string> = {
  ADMISSION: 'De ingreso',
  DISCHARGE: 'De egreso',
};
