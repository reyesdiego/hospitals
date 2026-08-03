import { type Role } from '../auth/types';

export type NavItem = {
  label: string;
  path: string;
  icon: string;
  roles: Role[];
};

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
  type LucideIcon,
} from 'lucide-react';

export type NavConfig = {
  label: string;
  path: string;
  icon: LucideIcon;
  roles: Role[];
};

export const NAV_ITEMS: NavConfig[] = [
  {
    label: 'Panel principal',
    path: '/dashboard',
    icon: LayoutDashboard,
    roles: ['admin', 'doctor', 'nurse', 'receptionist', 'patient'],
  },
  {
    label: 'Pacientes',
    path: '/patients',
    icon: Users,
    roles: ['admin', 'doctor', 'nurse', 'receptionist'],
  },
  {
    label: 'Admision',
    path: '/admissions',
    icon: ClipboardCheck,
    roles: ['admin', 'doctor', 'nurse', 'receptionist'],
  },
  {
    label: 'Hospitalizaciones',
    path: '/hospitalizations',
    icon: ClipboardPlus,
    roles: ['admin', 'doctor', 'nurse'],
  },
  {
    label: 'Camas',
    path: '/beds',
    icon: BedDouble,
    roles: ['admin', 'doctor', 'nurse'],
  },
  {
    label: 'Habitaciones',
    path: '/rooms',
    icon: DoorOpen,
    roles: ['admin', 'nurse'],
  },
  {
    label: 'Centros',
    path: '/facilities',
    icon: Building2,
    roles: ['admin'],
  },
  {
    label: 'Servicios',
    path: '/services',
    icon: Stethoscope,
    roles: ['admin'],
  },
];

export const ICONS = { HeartPulse };
