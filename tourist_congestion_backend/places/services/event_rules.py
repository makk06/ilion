from .hourly_forecast import dt


def overlaps(event, at):
    at = dt(at)
    if event.get('starts_at') and event.get('ends_at'):
        return dt(event['starts_at']) <= at < dt(event['ends_at'])
    return event['start_date'] <= at.date().isoformat() <= event['end_date']
