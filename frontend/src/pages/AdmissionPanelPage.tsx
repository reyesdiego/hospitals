import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getDefault } from '@/api/endpoints/default/default';
import { getPayerMock } from '@/api/endpoints/payer-mock/payer-mock';
import { getPractices } from '@/api/endpoints/practices/practices';
import { getRegistry } from '@/api/endpoints/registry/registry';
import type {
  AdmissionCreate,
  AdmissionDashboardRead,
  DiagnosisRole,
  HospitalizationDiagnosisCreate,
  PatientCoverageCreate,
  PatientCreate,
  PayerAuthorizationRead,
} from '@/api/model';
import { Badge, Card, EmptyState, ErrorState, PageHeader, Spinner } from '@/components/ui';
import AvailableBedSelect from '@/components/beds/AvailableBedSelect';
import DiagnosisPicker from '@/components/diagnoses/DiagnosisPicker';
import CancelOrderModal from '@/components/hospitalization/CancelOrderModal';
import ProfessionalPicker from '@/components/professionals/ProfessionalPicker';
import { DIAGNOSIS_ROLE_LABELS } from '@/config/diagnosisLabels';
import { money } from '@/components/practices/labels';
import { ADMISSION_STATUS_COLORS, ADMISSION_STATUS_LABELS } from '@/config/workflowLabels';
import { apiErrorMessage } from '@/utils/api-error';
import { formatDate } from '@/utils/format';
import {
  BedDouble,
  CheckCircle2,
  ClipboardCheck,
  FileSignature,
  KeyRound,
  Search,
  ShieldCheck,
  UserPlus,
  Wallet,
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

/** Cuanto se sostiene la cama de una orden medica programada hasta que el paciente llega. */
const RESERVATION_WINDOWS = [
  { minutes: 120, label: '2 horas' },
  { minutes: 720, label: '12 horas' },
  { minutes: 1440, label: '24 horas' },
  { minutes: 4320, label: '3 dias' },
  { minutes: 10080, label: '7 dias' },
] as const;

/** The clerk either picks a coverage the patient already has, loads a new one, or admits
 * the patient as private. */
type CoverageChoice = 'NONE' | 'NEW' | string;

type CoverageDraft = {
  payer_id: string;
  health_plan_id: string;
  payer_name: string;
  member_number: string;
  /** Alta del afiliado: es desde cuando se cuentan las carencias de la cartilla. */
  valid_from: string;
  authorization_required: boolean;
};

const emptyCoverageDraft: CoverageDraft = {
  payer_id: '',
  health_plan_id: '',
  payer_name: '',
  member_number: '',
  valid_from: '',
  authorization_required: false,
};

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
  coverage_id: null,
  coverage: null,
  authorization_status: 'NOT_REQUIRED',
  authorization_number: '',
  responsible_contact_name: '',
  responsible_contact_phone: '',
  responsible_contact_relationship: '',
  admission_reason: '',
  responsible_physician: '',
  responsible_physician_id: null,
  requesting_service_id: null,
  presumptive_diagnosis: '',
  requested_bed_id: null,
  bed_reservation_expires_in_minutes: 1440,
  consents: [],
  notes: '',
  confirm_admission: true,
};

/** Orden medica programada cuyo paciente todavia no ingreso: se cancela, no se da de alta. */
function isPendingScheduledOrder(admission: AdmissionDashboardRead) {
  return (
    admission.origin === 'SCHEDULED_MEDICAL_ORDER' &&
    ['PENDING_BED', 'PENDING_AUTHORIZATION'].includes(admission.status)
  );
}

