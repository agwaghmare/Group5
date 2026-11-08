"""Report what is actually present in the finpilot/compliance schemas (verification helper)."""
from sqlalchemy import text

from app.core.db import get_engine

with get_engine().connect() as c:
    def q(sql):
        return c.execute(text(sql)).all()

    print("alembic:", q("select version_num from public.finpilot_alembic_version"))
    tabs = q("select table_schema, count(*) from information_schema.tables where table_schema in ('finpilot','compliance') and table_type='BASE TABLE' group by 1")
    print("base tables:", tabs)
    print("hypertables:", sorted(r[0] for r in q("select hypertable_name from timescaledb_information.hypertables where hypertable_schema='finpilot'")))
    print("rls tables:", len(q("select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname in ('finpilot','compliance') and c.relrowsecurity")))
    print("policies:", q("select count(*) from pg_policies where schemaname in ('finpilot','compliance')")[0][0])
    print("views:", sorted(r[0] for r in q("select table_name from information_schema.views where table_schema='finpilot'")))
    print("app roles:", sorted(r[0] for r in q("select rolname from pg_roles where rolname like 'app\\_%'")))
    print("immutable triggers:", sorted(r[0] for r in q("select distinct tgname from pg_trigger where tgname like 'trg\\_%' and not tgisinternal")))
