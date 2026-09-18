import type { HospitalizationRead } from '@/api/model';
import { HospitalizationStatusBadge } from '@/components/StatusBadges';
import { Card, SectionTitle } from '@/components/ui';
import { formatDateTime } from '@/utils/format';
import { Activity, Check, Circle } from 'lucide-react';

type Step = {
  label: string;
  at: string | null | undefined;
  pending: string;
};

/**
 * The lifecycle moments are different events and never share a timestamp: the clinical
 * discharge does not free the bed, and the financial closure is the last step.
 */
export function LifecycleCard({ hosp }: { hosp: HospitalizationRead }) {
  const steps: Step[] = [
    {
      label: 'Ingreso (ocupacion de cama)',
      at: hosp.admitted_at,
      pending: 'Pendiente de asignacion de cama',
    },
    {
      label: 'Alta clinica',
      at: hosp.clinically_discharged_at,
      pending: 'El paciente sigue en tratamiento',
    },
    {
      label: 'Salida fisica',
      at: hosp.physically_departed_at,
      pending: 'El paciente aun ocupa la cama',
    },
    {
      label: 'Alta administrativa',
      at: hosp.administratively_discharged_at,
      pending: 'Documentacion pendiente',
    },
    {
      label: 'Cierre de cuenta',
      at: hosp.closed_at,
      pending: 'Facturacion en curso',
    },
  ];

  return (
    <Card className="p-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <SectionTitle icon={<Activity className="h-5 w-5 text-teal-600" />}>
          Ciclo de la internacion
        </SectionTitle>
        <HospitalizationStatusBadge status={hosp.status} />
      </div>

      <ol className="space-y-1">
        {steps.map((step) => {
          const done = Boolean(step.at);
          return (
            <li key={step.label} className="flex items-start gap-3 rounded-lg px-2 py-2">
              <span
                className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${
                  done ? 'bg-teal-50 text-teal-600' : 'bg-slate-100 text-slate-300'
                }`}
              >
                {done ? <Check className="h-3.5 w-3.5" /> : <Circle className="h-3 w-3" />}
              </span>
              <div className="min-w-0">
                <p
                  className={`text-sm font-semibold ${done ? 'text-slate-700' : 'text-slate-400'}`}
                >
                  {step.label}
                </p>
                <p className="text-xs text-slate-400">
                  {done ? formatDateTime(step.at) : step.pending}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

export default LifecycleCard;
