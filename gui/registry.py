"""Registered jobs shown in the GUI sidebar."""

from gui.job_spec import JobSpec
from scripts.artikelnummern import JOB_SPEC as artikelnummern
from scripts.generate_weclapp_import import JOB_SPEC as weclapp_import
from scripts.gruppen_diagram import JOB_SPEC as gruppen_diagram
from scripts.master_dashboard import JOB_SPEC as master_dashboard
from scripts.replace_legacy_names import JOB_SPEC as legacy_names

JOBS: list[JobSpec] = [
    artikelnummern,
    legacy_names,
    weclapp_import,
    gruppen_diagram,
    master_dashboard,
]
