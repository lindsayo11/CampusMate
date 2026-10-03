from alembic import context
from app.database import Base, engine
from app import models, social, teams, worker, rate_limits, sources, operations, team_tasks, collector, knowledge, task_alerts, intake_models  # register all domain tables
from app import agent_state, data_feedback, startup_models


def run():
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata,
                          render_as_batch=connection.dialect.name == 'sqlite', compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

run()
