"""Registered jobs shown in the GUI sidebar."""

from gui.job_spec import JobSpec
from scripts.artikelnummern import JOB_SPEC as artikelnummern
from scripts.generate_weclapp_import import JOB_SPEC as weclapp_import
from scripts.replace_legacy_names import JOB_SPEC as legacy_names

JOBS: list[JobSpec] = [artikelnummern, legacy_names, weclapp_import]
