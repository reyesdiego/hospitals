import { type Permission } from '@/api/model';
import {
  LayoutDashboard,
  Users,
  BedDouble,
  Building2,
  DoorOpen,
  ClipboardPlus,
  HeartPulse,
  Stethoscope,
  ClipboardCheck,
  ClipboardList,
  BookMarked,
  TrendingUp,
  ShieldPlus,
  Syringe,
  UserCog,
  type LucideIcon,
} from 'lucide-react';

export type NavConfig = {
  label: string;
  path: string;
  icon: LucideIcon;
  /** Vacio: lo ve cualquier usuario con sesion. Si no, hace falta alguno de estos permisos. */
  permissions: Permission[];
};

export const NAV_ITEMS: NavConfig[] = [
  {
    label: 'Panel principal',
    path: '/dashboard',
    icon: LayoutDashboard,
    permissions: [],
  },
  {
    label: 'Pacientes',
    path: '/patients',
    icon: Users,
    permissions: ['ADMISSION'],
  },
  {
    label: 'Profesionales',
    path: '/professionals',
    icon: Stethoscope,
    permissions: ['CATALOG'],
  },
  {
    label: 'Admision',
    path: '/admissions',
    icon: ClipboardCheck,
    permissions: ['ADMISSION'],
  },
  {
    label: 'Hospitalizaciones',
    path: '/hospitalizations',
    icon: ClipboardPlus,
    permissions: ['HOSPITALIZATION'],
  },
  {
    label: 'Tareas de enfermeria',
    path: '/nursing-tasks',
    icon: Syringe,
    permissions: ['NURSING_TASKS'],
  },
  {
    label: 'Camas',
    path: '/beds',
    icon: BedDouble,
    permissions: ['BED_CLEANING', 'BED_MANAGEMENT'],
  },
  {
    label: 'Habitaciones',
    path: '/rooms',
    icon: DoorOpen,
    permissions: ['CATALOG'],
  },
  {
    label: 'Centros',
    path: '/facilities',
    icon: Building2,
    permissions: ['CATALOG'],
  },
  {
    label: 'Servicios',
    path: '/services',
    icon: Stethoscope,
    permissions: ['CATALOG'],
  },
  {
    label: 'Practicas medicas',
    path: '/practices',
    icon: ClipboardList,
    permissions: ['CATALOG'],
  },
  {
    label: 'Diagnosticos CIE-10',
    path: '/diagnoses',
    icon: BookMarked,
    permissions: ['CATALOG'],
  },
  {
    label: 'Coberturas',
    path: '/coverages',
    icon: ShieldPlus,
    permissions: ['CATALOG'],
  },
  {
    label: 'Informe estadistico',
    path: '/reports/morbidity',
    icon: TrendingUp,
    permissions: ['HOSPITALIZATION', 'ADMISSION'],
  },
  {
    label: 'Usuarios',
    path: '/users',
    icon: UserCog,
    permissions: ['USER_ADMIN'],
  },
];

export const ICONS = { HeartPulse };
