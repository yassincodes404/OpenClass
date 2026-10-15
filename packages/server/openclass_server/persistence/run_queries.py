"""SQL expressions for the effective run view (immutable run + checkpoint)."""

import sqlalchemy as sa

from .tables import DecisionRunCheckpointRow as Checkpoint
from .tables import DecisionRunRow as Run

choice = sa.func.coalesce(Checkpoint.selected_choice, Run.selected_choice)
supervision = sa.func.coalesce(Checkpoint.supervision_outcome, Run.supervision_outcome)
latency = sa.func.coalesce(Checkpoint.latency_ms, Run.latency_ms)
unknown = sa.or_(choice == "UNKNOWN", supervision == "UNKNOWN")
joined_runs = Run.__table__.outerjoin(Checkpoint, Run.id == Checkpoint.run_id)
