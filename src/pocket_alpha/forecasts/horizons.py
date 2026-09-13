import calendar
from datetime import datetime, timedelta

from pocket_alpha.common.clock import utc
from pocket_alpha.domain.models import ForecastHorizon

_FIXED = {
    ForecastHorizon.H1: timedelta(hours=1),
    ForecastHorizon.H4: timedelta(hours=4),
    ForecastHorizon.H8: timedelta(hours=8),
    ForecastHorizon.H12: timedelta(hours=12),
    ForecastHorizon.H24: timedelta(hours=24),
    ForecastHorizon.D2: timedelta(days=2),
    ForecastHorizon.D3: timedelta(days=3),
    ForecastHorizon.D7: timedelta(days=7),
    ForecastHorizon.D14: timedelta(days=14),
    ForecastHorizon.D30: timedelta(days=30),
    ForecastHorizon.D90: timedelta(days=90),
}


def expires_at(generated_at: datetime, horizon: ForecastHorizon) -> datetime:
    """Resolve fixed horizons or UTC calendar months, clamping month-end."""
    generated_at = utc(generated_at)
    if horizon in _FIXED:
        return generated_at + _FIXED[horizon]
    months = 6 if horizon == ForecastHorizon.M6 else 12
    absolute_month = generated_at.year * 12 + generated_at.month - 1 + months
    year, month_index = divmod(absolute_month, 12)
    month = month_index + 1
    day = min(generated_at.day, calendar.monthrange(year, month)[1])
    return generated_at.replace(year=year, month=month, day=day)
