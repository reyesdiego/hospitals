import type { Nomenclador, PracticeChapter, PracticeSetting, PracticeType } from '@/api/model';

export const NOMENCLADOR_LABELS: Record<Nomenclador, string> = {
  NACIONAL: 'Nomenclador Nacional',
  NBU: 'Nomenclador Bioquimico Unico',
  NU_SSS: 'Nomenclador Unico SSS',
  HPGD: 'HPGD',
  PROPIO: 'Nomenclador propio',
};

export const NOMENCLADOR_SHORT: Record<Nomenclador, string> = {
  NACIONAL: 'Nacional',
  NBU: 'NBU',
  NU_SSS: 'NU SSS',
  HPGD: 'HPGD',
  PROPIO: 'Propio',
};

export const CHAPTER_LABELS: Record<PracticeChapter, string> = {
  CONSULTAS: 'Consultas',
  INTERNACION: 'Internacion',
  PRACTICAS_ESPECIALIZADAS: 'Practicas especializadas',
  CIRUGIA: 'Cirugia',
  OBSTETRICIA: 'Obstetricia',
  ANESTESIA: 'Anestesia',
  LABORATORIO: 'Laboratorio',
  DIAGNOSTICO_POR_IMAGENES: 'Diagnostico por imagenes',
  ANATOMIA_PATOLOGICA: 'Anatomia patologica',
  HEMOTERAPIA: 'Hemoterapia',
  KINESIOLOGIA: 'Kinesiologia',
  FONOAUDIOLOGIA: 'Fonoaudiologia',
  SALUD_MENTAL: 'Salud mental',
  ODONTOLOGIA: 'Odontologia',
  TRASLADOS: 'Traslados',
  OTROS: 'Otros',
};

export const PRACTICE_TYPE_LABELS: Record<PracticeType, string> = {
  CONSULTA: 'Consulta',
  PRACTICA: 'Practica',
  CIRUGIA: 'Cirugia',
  LABORATORIO: 'Laboratorio',
  IMAGENES: 'Imagenes',
  ANESTESIA: 'Anestesia',
  INTERNACION: 'Internacion',
  MODULO: 'Modulo',
  TRASLADO: 'Traslado',
  OTRO: 'Otro',
};

export const SETTING_LABELS: Record<PracticeSetting, string> = {
  AMBULATORIO: 'Ambulatorio',
  INTERNACION: 'Internacion',
  AMBOS: 'Ambulatorio e internacion',
};

/** Unidades que publica el nomenclador para cada practica. */
export const UNIT_LABELS = {
  galeno_units: 'Galeno (honorarios)',
  expense_units: 'Gastos',
  anesthesia_units: 'Anestesia',
  biochemical_units: 'Bioquimicas (UB)',
  radiology_units: 'Radiologicas (UR)',
} as const;

export type UnitField = keyof typeof UNIT_LABELS;

export const UNIT_FIELDS = Object.keys(UNIT_LABELS) as UnitField[];

const CURRENCY = new Intl.NumberFormat('es-AR', {
  style: 'currency',
  currency: 'ARS',
  maximumFractionDigits: 2,
});

export function money(amount: string | null | undefined, currency = 'ARS'): string {
  if (amount === null || amount === undefined) return '-';
  const value = Number(amount);
  if (Number.isNaN(value)) return amount;
  return currency === 'ARS' ? CURRENCY.format(value) : `${currency} ${value.toFixed(2)}`;
}

/** Las unidades llegan como "40.00": se muestran sin ceros al final. */
export function units(value: string): string {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) return value;
  return String(parsed);
}

export function period(from: string | null, until: string | null): string {
  const format = (value: string) => new Date(`${value}T00:00:00`).toLocaleDateString('es-AR');
  if (!from && !until) return 'Sin vigencia definida';
  if (from && !until) return `Desde ${format(from)}`;
  if (!from && until) return `Hasta ${format(until!)}`;
  return `${format(from!)} - ${format(until!)}`;
}
