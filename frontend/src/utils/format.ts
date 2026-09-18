export function formatDateTime(value: string | null | undefined): string | null {
  return value ? new Date(value).toLocaleString('es-ES') : null;
}

export function formatDate(value: string | null | undefined): string | null {
  return value ? new Date(`${value}T00:00:00`).toLocaleDateString('es-ES') : null;
}

export function formatTime(value: string | null | undefined): string | null {
  return value
    ? new Date(value).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
    : null;
}

export function minutesUntil(value: string | null | undefined): number | null {
  if (!value) return null;
  return Math.round((new Date(value).getTime() - Date.now()) / 60000);
}
