import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import type { AdmissionCreate, PatientCreate } from '@/api/model';
import { Badge, Card, EmptyState, ErrorState, PageHeader, Spinner } from '@/components/ui';
import { ADMISSION_STATUS_COLORS, ADMISSION_STATUS_LABELS } from '@/config/workflowLabels';
import {
  BedDouble,
  CheckCircle2,
  ClipboardCheck,
  FileSignature,
  Search,
  ShieldCheck,
  UserPlus,
} from 'lucide-react';

const ORIGIN_LABELS = {
  EMERGENCY_ROOM: 'Guardia',
  OUTPATIENT_CLINIC: 'Consultorio',
  SCHEDULED_SURGERY: 'Cirugia programada',
  EXTERNAL_REFERRAL: 'Derivacion externa',
  HOME_HOSPITALIZATION: 'Internacion domiciliaria',
  SPECIAL_CARE_UNIT: 'Unidad cuidados especiales',
  SCHEDULED_MEDICAL_ORDER: 'Orden medica programada',
} as const;

const initialPatient: PatientCreate = {
  first_name: '',
  last_name: '',
  document_type: 'DNI',
  document_number: '',
  birth_date: null,
};

const initialAdmission: AdmissionCreate = {
  patient_id: '',
  origin: 'EMERGENCY_ROOM',
  admission_type: 'EMERGENCY',
  identity_validated: false,
  duplicate_checked: false,
  coverage: {
    payer_name: '',
    plan_name: '',
    member_number: '',
    authorization_required: false,
  },
  authorization_status: 'NOT_REQUIRED',
  authorization_number: '',
  responsible_contact_name: '',
  responsible_contact_phone: '',
  responsible_contact_relationship: '',
  admission_reason: '',
  responsible_physician: '',
  requesting_service_id: null,
  presumptive_diagnosis: '',
  requested_bed_id: null,
  consents: [],
  notes: '',
  confirm_admission: true,
};

