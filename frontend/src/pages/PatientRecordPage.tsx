import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { getPatientRecord } from '@/api/endpoints/patient-record/patient-record';
import type { PatientPracticeRead } from '@/api/model';
import { Badge, Card, EmptyState, ErrorState, PageHeader, SectionTitle, Spinner } from '@/components/ui';
import { money } from '@/components/practices/labels';
import {
  CLINICAL_NOTE_KIND_COLORS,
  CLINICAL_NOTE_KIND_LABELS,
} from '@/config/workflowLabels';
import {
  DIAGNOSIS_ROLE_COLORS,
  DIAGNOSIS_ROLE_LABELS,
  DIAGNOSIS_STAGE_LABELS,
} from '@/config/diagnosisLabels';
import { HospitalizationStatusBadge } from '@/components/StatusBadges';
import {
  ADMISSION_TYPE_LABELS,
  MEDICATION_ROUTE_LABELS,
  PAYMENT_METHOD_LABELS,
  PRACTICE_ORDER_STATUS_COLORS,
  PRACTICE_ORDER_STATUS_LABELS,
  TREATMENT_KIND_LABELS,
  TREATMENT_STATUS_COLORS,
  TREATMENT_STATUS_LABELS,
} from '@/config/workflowLabels';
import { formatDate, formatDateTime } from '@/utils/format';
import {
  Activity,
  ArrowLeft,
  BedDouble,
  BookMarked,
  ClipboardList,
  NotebookPen,
  Pill,
  Stethoscope,
  Wallet,
} from 'lucide-react';

/** Un dato suelto de la ficha: etiqueta arriba, valor abajo. */
function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <Card className={`p-4 ${tone ?? ''}`}>
      <p className="text-xs text-slate-400">{label}</p>
      <p className="text-xl font-bold text-slate-800">{value}</p>
    </Card>
  );
}