export default function AdmissionPanelPage() {
  const api = getDefault();
  const registry = getRegistry();
  const catalog = getPractices();
  const payerMock = getPayerMock();
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
  const [coverageChoice, setCoverageChoice] = useState<CoverageChoice>('NONE');
  /** Orden programada que se esta por dar de baja porque el paciente no va a venir. */
  const [cancelling, setCancelling] = useState<AdmissionDashboardRead | null>(null);
  const [coverageDraft, setCoverageDraft] = useState<CoverageDraft>(emptyCoverageDraft);
  /** Codigo de autorizacion que la cobertura le dio al afiliado, y para que practica. */
  const [authDraft, setAuthDraft] = useState({ practice_id: '', code: '' });
  const [payerAnswer, setPayerAnswer] = useState<PayerAuthorizationRead | null>(null);
  /** Lo que contesto la prestadora cuando la practica pasa a hacerse sin cobertura. */
  const [privateFallback, setPrivateFallback] = useState<PayerAuthorizationRead | null>(null);
  /** Diagnosticos de ingreso codificados: el texto libre es el relato, estos van a la
   * estadistica. El primero entra como principal. */
  const [diagnoses, setDiagnoses] = useState<
    (HospitalizationDiagnosisCreate & { description: string })[]
  >([]);

  const patientsQuery = useQuery({
    queryKey: ['patients'],
    queryFn: () => api.listPatientsApiV1PatientsGet(),
  });
  const servicesQuery = useQuery({
    queryKey: ['services'],
    queryFn: () => api.listServicesApiV1ServicesGet(),
  });
  const admissionsQuery = useQuery({
    queryKey: ['admissions'],
    queryFn: () => api.listAdmissionsApiV1AdmissionsGet(),
  });
  const payersQuery = useQuery({
    queryKey: ['payers'],
    queryFn: () => registry.listPayersApiV1PayersGet(),
  });
  const patientCoveragesQuery = useQuery({
    queryKey: ['patient-coverages', admissionForm.patient_id],
    queryFn: () =>
      registry.listPatientCoveragesApiV1PatientsPatientIdCoveragesGet(admissionForm.patient_id),
    enabled: admissionForm.patient_id !== '',
  });
  const professionalsQuery = useQuery({
    queryKey: ['professionals'],
    queryFn: () => api.listProfessionalsApiV1ProfessionalsGet(),
  });
  const plansQuery = useQuery({
    queryKey: ['health-plans', coverageDraft.payer_id],
    queryFn: () =>
      registry.listPayerHealthPlansApiV1PayersPayerIdHealthPlansGet(coverageDraft.payer_id),
    enabled: coverageDraft.payer_id !== '',
  });

  const createPatientMutation = useMutation({
    mutationFn: (data: PatientCreate) => api.createPatientApiV1PatientsPost(data),
    onSuccess: (patient) => {
      queryClient.invalidateQueries({ queryKey: ['patients'] });
      setAdmissionForm((current) => ({ ...current, patient_id: patient.id }));
      setPatientForm(initialPatient);
      setCoverageChoice('NEW');
      setCoverageDraft(emptyCoverageDraft);
    },
  });

  const createAdmissionMutation = useMutation({
    mutationFn: (data: AdmissionCreate) => api.createAdmissionApiV1AdmissionsPost(data),
    onSuccess: (admission) => {
      queryClient.invalidateQueries({ queryKey: ['admissions'] });
      queryClient.invalidateQueries({ queryKey: ['hospitalizations'] });
      queryClient.invalidateQueries({ queryKey: ['beds'] });
      queryClient.invalidateQueries({ queryKey: ['beds-available'] });
      setAdmissionForm(initialAdmission);
      setSignedConsents({ GENERAL_ADMISSION: false, DATA_PROCESSING: false, PROCEDURE: false });
      setCoverageChoice('NONE');
      setCoverageDraft(emptyCoverageDraft);
      setAuthDraft({ practice_id: '', code: '' });
      setPayerAnswer(null);
      setPrivateFallback(null);
      setDiagnoses([]);
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
  const services = servicesQuery.data ?? [];
  const admissions = admissionsQuery.data ?? [];

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
  const payers = payersQuery.data ?? [];
  const professionals = professionalsQuery.data ?? [];
  const plans = plansQuery.data ?? [];
  const patientCoverages = patientCoveragesQuery.data ?? [];
  const chosenCoverage = patientCoverages.find((coverage) => coverage.id === coverageChoice);

  /** El plan cuya cartilla y cuya prestadora mandan: el de la cobertura elegida, o el de la
   * cobertura nueva que se esta cargando. */
  const selectedPlanId =
    coverageChoice === 'NEW' ? coverageDraft.health_plan_id : (chosenCoverage?.health_plan_id ?? '');
  const memberNumber =
    coverageChoice === 'NEW' ? coverageDraft.member_number : (chosenCoverage?.member_number ?? '');

  const cartillaQuery = useQuery({
    queryKey: ['plan-practices', selectedPlanId],
    queryFn: () =>
      registry.listHealthPlanPracticesApiV1HealthPlansHealthPlanIdPracticesGet(selectedPlanId),
    enabled: selectedPlanId !== '',
  });
  const cartilla = cartillaQuery.data ?? [];
  // Un plan sin cartilla cargada no restringe nada: para autorizar se ofrece el catalogo.
  const practiceCatalogQuery = useQuery({
    queryKey: ['practices', 'active'],
    queryFn: () => catalog.listPracticesApiV1PracticesGet({ only_active: true }),
    enabled: selectedPlanId !== '' && cartillaQuery.isSuccess && cartilla.length === 0,
  });
  const authorizablePractices = cartilla.length
    ? cartilla.map((entry) => ({
        id: entry.practice_id,
        code: entry.practice_code,
        name: entry.practice_name,
      }))
    : (practiceCatalogQuery.data ?? []).map((practice) => ({
        id: practice.id,
        code: practice.code,
        name: practice.name,
      }));

  const verifyAuthorizationMutation = useMutation({
    mutationFn: () =>
      payerMock.verifyPayerAuthorizationApiV1PayerMockAuthorizationsPost({
        health_plan_id: selectedPlanId,
        authorization_code: authDraft.code,
        practice_id: authDraft.practice_id || null,
        member_number: memberNumber || null,
      }),
    onSuccess: (answer) => {
      setPayerAnswer(answer);
      setPrivateFallback(null);
      // Lo que contesta la prestadora es la autorizacion con la que queda la admision.
      setAdmissionForm((current) => ({
        ...current,
        authorization_status: answer.authorized ? 'AUTHORIZED' : 'REJECTED',
        authorization_number: answer.authorization_number ?? '',
      }));
    },
  });

  /** Cambiar de cobertura o de plan invalida lo que ya haya contestado la prestadora. */
  const resetAuthorization = () => {
    setAuthDraft({ practice_id: '', code: '' });
    setPayerAnswer(null);
    setPrivateFallback(null);
    verifyAuthorizationMutation.reset();
  };

  /** Sin autorizacion la practica se hace sin cobertura: la paga el paciente. */
  const takePrivate = () => {
    if (!payerAnswer) return;
    setPrivateFallback(payerAnswer);
    setPayerAnswer(null);
    setCoverageChoice('NONE');
    setAdmissionForm((current) => ({
      ...current,
      authorization_status: 'NOT_REQUIRED',
      authorization_number: '',
    }));
  };

  /** Selecting a patient starts the coverage step over: the ones listed belong to them. */
  const selectPatient = (patientId: string) => {
    setAdmissionForm((current) => ({
      ...current,
      patient_id: patientId,
      identity_validated: true,
      duplicate_checked: true,
    }));
    setCoverageChoice('NONE');
    setCoverageDraft(emptyCoverageDraft);
    resetAuthorization();
  };

  /** A coverage that needs authorization leaves the admission pending, unless the clerk
   * already resolved it. */
  const chooseCoverage = (choice: CoverageChoice, needsAuthorization: boolean) => {
    setCoverageChoice(choice);
    resetAuthorization();
    if (needsAuthorization && admissionForm.authorization_status === 'NOT_REQUIRED') {
      setAdmissionForm((current) => ({ ...current, authorization_status: 'PENDING' }));
    }
  };
  const duplicateMatches = patients.filter(
    (patient) =>
      patient.document_type === patientForm.document_type &&
      patient.document_number &&
      patient.document_number === patientForm.document_number,
  );

  /** En la orden medica programada el paciente todavia no llego: se le reserva la cama, y el
   * contacto y los consentimientos se toman cuando se presenta. */
  const scheduledOrder = admissionForm.origin === 'SCHEDULED_MEDICAL_ORDER';

  const steps = [
    { label: 'Paciente', done: Boolean(admissionForm.patient_id) },
    { label: 'Identidad', done: Boolean(admissionForm.identity_validated) },
    { label: 'Duplicados', done: Boolean(admissionForm.duplicate_checked) },
    {
      label: 'Cobertura',
      done:
        coverageChoice !== 'NEW' ||
        Boolean(coverageDraft.payer_id || coverageDraft.payer_name.trim()),
    },
    { label: 'Consentimientos', done: scheduledOrder || signedConsents.GENERAL_ADMISSION },
    {
      label: 'Ingreso',
      done: Boolean(admissionForm.admission_reason && admissionForm.responsible_physician_id),
    },
  ];

  const createPatient = (event: React.FormEvent) => {
    event.preventDefault();
    createPatientMutation.mutate(patientForm);
  };

  /** The API takes ``coverage_id`` for a coverage the patient already has, or ``coverage``
   * to register a new one along with the admission, but never both. */
  const coveragePayload = (): {
    coverage_id: string | null;
    coverage: PatientCoverageCreate | null;
  } => {
    if (coverageChoice === 'NONE') return { coverage_id: null, coverage: null };
    if (coverageChoice !== 'NEW') return { coverage_id: coverageChoice, coverage: null };

    const fromCatalog = coverageDraft.payer_id !== '';
    if (!fromCatalog && coverageDraft.payer_name.trim() === '') {
      return { coverage_id: null, coverage: null };
    }
    return {
      coverage_id: null,
      coverage: {
        payer_id: coverageDraft.payer_id || null,
        health_plan_id: coverageDraft.health_plan_id || null,
        // The catalog fills the names; free text is for the card the patient brings.
        payer_name: fromCatalog ? null : coverageDraft.payer_name.trim(),
        plan_name: null,
        member_number: coverageDraft.member_number.trim() || null,
        valid_from: coverageDraft.valid_from || null,
        authorization_required: coverageDraft.authorization_required,
        status: 'ACTIVE',
      },
    };
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
    createAdmissionMutation.mutate({
      ...admissionForm,
      responsible_contact_name: admissionForm.responsible_contact_name?.trim() || null,
      responsible_contact_phone: admissionForm.responsible_contact_phone?.trim() || null,
      ...coveragePayload(),
      diagnoses: diagnoses.map(({ code, role }) => ({ code, role })),
      requested_bed_id: admissionForm.requested_bed_id || null,
      requesting_service_id: admissionForm.requesting_service_id || null,
      consents,
    });
  };

  const loading =
    patientsQuery.isLoading ||
    servicesQuery.isLoading ||
    admissionsQuery.isLoading ||
    professionalsQuery.isLoading;
  const error =
    patientsQuery.isError ||
    servicesQuery.isError ||
    admissionsQuery.isError ||
    professionalsQuery.isError;

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
                        onClick={() => selectPatient(patient.id)}
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
              {!admissionForm.patient_id && (
                <p className="rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-500">
                  Elija primero un paciente para ver sus coberturas.
                </p>
              )}

              {admissionForm.patient_id && (
                <div className="space-y-3">
                  {patientCoveragesQuery.isLoading && <Spinner />}

                  {patientCoverages.map((coverage) => (
                    <label
                      key={coverage.id}
                      className={`flex cursor-pointer items-start gap-3 rounded-lg border px-4 py-3 transition-colors ${
                        coverageChoice === coverage.id
                          ? 'border-teal-400 bg-teal-50/60'
                          : 'border-slate-200 hover:bg-slate-50'
                      }`}
                    >
                      <input
                        type="radio"
                        name="coverage-choice"
                        checked={coverageChoice === coverage.id}
                        onChange={() => chooseCoverage(coverage.id, coverage.authorization_required)}
                        className="mt-1 h-4 w-4"
                      />
                      <span>
                        <span className="block text-sm font-semibold text-slate-700">
                          {coverage.payer_name}
                          {coverage.plan_name ? ` · ${coverage.plan_name}` : ''}
                        </span>
                        <span className="block text-xs text-slate-400">
                          {coverage.member_number
                            ? `Afiliado ${coverage.member_number}`
                            : 'Sin numero de afiliado'}
                          {coverage.status !== 'ACTIVE' ? ` · ${coverage.status}` : ''}
                          {coverage.authorization_required ? ' · requiere autorizacion' : ''}
                        </span>
                      </span>
                    </label>
                  ))}

                  <label
                    className={`flex cursor-pointer items-center gap-3 rounded-lg border px-4 py-3 transition-colors ${
                      coverageChoice === 'NEW'
                        ? 'border-teal-400 bg-teal-50/60'
                        : 'border-slate-200 hover:bg-slate-50'
                    }`}
                  >
                    <input
                      type="radio"
                      name="coverage-choice"
                      checked={coverageChoice === 'NEW'}
                      onChange={() => chooseCoverage('NEW', coverageDraft.authorization_required)}
                      className="h-4 w-4"
                    />
                    <span className="text-sm font-semibold text-slate-700">Cargar una cobertura nueva</span>
                  </label>

                  {coverageChoice === 'NEW' && (
                    <div className="grid gap-4 rounded-lg bg-slate-50 p-4 md:grid-cols-3">
                      <select
                        value={coverageDraft.payer_id}
                        onChange={(e) =>
                          setCoverageDraft({
                            ...coverageDraft,
                            payer_id: e.target.value,
                            health_plan_id: '',
                          })
                        }
                        className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                      >
                        <option value="">Sin catalogo (cargar a mano)</option>
                        {payers.map((payer) => (
                          <option key={payer.id} value={payer.id}>
                            {payer.name}
                          </option>
                        ))}
                      </select>

                      {coverageDraft.payer_id ? (
                        <select
                          value={coverageDraft.health_plan_id}
                          onChange={(e) => {
                            setCoverageDraft({ ...coverageDraft, health_plan_id: e.target.value });
                            resetAuthorization();
                          }}
                          className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                        >
                          <option value="">Sin plan</option>
                          {plans.map((plan) => (
                            <option key={plan.id} value={plan.id}>
                              {plan.name}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          placeholder="Nombre del financiador"
                          value={coverageDraft.payer_name}
                          onChange={(e) =>
                            setCoverageDraft({ ...coverageDraft, payer_name: e.target.value })
                          }
                          className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                        />
                      )}

                      <input
                        placeholder="Afiliado"
                        value={coverageDraft.member_number}
                        onChange={(e) =>
                          setCoverageDraft({ ...coverageDraft, member_number: e.target.value })
                        }
                        className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                      />

                      <label className="text-xs text-slate-500 md:col-span-3">
                        Afiliado desde (las carencias de la cartilla se cuentan desde esta fecha)
                        <input
                          type="date"
                          value={coverageDraft.valid_from}
                          onChange={(e) =>
                            setCoverageDraft({ ...coverageDraft, valid_from: e.target.value })
                          }
                          className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 outline-none focus:border-teal-500 md:w-64"
                        />
                      </label>

                      <label className="flex items-center gap-2 text-sm text-slate-600 md:col-span-3">
                        <input
                          type="checkbox"
                          checked={coverageDraft.authorization_required}
                          onChange={(e) =>
                            setCoverageDraft({
                              ...coverageDraft,
                              authorization_required: e.target.checked,
                            })
                          }
                          className="h-4 w-4 rounded border-slate-300"
                        />
                        Requiere autorizacion previa
                      </label>
                    </div>
                  )}

                  {selectedPlanId && (
                    <div className="space-y-3 rounded-lg border border-teal-100 bg-teal-50/40 p-4">
                      <div className="flex items-center gap-2">
                        <KeyRound className="h-4 w-4 text-teal-600" />
                        <h3 className="text-sm font-bold text-slate-700">
                          Autorizacion de la cobertura
                        </h3>
                      </div>
                      <p className="text-xs text-slate-500">
                        Codigo de 3 digitos que la cobertura le dio al afiliado. Se valida contra
                        la prestadora antes de confirmar el ingreso.
                      </p>
                      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_140px_auto]">
                        <select
                          value={authDraft.practice_id}
                          onChange={(e) => {
                            setAuthDraft({ ...authDraft, practice_id: e.target.value });
                            setPayerAnswer(null);
                          }}
                          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                        >
                          <option value="">Practica a autorizar</option>
                          {authorizablePractices.map((practice) => (
                            <option key={practice.id} value={practice.id}>
                              {practice.code} - {practice.name}
                            </option>
                          ))}
                        </select>
                        <input
                          inputMode="numeric"
                          maxLength={3}
                          placeholder="Codigo (3 digitos)"
                          value={authDraft.code}
                          onChange={(e) => {
                            setAuthDraft({
                              ...authDraft,
                              code: e.target.value.replace(/\D/g, '').slice(0, 3),
                            });
                            setPayerAnswer(null);
                          }}
                          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                        />
                        <button
                          type="button"
                          onClick={() => verifyAuthorizationMutation.mutate()}
                          disabled={
                            authDraft.code.length !== 3 || verifyAuthorizationMutation.isPending
                          }
                          className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
                        >
                          {verifyAuthorizationMutation.isPending ? 'Validando...' : 'Validar'}
                        </button>
                      </div>

                      {verifyAuthorizationMutation.isError && (
                        <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">
                          {apiErrorMessage(
                            verifyAuthorizationMutation.error,
                            'No se pudo consultar a la cobertura.',
                          )}
                        </p>
                      )}

                      {payerAnswer?.authorized && (
                        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs text-emerald-800">
                          <p className="font-semibold">{payerAnswer.message}</p>
                          <p className="mt-1">
                            Autorizacion {payerAnswer.authorization_number}
                            {payerAnswer.valid_until
                              ? ` · vigente hasta ${formatDate(payerAnswer.valid_until)}`
                              : ''}
                          </p>
                          {Number(payerAnswer.copayment_amount) > 0 ? (
                            <p className="mt-2 flex items-center gap-2 font-semibold">
                              <Wallet className="h-4 w-4" />
                              Copago a cargo del paciente:{' '}
                              {money(payerAnswer.copayment_amount, payerAnswer.currency)}
                            </p>
                          ) : (
                            payerAnswer.practice_id && (
                              <p className="mt-2">
                                La practica no tiene copago: la cubre el plan en su totalidad.
                              </p>
                            )
                          )}
                        </div>
                      )}

                      {payerAnswer && !payerAnswer.authorized && (
                        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
                          <p className="font-semibold">{payerAnswer.message}</p>
                          <p className="mt-1">
                            {payerAnswer.private_amount
                              ? `Se puede hacer en forma particular: el paciente abona ${money(
                                  payerAnswer.private_amount,
                                  payerAnswer.currency,
                                )}.`
                              : 'Se puede hacer en forma particular; la practica no tiene valor cargado en el nomenclador.'}
                          </p>
                          <button
                            type="button"
                            onClick={takePrivate}
                            className="mt-2 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700"
                          >
                            Atender como particular
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  <label
                    className={`flex cursor-pointer items-center gap-3 rounded-lg border px-4 py-3 transition-colors ${
                      coverageChoice === 'NONE'
                        ? 'border-teal-400 bg-teal-50/60'
                        : 'border-slate-200 hover:bg-slate-50'
                    }`}
                  >
                    <input
                      type="radio"
                      name="coverage-choice"
                      checked={coverageChoice === 'NONE'}
                      onChange={() => setCoverageChoice('NONE')}
                      className="h-4 w-4"
                    />
                    <span className="text-sm font-semibold text-slate-700">
                      Particular, sin cobertura
                    </span>
                  </label>

                  {privateFallback && coverageChoice === 'NONE' && (
                    <p className="flex items-center gap-2 rounded-lg bg-amber-50 px-4 py-3 text-xs font-medium text-amber-800">
                      <Wallet className="h-4 w-4 shrink-0" />
                      <span>
                        {privateFallback.practice_name ?? 'La practica'} se hace en forma
                        particular porque {privateFallback.payer_name} no la autorizo
                        {privateFallback.private_amount
                          ? `: el paciente abona ${money(
                              privateFallback.private_amount,
                              privateFallback.currency,
                            )}.`
                          : '. La practica no tiene valor cargado en el nomenclador.'}
                      </span>
                    </p>
                  )}
                </div>
              )}

              <div className="mt-4 grid gap-4 md:grid-cols-2">
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
                <input
                  placeholder="Numero de autorizacion"
                  value={admissionForm.authorization_number ?? ''}
                  onChange={(e) =>
                    setAdmissionForm({ ...admissionForm, authorization_number: e.target.value })
                  }
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                />
              </div>

              {chosenCoverage?.authorization_required &&
                admissionForm.authorization_status === 'PENDING' && (
                  <p className="mt-3 rounded-lg bg-amber-50 px-4 py-2 text-xs font-medium text-amber-700">
                    {chosenCoverage.payer_name} exige autorizacion previa: la admision queda
                    pendiente hasta que se cargue el numero.
                  </p>
                )}
            </Card>

            <Card className="p-5">
              <div className="mb-4 flex items-center gap-2">
                <ClipboardCheck className="h-5 w-5 text-teal-600" />
                <h2 className="text-base font-bold text-slate-800">Ingreso e internacion</h2>
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                <select
                  value={admissionForm.origin}
                  onChange={(e) => {
                    const origin = e.target.value as AdmissionCreate['origin'];
                    setAdmissionForm({
                      ...admissionForm,
                      origin,
                      // Una orden programada no es una urgencia.
                      admission_type:
                        origin === 'SCHEDULED_MEDICAL_ORDER' && admissionForm.admission_type === 'EMERGENCY'
                          ? 'SCHEDULED'
                          : admissionForm.admission_type,
                    });
                  }}
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
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-600">
                    Medico responsable
                  </label>
                  <ProfessionalPicker
                    value={admissionForm.responsible_physician_id ?? ''}
                    onSelect={(id) => {
                      const professional = professionals.find((item) => item.id === id);
                      setAdmissionForm({
                        ...admissionForm,
                        responsible_physician_id: professional?.id ?? null,
                        // El nombre queda escrito en la admision: es lo que se lee despues
                        // aunque el legajo del profesional cambie.
                        responsible_physician: professional
                          ? `${professional.last_name}, ${professional.first_name}`
                          : '',
                      });
                    }}
                    emptyLabel=""
                  />
                </div>
                <input
                  placeholder="Diagnostico presuntivo"
                  value={admissionForm.presumptive_diagnosis ?? ''}
                  onChange={(e) =>
                    setAdmissionForm({ ...admissionForm, presumptive_diagnosis: e.target.value })
                  }
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                />
              </div>

              <div className="mt-4 rounded-lg bg-slate-50 p-4">
                <p className="mb-2 text-sm font-semibold text-slate-700">
                  Diagnosticos de ingreso (CIE-10)
                </p>
                <p className="mb-3 text-xs text-slate-500">
                  Son presuntivos: el diagnostico definitivo lo asienta el medico con el alta.
                  El primero que se agrega queda como principal. Quedan indicados por{' '}
                  <span className="font-semibold text-slate-600">
                    {admissionForm.responsible_physician || 'el medico responsable (elegilo arriba)'}
                  </span>
                  .
                </p>
                <DiagnosisPicker
                  onSelect={(code) =>
                    setDiagnoses((current) =>
                      current.some((item) => item.code === code.code)
                        ? current
                        : [
                            ...current,
                            {
                              code: code.code,
                              description: code.description,
                              role: current.length === 0 ? 'PRINCIPAL' : 'SECONDARY',
                            },
                          ],
                    )
                  }
                />
                {diagnoses.length > 0 && (
                  <div className="mt-3 divide-y divide-slate-100 rounded-lg bg-white">
                    {diagnoses.map((item) => (
                      <div
                        key={item.code}
                        className="flex flex-wrap items-center justify-between gap-3 px-3 py-2"
                      >
                        <p className="text-sm text-slate-700">
                          <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-bold">
                            {item.code}
                          </span>{' '}
                          {item.description}
                        </p>
                        <div className="flex items-center gap-2">
                          <select
                            value={item.role ?? 'SECONDARY'}
                            onChange={(e) =>
                              setDiagnoses((current) =>
                                current.map((entry) =>
                                  entry.code === item.code
                                    ? { ...entry, role: e.target.value as DiagnosisRole }
                                    : entry,
                                ),
                              )
                            }
                            className="rounded-lg border border-slate-200 px-2 py-1 text-xs outline-none focus:border-teal-500"
                          >
                            {Object.entries(DIAGNOSIS_ROLE_LABELS).map(([value, label]) => (
                              <option key={value} value={value}>
                                {label}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            onClick={() =>
                              setDiagnoses((current) =>
                                current.filter((entry) => entry.code !== item.code),
                              )
                            }
                            className="rounded-lg px-2 py-1 text-xs font-semibold text-red-600 hover:bg-red-50"
                          >
                            Quitar
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
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
                {scheduledOrder && <Badge status="Opcional" color="bg-slate-100 text-slate-500" />}
              </div>
              {scheduledOrder && (
                <p className="mb-4 rounded-lg bg-slate-50 px-4 py-2 text-xs text-slate-500">
                  Orden medica programada: el paciente todavia no llego. El contacto y los
                  consentimientos se pueden tomar cuando se presente a internarse.
                </p>
              )}
              <div className="grid gap-4 md:grid-cols-3">
                <input
                  required={!scheduledOrder}
                  placeholder="Contacto responsable"
                  value={admissionForm.responsible_contact_name ?? ''}
                  onChange={(e) =>
                    setAdmissionForm({ ...admissionForm, responsible_contact_name: e.target.value })
                  }
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                />
                <input
                  required={!scheduledOrder}
                  placeholder="Telefono"
                  value={admissionForm.responsible_contact_phone ?? ''}
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
                <h2 className="text-base font-bold text-slate-800">
                  {scheduledOrder ? 'Reserva de cama' : 'Solicitud de cama'}
                </h2>
              </div>
              {scheduledOrder && (
                <p className="mb-3 text-xs text-slate-500">
                  La cama queda reservada para el paciente sin ocuparla. Cuando llega, se confirma
                  la reserva desde la internacion.
                </p>
              )}
              <div
                className={scheduledOrder ? 'grid gap-4 md:grid-cols-[minmax(0,1fr)_200px]' : undefined}
              >
                <AvailableBedSelect
                  value={admissionForm.requested_bed_id ?? ''}
                  onChange={(bedId) =>
                    setAdmissionForm((current) => ({ ...current, requested_bed_id: bedId || null }))
                  }
                  emptyLabel={
                    scheduledOrder
                      ? 'Registrar la orden sin reservar cama'
                      : 'Confirmar ingreso sin cama asignada'
                  }
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500"
                />
                {scheduledOrder && (
                  <select
                    value={admissionForm.bed_reservation_expires_in_minutes ?? 1440}
                    onChange={(e) =>
                      setAdmissionForm({
                        ...admissionForm,
                        bed_reservation_expires_in_minutes: Number(e.target.value),
                      })
                    }
                    disabled={!admissionForm.requested_bed_id}
                    aria-label="Vigencia de la reserva"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-500 disabled:opacity-50"
                  >
                    {RESERVATION_WINDOWS.map((window) => (
                      <option key={window.minutes} value={window.minutes}>
                        Reserva por {window.label}
                      </option>
                    ))}
                  </select>
                )}
              </div>

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
                  disabled={
                    createAdmissionMutation.isPending ||
                    !admissionForm.patient_id ||
                    !admissionForm.responsible_physician_id
                  }
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-teal-500 to-cyan-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md disabled:opacity-50"
                >
                  <CheckCircle2 className="h-4 w-4" />
                  {createAdmissionMutation.isPending
                    ? 'Confirmando...'
                    : scheduledOrder
                      ? admissionForm.requested_bed_id
                        ? 'Reservar cama'
                        : 'Registrar orden'
                      : 'Confirmar ingreso'}
                </button>
              </div>
              {createAdmissionMutation.isError && (
                <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
                  {apiErrorMessage(
                    createAdmissionMutation.error,
                    'No se pudo confirmar la admision. Revisa identidad, duplicados y autorizacion.',
                  )}
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
                      {isPendingScheduledOrder(admission) && (
                        <button
                          type="button"
                          onClick={() => setCancelling(admission)}
                          className="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-semibold text-red-600 hover:bg-red-50"
                        >
                          Cancelar orden
                        </button>
                      )}
                      {!['ADMINISTRATIVE_DISCHARGE', 'CANCELLED', 'REJECTED'].includes(admission.status) &&
                        !isPendingScheduledOrder(admission) && (
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

      {cancelling && (
        <CancelOrderModal
          admissionId={cancelling.id}
          hospitalizationId={cancelling.hospitalization_id}
          patientName={`${cancelling.patient.first_name} ${cancelling.patient.last_name}`}
          onClose={() => setCancelling(null)}
        />
      )}
    </div>
  );
}
