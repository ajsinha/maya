# maya-sdk

The Python client for MAYA: every capability of a MAYA server, from a notebook, a
scheduler or a CI job, plus record-and-replay fixtures and offline reproducibility bundles.

This package stands alone. It is what end users install; they never need the MAYA server.
It needs **Python 3.13 or later** (it is tested on 3.13).

```bash
pip install maya-sdk                 # httpx, PyYAML, pyarrow, numpy
pip install "maya-sdk[offline]"      # + cryptography, to check a bundle's signature
pip install "maya-sdk[polars]"       # + polars, for to_polars()
```

```python
import maya.sdk as maya

my = maya.connect(base_url="https://maya.example.com", api_key="maya_prod_…")
print(my.auth.me()["username"])

# or a named profile from ~/.maya/config.yaml
my = maya.connect("prod")
```

```yaml
# ~/.maya/config.yaml
profiles:
  prod:
    base_url: "https://${MAYA_PROD_HOST:maya.example.com}"
    api_key_env: MAYA_PROD_KEY     # the key itself stays in the environment
```

An offline bundle opens, verifies and scores with no route to any server:

```python
off = maya.offline("pd-2026q1.zip")
off.verify()  # file hashes, and the signature with [offline]
off.predict({"x": [1.0, 2.0]})  # from the signed formula, never the bundled code
```

The complete reference is in MAYA's help, under **Python SDK and CLI**.

## Building

From the MAYA repository:

```bash
python -m pip wheel ./sdk --no-deps -w dist
```

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