export default function AdmissionPanelPage() {
  const api = getDefault();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [patientForm, setPatientForm] = useState<PatientCreate>(initialPatient);
  const [admissionForm, setAdmissionForm] = useState<AdmissionCreate>(initialAdmission);
  const [signedConsents, setSignedConsents] = useState({
    GENERAL_ADMISSION: false,
    DATA_PROCESSING: false,
    PROCEDURE: false,
  });

  const patientsQuery = useQuery({
    queryKey: ['patients'],
    queryFn: () => api.listPatientsApiV1PatientsGet(),
  });
  const servicesQuery = useQuery({
    queryKey: ['services'],
    queryFn: () => api.listServicesApiV1ServicesGet(),
  });
  const bedsQuery = useQuery({
    queryKey: ['beds'],
    queryFn: () => api.listBedsApiV1BedsGet(),
  });
  const admissionsQuery = useQuery({
    queryKey: ['admissions'],
    queryFn: () => api.listAdmissionsApiV1AdmissionsGet(),
  });

  const createPatientMutation = useMutation({
    mutationFn: (data: PatientCreate) => api.createPatientApiV1PatientsPost(data),
    onSuccess: (patient) => {
      queryClient.invalidateQueries({ queryKey: ['patients'] });
      setAdmissionForm((current) => ({ ...current, patient_id: patient.id }));
      setPatientForm(initialPatient);
    },
  });

  const createAdmissionMutation = useMutation({
    mutationFn: (data: AdmissionCreate) => api.createAdmissionApiV1AdmissionsPost(data),
    onSuccess: (admission) => {
      queryClient.invalidateQueries({ queryKey: ['admissions'] });
      queryClient.invalidateQueries({ queryKey: ['hospitalizations'] });
      queryClient.invalidateQueries({ queryKey: ['beds'] });
      setAdmissionForm(initialAdmission);
      setSignedConsents({ GENERAL_ADMISSION: false, DATA_PROCESSING: false, PROCEDURE: false });
      // The request creates the hospitalization: continue the flow on it.
      if (admission.hospitalization_id) {
        navigate(`/hospitalizations/${admission.hospitalization_id}`);
      }
    },
  });

  const dischargeMutation = useMutation({
    mutationFn: (admissionId: string) =>
      api.administrativeDischargeApiV1AdmissionsAdmissionIdAdministrativeDischargePost(
        admissionId,
        {},
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admissions'] });
      queryClient.invalidateQueries({ queryKey: ['hospitalizations'] });
    },
  });

  const patients = patientsQuery.data ?? [];
  const beds = bedsQuery.data ?? [];
  const services = servicesQuery.data ?? [];
  const admissions = admissionsQuery.data ?? [];
  const availableBeds = beds.filter((bed) => bed.status === 'AVAILABLE');

  const filteredPatients = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return patients.slice(0, 6);
    return patients.filter((patient) =>
      `${patient.first_name} ${patient.last_name} ${patient.document_type} ${patient.document_number}`
        .toLowerCase()
        .includes(q),
    );
  }, [patients, search]);

  const selectedPatient = patients.find((patient) => patient.id === admissionForm.patient_id);
  const duplicateMatches = patients.filter(
    (patient) =>
      patient.document_type === patientForm.document_type &&
      patient.document_number &&
      patient.document_number === patientForm.document_number,
  );

  const steps = [
    { label: 'Paciente', done: Boolean(admissionForm.patient_id) },
    { label: 'Identidad', done: Boolean(admissionForm.identity_validated) },
    { label: 'Duplicados', done: Boolean(admissionForm.duplicate_checked) },
    { label: 'Cobertura', done: Boolean(admissionForm.authorization_status) },
    { label: 'Consentimientos', done: signedConsents.GENERAL_ADMISSION },
    { label: 'Ingreso', done: Boolean(admissionForm.admission_reason && admissionForm.responsible_physician) },
  ];

  const createPatient = (event: React.FormEvent) => {
    event.preventDefault();
    createPatientMutation.mutate(patientForm);
  };

  const createAdmission = (event: React.FormEvent) => {
    event.preventDefault();
    const consents = Object.entries(signedConsents)
      .filter(([, signed]) => signed)
      .map(([consent_type]) => ({
        consent_type: consent_type as 'GENERAL_ADMISSION' | 'DATA_PROCESSING' | 'PROCEDURE',
        signed_by:
          admissionForm.responsible_contact_name ||
          `${selectedPatient?.first_name ?? ''} ${selectedPatient?.last_name ?? ''}`.trim(),
      }));
    const coverage = admissionForm.coverage?.payer_name
      ? admissionForm.coverage
      : null;
    createAdmissionMutation.mutate({
      ...admissionForm,
      coverage,
      requested_bed_id: admissionForm.requested_bed_id || null,
      requesting_service_id: admissionForm.requesting_service_id || null,
      consents,
    });
  };

  const loading =
    patientsQuery.isLoading || servicesQuery.isLoading || bedsQuery.isLoading || admissionsQuery.isLoading;
  const error =
    patientsQuery.isError || servicesQuery.isError || bedsQuery.isError || admissionsQuery.isError;

  return (
    <div>
      <PageHeader
        title="Panel de admision"
        subtitle="Pre-admision, ingreso programado o de urgencia, episodio e internacion"
      />

      {loading && <Spinner />}
      {error && <ErrorState message="No se pudieron cargar los datos de admision." />}

      {!loading && !error && (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
          <form onSubmit={createAdmission} className="space-y-6">
            <Card className="p-5">
              <div className="mb-4 flex items-center gap-2">
                <UserPlus className="h-5 w-5 text-teal-600" />
                <h2 className="text-base font-bold text-slate-800">Paciente</h2>
              </div>
              <div className="grid gap-5 lg:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-600">
                    Buscar paciente
                  </label>
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <input
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Nombre o documento"
                      className="w-full rounded-lg border border-slate-200 py-2.5 pl-10 pr-3 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/20"
                    />
                  </div>
                  <div className="mt-3 max-h-64 overflow-y-auto rounded-lg border border-slate-100">
                    {filteredPatients.map((patient) => (
                      <button
                        key={patient.id}
                        type="button"
                        onClick={() =>
                          setAdmissionForm((current) => ({
                            ...current,
                            patient_id: patient.id,
                            identity_validated: true,
                            duplicate_checked: true,
                          }))
                        }
                        className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm transition-colors hover:bg-slate-50 ${
                          admissionForm.patient_id === patient.id ? 'bg-teal-50 text-teal-800' : 'text-slate-600'
                        }`}
                      >
                        <span className="font-medium">
                          {patient.first_name} {patient.last_name}
                        </span>
                        <span className="text-xs text-slate-400">
                          {patient.document_type} {patient.document_number}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-600">
                    Registrar paciente
                  </label>
                  <div className="grid grid-cols-2 gap-3">
                    <input
                      required={!admissionForm.patient_id}
                      placeholder="Nombre"
                      value={patientForm.first_name}
                      onChange={(e) => setPatientForm({ ...patientForm, first_name: e.target.value })}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                    />
                    <input
                      required={!admissionForm.patient_id}
                      placeholder="Apellido"
                      value={patientForm.last_name}
                      onChange={(e) => setPatientForm({ ...patientForm, last_name: e.target.value })}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                    />
                    <select
                      value={patientForm.document_type}
                      onChange={(e) => setPatientForm({ ...patientForm, document_type: e.target.value })}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                    >
                      <option value="DNI">DNI</option>
                      <option value="PASSPORT">Pasaporte</option>
                      <option value="NIE">NIE</option>
                    </select>
                    <input
                      required={!admissionForm.patient_id}
                      placeholder="Documento"
                      value={patientForm.document_number}
                      onChange={(e) => setPatientForm({ ...patientForm, document_number: e.target.value })}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                    />
                  </div>
                  {duplicateMatches.length > 0 && (
                    <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700">
                      Posible duplicado: {duplicateMatches[0].first_name} {duplicateMatches[0].last_name}
                    </p>
                  )}
                  <button
                    type="button"
                    onClick={createPatient}
                    disabled={createPatientMutation.isPending}
                    className="mt-3 inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
                  >
                    <UserPlus className="h-4 w-4" />
                    Registrar y seleccionar
                  </button>
                </div>
              </div>
            </Card>

            <Card className="p-5">
              <div className="mb-4 flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-teal-600" />
                <h2 className="text-base font-bold text-slate-800">Cobertura y autorizacion</h2>
              </div>
              <div className="grid gap-4 md:grid-cols-4">
                <input
                  placeholder="Cobertura"
                  value={admissionForm.coverage?.payer_name ?? ''}
                  onChange={(e) =>
                    setAdmissionForm({
                      ...admissionForm,
                      coverage: { ...admissionForm.coverage!, payer_name: e.target.value },
                    })
                  }
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                />
                <input
                  placeholder="Plan"
                  value={admissionForm.coverage?.plan_name ?? ''}
                  onChange={(e) =>
                    setAdmissionForm({
                      ...admissionForm,
                      coverage: { ...admissionForm.coverage!, plan_name: e.target.value },
                    })
                  }
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                />
                <input
                  placeholder="Afiliado"
                  value={admissionForm.coverage?.member_number ?? ''}
                  onChange={(e) =>
                    setAdmissionForm({
                      ...admissionForm,
                      coverage: { ...admissionForm.coverage!, member_number: e.target.value },
                    })
                  }
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                />
                <select
                  value={admissionForm.authorization_status}
                  onChange={(e) =>
                    setAdmissionForm({
                      ...admissionForm,
                      authorization_status: e.target.value as AdmissionCreate['authorization_status'],
                    })
                  }
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                >
                  <option value="NOT_REQUIRED">No requiere</option>
                  <option value="PENDING">Pendiente</option>
                  <option value="AUTHORIZED">Autorizada</option>
                  <option value="REJECTED">Rechazada</option>
                </select>
              </div>
              <input
                placeholder="Numero de autorizacion"
                value={admissionForm.authorization_number ?? ''}
                onChange={(e) =>
                  setAdmissionForm({ ...admissionForm, authorization_number: e.target.value })
                }
                className="mt-4 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
              />
            </Card>

            <Card className="p-5">
              <div className="mb-4 flex items-center gap-2">
                <ClipboardCheck className="h-5 w-5 text-teal-600" />
                <h2 className="text-base font-bold text-slate-800">Ingreso e internacion</h2>
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                <select
                  value={admissionForm.origin}
                  onChange={(e) =>
                    setAdmissionForm({ ...admissionForm, origin: e.target.value as AdmissionCreate['origin'] })
                  }
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                >
                  {Object.entries(ORIGIN_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <select
                  value={admissionForm.admission_type}
                  onChange={(e) =>
                    setAdmissionForm({
                      ...admissionForm,
                      admission_type: e.target.value as AdmissionCreate['admission_type'],
                    })
                  }
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                >
                  <option value="PRE_ADMISSION">Pre-admision</option>
                  <option value="SCHEDULED">Programada</option>
                  <option value="EMERGENCY">Urgencia</option>
                </select>
                <select
                  value={admissionForm.requesting_service_id ?? ''}
                  onChange={(e) =>
                    setAdmissionForm({ ...admissionForm, requesting_service_id: e.target.value || null })
                  }
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                >
                  <option value="">Servicio solicitante</option>
                  {services.map((service) => (
                    <option key={service.id} value={service.id}>
                      {service.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <input
                  required
                  placeholder="Medico responsable"
                  value={admissionForm.responsible_physician}
                  onChange={(e) =>
                    setAdmissionForm({ ...admissionForm, responsible_physician: e.target.value })
                  }
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                />
                <input
                  placeholder="Diagnostico presuntivo"
                  value={admissionForm.presumptive_diagnosis ?? ''}
                  onChange={(e) =>
                    setAdmissionForm({ ...admissionForm, presumptive_diagnosis: e.target.value })
                  }
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                />
              </div>
              <textarea
                required
                minLength={3}
                maxLength={500}
                rows={3}
                placeholder="Motivo de ingreso"
                value={admissionForm.admission_reason}
                onChange={(e) =>
                  setAdmissionForm({ ...admissionForm, admission_reason: e.target.value })
                }
                className="mt-4 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
              />
            </Card>

            <Card className="p-5">
              <div className="mb-4 flex items-center gap-2">
                <FileSignature className="h-5 w-5 text-teal-600" />
                <h2 className="text-base font-bold text-slate-800">Contacto y consentimientos</h2>
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                <input
                  required
                  placeholder="Contacto responsable"
                  value={admissionForm.responsible_contact_name}
                  onChange={(e) =>
                    setAdmissionForm({ ...admissionForm, responsible_contact_name: e.target.value })
                  }
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                />
                <input
                  required
                  placeholder="Telefono"
                  value={admissionForm.responsible_contact_phone}
                  onChange={(e) =>
                    setAdmissionForm({ ...admissionForm, responsible_contact_phone: e.target.value })
                  }
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                />
                <input
                  placeholder="Vinculo"
                  value={admissionForm.responsible_contact_relationship ?? ''}
                  onChange={(e) =>
                    setAdmissionForm({
                      ...admissionForm,
                      responsible_contact_relationship: e.target.value,
                    })
                  }
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                />
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-3">
                {[
                  ['GENERAL_ADMISSION', 'Ingreso general'],
                  ['DATA_PROCESSING', 'Datos personales'],
                  ['PROCEDURE', 'Procedimiento'],
                ].map(([key, label]) => (
                  <label
                    key={key}
                    className="flex items-center gap-3 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600"
                  >
                    <input
                      type="checkbox"
                      checked={signedConsents[key as keyof typeof signedConsents]}
                      onChange={(e) =>
                        setSignedConsents({ ...signedConsents, [key]: e.target.checked })
                      }
                      className="h-4 w-4 accent-teal-600"
                    />
                    {label}
                  </label>
                ))}
              </div>
            </Card>

            <Card className="p-5">
              <div className="mb-4 flex items-center gap-2">
                <BedDouble className="h-5 w-5 text-teal-600" />
                <h2 className="text-base font-bold text-slate-800">Solicitud de cama</h2>
              </div>
              <select
                value={admissionForm.requested_bed_id ?? ''}
                onChange={(e) =>
                  setAdmissionForm({ ...admissionForm, requested_bed_id: e.target.value || null })
                }
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
              >
                <option value="">Confirmar ingreso sin cama asignada</option>
                {availableBeds.map((bed) => (
                  <option key={bed.id} value={bed.id}>
                    {bed.code} - {bed.ward} Hab. {bed.room}
                  </option>
                ))}
              </select>

              <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-wrap gap-2">
                  {steps.map((step) => (
                    <Badge
                      key={step.label}
                      status={step.label}
                      color={step.done ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'}
                    />
                  ))}
                </div>
                <button
                  type="submit"
                  disabled={createAdmissionMutation.isPending || !admissionForm.patient_id}
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md disabled:opacity-50"
                >
                  <CheckCircle2 className="h-4 w-4" />
                  {createAdmissionMutation.isPending ? 'Confirmando...' : 'Confirmar ingreso'}
                </button>
              </div>
              {createAdmissionMutation.isError && (
                <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
                  No se pudo confirmar la admision. Revisa identidad, duplicados y autorizacion.
                </p>
              )}
            </Card>
          </form>

          <aside className="space-y-4">
            <Card className="p-5">
              <h2 className="text-base font-bold text-slate-800">Admisiones recientes</h2>
              <div className="mt-4 space-y-3">
                {admissions.length === 0 && <EmptyState message="No hay admisiones registradas." />}
                {admissions.slice(0, 8).map((admission) => (
                  <div key={admission.id} className="rounded-lg border border-slate-100 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-bold text-slate-800">
                          {admission.patient.first_name} {admission.patient.last_name}
                        </p>
                        <p className="text-xs text-slate-500">
                          {ORIGIN_LABELS[admission.origin]} · {admission.responsible_physician}
                        </p>
                      </div>
                      <Badge
                        status={ADMISSION_STATUS_LABELS[admission.status]}
                        color={ADMISSION_STATUS_COLORS[admission.status]}
                      />
                    </div>
                    <p className="mt-2 line-clamp-2 text-xs text-slate-500">
                      {admission.admission_reason}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {admission.hospitalization_id && (
                        <button
                          type="button"
                          onClick={() =>
                            navigate(`/hospitalizations/${admission.hospitalization_id}`)
                          }
                          className="rounded-lg bg-teal-50 px-3 py-1.5 text-xs font-semibold text-teal-700 hover:bg-teal-100"
                        >
                          Ver internacion
                        </button>
                      )}
                      {admission.status !== 'ADMINISTRATIVE_DISCHARGE' && (
                        <button
                          type="button"
                          onClick={() => dischargeMutation.mutate(admission.id)}
                          disabled={dischargeMutation.isPending}
                          className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                        >
                          Alta administrativa
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </aside>
        </div>
      )}
    </div>
  );
}
