import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import { getReports } from '@/api/endpoints/reports/reports';
import type { DiagnosisRole, DiagnosisStage } from '@/api/model';
import {
  ActionButton,
  Card,
  EmptyState,
  ErrorState,
  Field,
  PageHeader,
  Spinner,
  inputClass,
} from '@/components/ui';
import { DIAGNOSIS_ROLE_LABELS, DIAGNOSIS_STAGE_LABELS } from '@/config/diagnosisLabels';
import { Download, TrendingUp } from 'lucide-react';

type Grouping = 'CODE' | 'CHAPTER';

const GROUPING_LABELS: Record<Grouping, string> = {
  CODE: 'Por diagnostico',
  CHAPTER: 'Por capitulo',
};

/** El periodo por defecto: el mes en curso, que es como se pide el informe. */
function monthStart(): string {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
}

export default function MorbidityReportPage() {
  const reports = getReports();
  const api = getDefault();
  const [fromDate, setFromDate] = useState(monthStart());
  const [toDate, setToDate] = useState(new Date().toISOString().slice(0, 10));
  const [serviceId, setServiceId] = useState('');
  const [stage, setStage] = useState<DiagnosisStage>('DISCHARGE');
  const [role, setRole] = useState<'' | DiagnosisRole>('PRINCIPAL');
  const [grouping, setGrouping] = useState<Grouping>('CODE');

  const servicesQuery = useQuery({
    queryKey: ['services'],
    queryFn: () => api.listServicesApiV1ServicesGet(),
  });

  const reportQuery = useQuery({
    queryKey: ['morbidity', fromDate, toDate, serviceId, stage, role, grouping],
    queryFn: () =>
      reports.getMorbidityReportApiV1ReportsMorbidityGet({
        from_date: fromDate || undefined,
        to_date: toDate || undefined,
        service_id: serviceId || undefined,
        stage,
        role: role || undefined,
        group_by: grouping,
      }),
  });

  const report = reportQuery.data;
  const rows = report?.rows ?? [];

  /** El informe se lleva a una planilla: es donde termina de armarse la estadistica. */
  const downloadCsv = () => {
    if (!report) return;
    const header = ['Codigo', 'Diagnostico', 'Egresos', 'Pacientes', 'Estadia promedio', 'Fallecidos', 'Mortalidad %'];
    const lines = rows.map((row) =>
      [
        row.key,
        `"${row.description.replace(/"/g, '""')}"`,
        row.episodes,
        row.patients,
        row.average_stay_days ?? '',
        row.deaths,
        row.mortality_rate,
      ].join(','),
    );
    const csv = [header.join(','), ...lines].join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `morbilidad-${fromDate}-${toDate}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <PageHeader
        title="Informe estadistico de morbilidad"
        subtitle="Egresos por diagnostico CIE-10, con pacientes, estadia promedio y fallecidos"
        action={
          <ActionButton tone="primary" onClick={downloadCsv} disabled={!report}>
            <Download className="h-4 w-4" />
            Descargar CSV
          </ActionButton>
        }
      />

      <Card className="mb-4 p-4">
        <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-6">
          <Field label="Desde (egreso)">
            <input
              type="date"
              value={fromDate}
              onChange={(event) => setFromDate(event.target.value)}
              className={inputClass}
            />
          </Field>
          <Field label="Hasta (egreso)">
            <input
              type="date"
              value={toDate}
              onChange={(event) => setToDate(event.target.value)}
              className={inputClass}
            />
          </Field>
          <Field label="Servicio">
            <select
              value={serviceId}
              onChange={(event) => setServiceId(event.target.value)}
              className={inputClass}
            >
              <option value="">Todos</option>
              {(servicesQuery.data ?? []).map((service) => (
                <option key={service.id} value={service.id}>
                  {service.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Momento">
            <select
              value={stage}
              onChange={(event) => setStage(event.target.value as DiagnosisStage)}
              className={inputClass}
            >
              {Object.entries(DIAGNOSIS_STAGE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Rol">
            <select
              value={role}
              onChange={(event) => setRole(event.target.value as '' | DiagnosisRole)}
              className={inputClass}
            >
              <option value="">Todos</option>
              {Object.entries(DIAGNOSIS_ROLE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Agrupar">
            <select
              value={grouping}
              onChange={(event) => setGrouping(event.target.value as Grouping)}
              className={inputClass}
            >
              {Object.entries(GROUPING_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
        </div>
        {role === '' && (
          <p className="mt-3 text-xs text-slate-500">
            Sin filtrar por rol, una internacion con varios diagnosticos suma en cada fila:
            el total deja de ser la cantidad de egresos.
          </p>
        )}
      </Card>

      {reportQuery.isLoading && <Spinner />}
      {reportQuery.isError && <ErrorState message="No se pudo generar el informe." />}

      {report && (
        <>
          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            <Card className="p-4">
              <p className="text-xs text-slate-400">Egresos contados</p>
              <p className="text-2xl font-bold text-slate-800">{report.total_episodes}</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-slate-400">Diagnosticos distintos</p>
              <p className="text-2xl font-bold text-slate-800">{rows.length}</p>
            </Card>
            <Card className={`p-4 ${report.uncoded_episodes > 0 ? 'bg-amber-50' : ''}`}>
              <p className="text-xs text-slate-400">Egresos sin codificar</p>
              <p
                className={`text-2xl font-bold ${
                  report.uncoded_episodes > 0 ? 'text-amber-700' : 'text-slate-800'
                }`}
              >
                {report.uncoded_episodes}
              </p>
            </Card>
          </div>

          <Card className="overflow-hidden">
            {rows.length === 0 ? (
              <EmptyState message="No hubo egresos codificados en el periodo." />
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-100 text-sm">
                  <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                    <tr>
                      <th className="px-5 py-3 text-left font-semibold">
                        {grouping === 'CHAPTER' ? 'Capitulo' : 'Codigo'}
                      </th>
                      <th className="px-5 py-3 text-left font-semibold">Diagnostico</th>
                      <th className="px-5 py-3 text-right font-semibold">Egresos</th>
                      <th className="px-5 py-3 text-right font-semibold">Pacientes</th>
                      <th className="px-5 py-3 text-right font-semibold">Estadia prom.</th>
                      <th className="px-5 py-3 text-right font-semibold">Fallecidos</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white">
                    {rows.map((row) => (
                      <tr key={row.key} className="hover:bg-slate-50">
                        <td className="px-5 py-3">
                          <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-bold text-slate-700">
                            {row.key}
                          </span>
                        </td>
                        <td className="px-5 py-3 text-slate-700">{row.description}</td>
                        <td className="px-5 py-3 text-right font-semibold text-slate-800">
                          {row.episodes}
                        </td>
                        <td className="px-5 py-3 text-right text-slate-600">{row.patients}</td>
                        <td className="px-5 py-3 text-right text-slate-600">
                          {row.average_stay_days !== null && row.average_stay_days !== undefined
                            ? `${row.average_stay_days} dias`
                            : '-'}
                        </td>
                        <td className="px-5 py-3 text-right text-slate-600">
                          {row.deaths > 0 ? `${row.deaths} (${row.mortality_rate}%)` : '0'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <p className="mt-3 flex items-center gap-2 text-xs text-slate-400">
            <TrendingUp className="h-4 w-4" />
            Se cuentan los egresos del periodo. Una internacion en curso no tiene diagnostico
            definitivo y no entra en el informe.
          </p>
        </>
      )}
    </div>
  );
}
