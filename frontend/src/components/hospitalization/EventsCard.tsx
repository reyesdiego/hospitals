import { useQuery } from '@tanstack/react-query';
import { getHospitalizationWorkflow } from '@/api/endpoints/hospitalization-workflow/hospitalization-workflow';
import { Card, SectionTitle } from '@/components/ui';
import { EVENT_TYPE_LABELS } from '@/config/workflowLabels';
import { formatDateTime } from '@/utils/format';
import { History } from 'lucide-react';

export function EventsCard({ hospitalizationId }: { hospitalizationId: string }) {
  const api = getHospitalizationWorkflow();
  const eventsQuery = useQuery({
    queryKey: ['hospitalization-events', hospitalizationId],
    queryFn: () =>
      api.listHospitalizationEventsApiV1HospitalizationsHospitalizationIdEventsGet(
        hospitalizationId,
      ),
  });

  const events = [...(eventsQuery.data ?? [])].reverse();

  return (
    <Card className="p-6">
      <SectionTitle icon={<History className="h-5 w-5 text-teal-600" />}>
        Auditoria de la internacion
      </SectionTitle>
      {events.length === 0 ? (
        <p className="text-sm text-slate-400">Sin eventos registrados.</p>
      ) : (
        <ol className="space-y-3">
          {events.map((event) => (
            <li key={event.id} className="border-l-2 border-slate-100 pl-4">
              <p className="text-sm font-semibold text-slate-700">
                {EVENT_TYPE_LABELS[event.event_type] ?? event.event_type}
              </p>
              <p className="text-xs text-slate-400">
                {formatDateTime(event.occurred_at)}
                {event.actor ? ` · ${event.actor}` : ''}
              </p>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

export default EventsCard;
