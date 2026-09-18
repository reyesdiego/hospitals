import type { QueryClient } from '@tanstack/react-query';

const HOSPITALIZATION_SCOPED = [
  'hospitalization',
  'hospitalization-bed-assignments',
  'hospitalization-events',
  'hospitalization-practices',
  'account',
  'bed-reservations',
  'service-assignments',
  'care-team',
  'discharge-plans',
  'discharge',
] as const;

const GLOBAL_SCOPED = ['beds', 'beds-available', 'rooms', 'hospitalizations', 'admissions'] as const;

/** Every lifecycle action can move beds, statuses and the audit trail at once. */
export function invalidateHospitalization(queryClient: QueryClient, hospitalizationId: string) {
  HOSPITALIZATION_SCOPED.forEach((key) =>
    queryClient.invalidateQueries({ queryKey: [key, hospitalizationId] }),
  );
  GLOBAL_SCOPED.forEach((key) => queryClient.invalidateQueries({ queryKey: [key] }));
}

export function invalidateBeds(queryClient: QueryClient) {
  GLOBAL_SCOPED.forEach((key) => queryClient.invalidateQueries({ queryKey: [key] }));
  queryClient.invalidateQueries({ queryKey: ['bed-status-history'] });
}
