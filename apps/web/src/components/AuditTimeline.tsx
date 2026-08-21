import type { AuditEvent } from "@/lib/types";

export function AuditTimeline({ events }: { events: AuditEvent[] }) {
  return (
    <section className="panel audit-panel" aria-labelledby="audit-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">04 · Reproducible audit</p>
          <h2 id="audit-title">Mandate timeline</h2>
        </div>
        <span className="status-chip ready">Append only</span>
      </div>
      {events.length === 0 ? (
        <p className="supporting-copy">Authenticate a mandate to begin the evidence trail.</p>
      ) : (
        <ol className="timeline">
          {events.map((event) => {
            const reasons = Array.isArray(event.payload.reason_codes)
              ? event.payload.reason_codes.filter((value): value is string => typeof value === "string")
              : [];
            const versions =
              event.payload.model_versions && typeof event.payload.model_versions === "object"
                ? (event.payload.model_versions as Record<string, unknown>)
                : null;
            return (
              <li key={event.event_id}>
                <span className="timeline-marker" />
                <div>
                  <strong>{event.event_type.replaceAll("_", " ")}</strong>
                  <time dateTime={event.created_at}>{new Date(event.created_at).toLocaleTimeString()}</time>
                  {event.payload.treatment ? <p>Treatment: {String(event.payload.treatment)}</p> : null}
                  {reasons.length > 0 ? <p>{reasons.join(" · ")}</p> : null}
                  {versions?.policy ? <code>{String(versions.policy)}</code> : null}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
