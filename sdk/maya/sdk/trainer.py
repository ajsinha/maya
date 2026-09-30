"""
Run inside a job MAYA dispatched: fetch the warrant's data, fit, upload the parameters.

    # train.py, the job's entrypoint
    from maya.sdk.trainer import fit_under_warrant

    def fit(train, target):
        ...                                   # your code, on your compute
        return {"a": 2.0, "b": 0.5}, {"rmse": 0.01}

    fit_under_warrant(fit)

The job's environment carries what the dispatch issued -- ``MAYA_URL``, ``MAYA_API_KEY``,
``MAYA_WARRANT_ID``, ``MAYA_DISPATCH_ID``. The data is the warrant's training and validation
rows and nothing else; ``fit`` receives the training rows and the target's name. The
parameters go back with the data's checksum, so MAYA can verify they were fitted on exactly
the rows it issued, and with the dispatch id among their metrics, so the parameter set says
which dispatched run produced it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import os
from typing import Any, Callable


def fit_under_warrant(
    fit: Callable[[Any, str], tuple[dict[str, float], dict[str, Any]]],
    client: Any = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fit on the warrant's training rows and upload the result; returns the parameter set."""
    env = dict(os.environ if env is None else env)
    warrant_id, dispatch_id = env["MAYA_WARRANT_ID"], env.get("MAYA_DISPATCH_ID", "")
    if client is None:
        from maya.sdk import Client

        client = Client(env["MAYA_URL"], token=env["MAYA_API_KEY"])
    warrant = client.warrant(warrant_id)
    with warrant.data() as ds:
        frame = ds.frame
        train = frame[frame["_split"] == "train"] if "_split" in frame.columns else frame
        values, metrics = fit(train, ds.target)
        checksum = ds.checksum
    return dict(
        warrant.upload_parameters(
            values, data_checksum=checksum, metrics={**(metrics or {}), "dispatch_id": dispatch_id}
        )
    )