export default function PatientRecordPage() {
  const { id = '' } = useParams();
  const api = getPatientRecord();

  const recordQuery = useQuery({
    queryKey: ['patient-record', id],
    queryFn: () => api.getPatientRecordApiV1PatientsPatientIdRecordGet(id),
    enabled: id !== '',
  });

  if (recordQuery.isLoading) return <Spinner />;
  if (recordQuery.isError || !recordQuery.data) {
    return <ErrorState message="No se pudo cargar la historia clinica del paciente." />;
  }

  const record = recordQuery.data;
  const { patient, totals } = record;
  const consultations = record.practices.filter((item) => item.is_consultation);
  const practices = record.practices.filter((item) => !item.is_consultation);
  const medication = record.prescriptions.filter((item) => item.kind === 'MEDICATION');
  const prescribedPractices = record.prescriptions.filter((item) => item.kind === 'PRACTICE');
  const stayLabel = (hospitalizationId: string) => {
    const stay = record.stays.find((item) => item.hospitalization_id === hospitalizationId);
    if (!stay) return null;
    return formatDate((stay.admitted_at ?? '').slice(0, 10)) ?? 'Internacion';
  };

  const practiceRow = (item: PatientPracticeRead) => (
    <div
      key={`${item.hospitalization_id}-${item.code}-${item.prescribed_at}`}
      className="flex flex-wrap items-center justify-between gap-3 px-4 py-2"
    >
      <div>
        <p className="text-sm font-medium text-slate-700">
          <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-bold">
            {item.code}
          </span>{' '}
          {item.name}
        </p>
        <p className="text-xs text-slate-400">
          {item.performed_at
            ? `Realizada ${formatDateTime(item.performed_at)}`
            : `Indicada ${formatDateTime(item.prescribed_at)}`}
          {item.indication ? ` · ${item.indication}` : ''}
        </p>
      </div>
      <div className="flex items-center gap-3">
        {item.amount && (
          <span className="text-sm font-semibold text-slate-700">{money(item.amount)}</span>
        )}
        <Badge
          status={PRACTICE_ORDER_STATUS_LABELS[item.status]}
          color={PRACTICE_ORDER_STATUS_COLORS[item.status]}
        />
      </div>
    </div>
  );

  return (
    <div>
      <PageHeader
        title={`${patient.last_name}, ${patient.first_name}`}
        subtitle={[
          `${patient.document_type} ${patient.document_number}`,
          record.age !== null && record.age !== undefined ? `${record.age} anos` : null,
          patient.birth_date ? `Nacimiento ${formatDate(patient.birth_date)}` : null,
        ]
          .filter(Boolean)
          .join(' · ')}
        action={
          <Link
            to="/patients"
            className="flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-50"
          >
            <ArrowLeft className="h-4 w-4" />
            Pacientes
          </Link>
        }
      />

      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Stat label="Internaciones" value={String(totals.stays)} />
        <Stat label="En curso" value={String(totals.open_stays)} />
        <Stat label="Practicas realizadas" value={String(totals.performed_practices)} />
        <Stat label="Consultas" value={String(totals.consultations)} />
        <Stat
          label="Saldo del paciente"
          value={money(totals.balance)}
          tone={Number(totals.balance) > 0 ? 'bg-amber-50' : ''}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card className="p-6">
          <SectionTitle icon={<BedDouble className="h-5 w-5 text-teal-600" />}>
            Internaciones
          </SectionTitle>
          {record.stays.length === 0 ? (
            <EmptyState message="El paciente no tuvo internaciones." />
          ) : (
            <div className="space-y-3">
              {record.stays.map((stay) => (
                <div key={stay.hospitalization_id} className="rounded-lg border border-slate-100 p-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-slate-800">
                        {stay.principal_diagnosis ?? stay.admission_reason}
                      </p>
                      <p className="text-xs text-slate-500">
                        {[
                          stay.admission_type
                            ? ADMISSION_TYPE_LABELS[stay.admission_type]
                            : null,
                          stay.facility_name,
                          stay.service_name,
                          stay.bed_label,
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                      </p>
                    </div>
                    <HospitalizationStatusBadge status={stay.status} />
                  </div>
                  <p className="mt-2 text-xs text-slate-400">
                    Ingreso {formatDateTime(stay.admitted_at) ?? 'sin registrar'}
                    {stay.clinically_discharged_at
                      ? ` · Egreso ${formatDateTime(stay.clinically_discharged_at)}`
                      : ''}
                    {stay.length_of_stay_days !== null &&
                    stay.length_of_stay_days !== undefined
                      ? ` · ${stay.length_of_stay_days} dias`
                      : ''}
                  </p>
                  <Link
                    to={`/hospitalizations/${stay.hospitalization_id}`}
                    className="mt-2 inline-block rounded-lg bg-teal-50 px-3 py-1.5 text-xs font-semibold text-teal-700 hover:bg-teal-100"
                  >
                    Ver internacion
                  </Link>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card className="p-6">
          <SectionTitle icon={<BookMarked className="h-5 w-5 text-teal-600" />}>
            Diagnosticos
          </SectionTitle>
          {record.diagnoses.length === 0 ? (
            <EmptyState message="Sin diagnosticos codificados." />
          ) : (
            <div className="divide-y divide-slate-100 rounded-lg border border-slate-100">
              {record.diagnoses.map((entry, index) => (
                <div
                  key={`${entry.hospitalization_id}-${entry.code}-${index}`}
                  className="flex flex-wrap items-center justify-between gap-3 px-4 py-2"
                >
                  <div>
                    <p className="text-sm font-medium text-slate-700">
                      <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-bold">
                        {entry.code}
                      </span>{' '}
                      {entry.description}
                    </p>
                    <p className="text-xs text-slate-500">
                      Indicado por{' '}
                      <span className="font-semibold text-slate-600">
                        {entry.diagnosed_by_name ?? 'profesional sin registrar'}
                      </span>
                    </p>
                    <p className="text-xs text-slate-400">
                      {DIAGNOSIS_STAGE_LABELS[entry.stage]} ·{' '}
                      {formatDateTime(entry.diagnosed_at)}
                      {stayLabel(entry.hospitalization_id)
                        ? ` · Internacion del ${stayLabel(entry.hospitalization_id)}`
                        : ''}
                    </p>
                  </div>
                  <Badge
                    status={DIAGNOSIS_ROLE_LABELS[entry.role]}
                    color={DIAGNOSIS_ROLE_COLORS[entry.role]}
                  />
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card className="p-6">
          <SectionTitle icon={<Stethoscope className="h-5 w-5 text-teal-600" />}>
            Consultas
          </SectionTitle>
          {consultations.length === 0 ? (
            <EmptyState message="Sin consultas registradas." />
          ) : (
            <div className="divide-y divide-slate-100 rounded-lg border border-slate-100">
              {consultations.map(practiceRow)}
            </div>
          )}
        </Card>

        <Card className="p-6">
          <SectionTitle icon={<Activity className="h-5 w-5 text-teal-600" />}>
            Practicas
          </SectionTitle>
          {practices.length === 0 ? (
            <EmptyState message="Sin practicas registradas." />
          ) : (
            <div className="divide-y divide-slate-100 rounded-lg border border-slate-100">
              {practices.map(practiceRow)}
            </div>
          )}
        </Card>

        <Card className="p-6">
          <SectionTitle icon={<Pill className="h-5 w-5 text-teal-600" />}>
            Medicacion e indicaciones del alta
          </SectionTitle>
          {record.prescriptions.length === 0 ? (
            <EmptyState message="Sin recetas ni indicaciones cargadas." />
          ) : (
            <div className="space-y-4">
              {[
                ['Medicacion', medication],
                ['Practicas indicadas', prescribedPractices],
              ].map(([title, items]) => {
                const list = items as typeof medication;
                if (list.length === 0) return null;
                return (
                  <div key={title as string}>
                    <p className="mb-2 text-sm font-semibold text-slate-700">{title as string}</p>
                    <div className="divide-y divide-slate-100 rounded-lg border border-slate-100">
                      {list.map((item, index) => (
                        <div key={`${item.description}-${index}`} className="px-4 py-2">
                          <p className="text-sm font-medium text-slate-700">
                            {item.description}
                            {item.presentation ? ` - ${item.presentation}` : ''}
                          </p>
                          <p className="text-xs text-slate-400">
                            {[
                              item.dosage,
                              item.duration_days ? `${item.duration_days} dias` : null,
                              formatDateTime(item.prescribed_at),
                            ]
                              .filter(Boolean)
                              .join(' · ')}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        <Card className="p-6">
          <SectionTitle icon={<Pill className="h-5 w-5 text-teal-600" />}>
            Medicacion y tratamientos
          </SectionTitle>
          {record.treatments.length === 0 ? (
            <EmptyState message="Sin medicacion ni tratamientos registrados." />
          ) : (
            <div className="divide-y divide-slate-100 rounded-lg border border-slate-100">
              {record.treatments.map((item, index) => (
                <div
                  key={`${item.description}-${index}`}
                  className="flex flex-wrap items-center justify-between gap-3 px-4 py-2"
                >
                  <div>
                    <p className="text-sm font-medium text-slate-700">
                      {item.description}
                      {item.presentation ? ` - ${item.presentation}` : ''}
                    </p>
                    <p className="text-xs text-slate-400">
                      {[
                        TREATMENT_KIND_LABELS[item.kind],
                        item.dose,
                        item.route ? MEDICATION_ROUTE_LABELS[item.route] : null,
                        item.frequency,
                        formatDateTime(item.started_at),
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </p>
                  </div>
                  <Badge
                    status={TREATMENT_STATUS_LABELS[item.status]}
                    color={TREATMENT_STATUS_COLORS[item.status]}
                  />
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card className="p-6">
          <SectionTitle icon={<NotebookPen className="h-5 w-5 text-teal-600" />}>
            Evolucion e interconsultas
          </SectionTitle>
          {record.notes.length === 0 ? (
            <EmptyState message="Sin notas en la historia." />
          ) : (
            <div className="space-y-3">
              {record.notes.slice(0, 15).map((item, index) => (
                <div key={`${item.noted_at}-${index}`} className="rounded-lg border border-slate-100 px-4 py-2">
                  <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                    <Badge
                      status={CLINICAL_NOTE_KIND_LABELS[item.kind]}
                      color={CLINICAL_NOTE_KIND_COLORS[item.kind]}
                    />
                    <span className="text-xs text-slate-400">
                      {formatDateTime(item.noted_at)}
                      {item.recorded_by_user_name ? ` · ${item.recorded_by_user_name}` : ''}
                    </span>
                  </div>
                  <p className="whitespace-pre-wrap text-sm text-slate-700">{item.note}</p>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card className="p-6">
          <SectionTitle icon={<Wallet className="h-5 w-5 text-teal-600" />}>Pagos</SectionTitle>
          <div className="mb-3 grid grid-cols-3 gap-3 text-sm">
            <div className="rounded-lg bg-slate-50 px-3 py-2">
              <p className="text-xs text-slate-400">A su cargo</p>
              <p className="font-semibold text-slate-700">{money(totals.patient_charged)}</p>
            </div>
            <div className="rounded-lg bg-slate-50 px-3 py-2">
              <p className="text-xs text-slate-400">Cobrado</p>
              <p className="font-semibold text-slate-700">{money(totals.paid)}</p>
            </div>
            <div
              className={`rounded-lg px-3 py-2 ${
                Number(totals.balance) > 0 ? 'bg-amber-50' : 'bg-emerald-50'
              }`}
            >
              <p className="text-xs text-slate-400">Saldo</p>
              <p className="font-semibold text-slate-700">{money(totals.balance)}</p>
            </div>
          </div>
          {record.payments.length === 0 ? (
            <EmptyState message="Sin pagos registrados." />
          ) : (
            <div className="divide-y divide-slate-100 rounded-lg border border-slate-100">
              {record.payments.map((payment, index) => (
                <div
                  key={`${payment.paid_at}-${index}`}
                  className="flex items-center justify-between px-4 py-2"
                >
                  <div>
                    <p
                      className={`text-sm font-semibold ${
                        payment.status === 'VOID'
                          ? 'text-slate-400 line-through'
                          : 'text-slate-700'
                      }`}
                    >
                      {money(payment.amount)} · {PAYMENT_METHOD_LABELS[payment.method]}
                    </p>
                    <p className="text-xs text-slate-400">
                      {formatDateTime(payment.paid_at)}
                      {payment.reference ? ` · Comprobante ${payment.reference}` : ''}
                      {payment.received_by ? ` · ${payment.received_by}` : ''}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card className="p-6 xl:col-span-2">
          <SectionTitle icon={<ClipboardList className="h-5 w-5 text-teal-600" />}>
            Coberturas
          </SectionTitle>
          {record.coverages.length === 0 ? (
            <EmptyState message="El paciente no tiene coberturas cargadas: es particular." />
          ) : (
            <div className="divide-y divide-slate-100 rounded-lg border border-slate-100">
              {record.coverages.map((coverage) => (
                <div key={coverage.id} className="flex items-center justify-between px-4 py-2">
                  <div>
                    <p className="text-sm font-medium text-slate-700">
                      {coverage.payer_name}
                      {coverage.plan_name ? ` · ${coverage.plan_name}` : ''}
                    </p>
                    <p className="text-xs text-slate-400">
                      {coverage.member_number
                        ? `Afiliado ${coverage.member_number}`
                        : 'Sin numero de afiliado'}
                      {coverage.valid_from ? ` · desde ${formatDate(coverage.valid_from)}` : ''}
                    </p>
                  </div>
                  <Badge
                    status={coverage.status}
                    color={
                      coverage.status === 'ACTIVE'
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-slate-100 text-slate-500'
                    }
                  />
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
