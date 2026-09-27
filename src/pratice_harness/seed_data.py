"""Load the sample records from the checkout or the installed wheel."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


_source = Path(__file__).resolve().parents[2] / "data" / "sample_data.py"
if _source.is_file():
    # Editable installs copy wheel data into site-packages, where it can become stale.
    _spec = spec_from_file_location("pratice_harness_local_sample_data", _source)
    if _spec is None or _spec.loader is None:
        raise RuntimeError(f"Cannot load sample data from {_source}")
    _module = module_from_spec(_spec)
    _spec.loader.exec_module(_module)
    seed_database = _module.seed_database
else:
    from sample_data import seed_database
