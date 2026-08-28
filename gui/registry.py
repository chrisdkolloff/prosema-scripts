"""Registered jobs shown in the GUI sidebar."""

from gui.job_spec import JobSpec
from scripts.export.generate_weclapp_import import JOB_SPEC as weclapp_import
from scripts.processing.artikelnummern import JOB_SPEC as artikelnummern
from scripts.processing.fill_prosema_prices import JOB_SPEC as fill_prosema_prices
from scripts.processing.replace_legacy_names import JOB_SPEC as legacy_names
from scripts.reports.gruppen_diagram import JOB_SPEC as gruppen_diagram
from scripts.reports.master_dashboard import JOB_SPEC as master_dashboard
from scripts.weclapp.export_articles import JOB_SPEC as weclapp_export_articles
from scripts.weclapp.test_connection import JOB_SPEC as weclapp_test

# weclapp article create jobs removed: use /artikel-registrierung in the web app.
JOBS: list[JobSpec] = [
    artikelnummern,
    legacy_names,
    weclapp_import,
    fill_prosema_prices,
    weclapp_test,
    weclapp_export_articles,
    gruppen_diagram,
    master_dashboard,
]
