# Tutorial 9 · Evidence bundles, verified offline

A validator, an auditor or a regulator should not have to trust MAYA's screens.
They should be able to take the evidence away and check it themselves, on a
machine with no route to MAYA. A **bundle** is that evidence: one signed zip
holding a sealed training warrant, its certificate, the data it issued, the
model, its specification, the approved parameters, and a small verifier. In
this tutorial you export one, verify it with the issuer's published key, watch
a tampered bundle and a re-signed forgery fail, and open the bundle as a
read-only, offline MAYA.

## Time to complete

20 minutes.

## Before you start

- [Tutorial 7 · The training warrant and blind scoring](/help/guides/tutorial-07-training-warrant):
  the sealed training warrant `credit/pd_fit_2024`, and **devi**.
- A terminal in a working directory. The tutorial writes `pd_fit_2024.zip`, two
  altered copies and an `unpacked/` folder there.

## What you will learn

- What a bundle contains, and how it is signed.
- Why a signature alone proves integrity, not origin, and how the issuer's key
  closes that gap.
- How to verify a bundle from the command line.
- What a tampered bundle and a re-signed forgery look like to the verifier.
- How to open a bundle as an offline MAYA, and what it will and will not do.
- What the bundled `verify.py` is for.

## Step 1 · Reconnect, and export the bundle

A bundle is exported from a sealed training warrant:

```python
# reconnect, export the bundle, and save it
import os

import maya.sdk as maya

URL = os.environ.get("MAYA_URL", "http://127.0.0.1:8600")
PW = "Tutorial-pass-1"


def key_for(user, password=PW):
    """Sign in and create an API key for that person."""
    token = maya.Client(URL).auth.login(user, password)["token"]
    return maya.Client(URL, token=token).auth.create_api_key("tutorial")["api_key"]


def connect_as(user, password=PW):
    """Sign in, create an API key, and return a client acting as that person."""
    return maya.connect(base_url=URL, api_key=key_for(user, password))


devi = connect_as("devi")
tw = next(w for w in devi.training.list() if w["name"] == "pd_fit_2024")
exported = devi.training.export_bundle(tw["id"])
with open("pd_fit_2024.zip", "wb") as fh:
    fh.write(devi.admin.blob(exported["blob"])["data"])

manifest = exported["manifest"]
print(manifest["warrant"], "| sealed pin:", manifest["sealed_featureset_pin"])
for name in sorted(manifest["files"]):
    print(" ", name)
print(
    "signature:", manifest["signature"]["algorithm"], "| re-executable:", manifest["reexecutable"]
)
```

You should see the warrant and the pin it was drawn on, the eighteen files, and
the signature:

```text
maya://warrant/train/credit/pd_fit_2024@v1 | sealed pin: maya://featureset/credit/training_panel#fit/2024-06-30
  certificate.json
  data/training.parquet
  environment.json
  featureset/definition.json
  featureset/member_pins.json
  featureset/pin.json
  lib/canonical.py
  lib/chunker.py
  model/artifact.py
  model/artifact_report.json
  model/formula_ir.json
  model/model_version.json
  model/parameter_set.json
  model/parameters.json
  model/reference_model.py
  model/spec.tex
  verify.py
  warrant.json
signature: Ed25519 | re-executable: True
```

The manifest lists every file with its SHA-256 hash, and the hash list is
signed with MAYA's Ed25519 key. It also carries the data's content hash,
computed from values by the canonical encoder in `lib/`, and the hash of the
model's output over the data, so the model can be re-run and compared.
`model/artifact.py` is the implementation mona attached in tutorial 6.

## Step 2 · The issuer's key

Anyone can sign a zip. A signature shows the files have not changed *since
signing*, and nothing about *who* signed. So a verifier needs the issuer's
public key, obtained from the issuer, not from the bundle:

```python
# the public half of the key this MAYA signs with
key = devi.custody.signing_key()
print(key["available"], key["algorithm"], "key id of", len(key["key_id"]), "characters")
print("the bundle names the same key:", manifest["signature"]["key_id"] == key["key_id"])

# for the command line: devi's API key, the warrant, and the issuer's key id
os.environ["MAYA_API_KEY"] = key_for("devi")
os.environ["WARRANT_ID"] = tw["id"]
os.environ["ISSUER_KEY"] = key["key_id"]
```

You should see the key, and that the bundle was signed with it:

```text
True Ed25519 key id of 16 characters
the bundle names the same key: True
```

The key id is the first 16 hex characters of the SHA-256 of the public key.
Your key differs from anyone else's; in a firm it would be published where
reviewers can find it, such as a policy page or the validation team's
handbook. On screen it is shown under **Warrants → Verify**
(`/warrants/verify`).

## Step 3 · Verify it from the command line

`python -m maya.cli export verify` checks a bundle with *this installation's*
verifier, never the `verify.py` inside the bundle (a changed bundle could change
that too). With `--key` it also checks who signed it:

```bash
# export the same bundle from the command line, then verify it against the issuer's key
python -m maya.cli export bundle "$WARRANT_ID" --out cli.zip | cut -d, -f1
python -m maya.cli export verify pd_fit_2024.zip --key "$ISSUER_KEY" > report.txt
echo "file hashes checked: $(grep -c 'file hash' report.txt)"
grep -v "file hash" report.txt
```

You should see the export, eighteen file hashes checked, and every other check
passed:

```text
cli.zip: signed bundle
file hashes checked: 18
  [ok] Ed25519 signature over the file list
  [ok] signed by the key you trust
  [ok] data content hash (canonical, value-based)
  [ok] re-execution output hash
verified: True
```

Because the signature is from the trusted key, the verifier also re-ran the
model on the bundle's data and matched the output hash: the parameters in the
bundle really produce the outputs MAYA recorded.

## Step 4 · A tampered bundle, and a re-signed forgery

Two ways to cheat. A **tampered** bundle changes a file and leaves the rest: here
a friendlier intercept in `model/parameters.json`. A **forgery** does the same,
then recomputes every hash and signs the result with a key of its own, so every
integrity check passes. Make both:

```python
# a tampered copy, and a forgery re-hashed and re-signed with a stranger's key
import base64
import hashlib
import io
import json
import zipfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def altered(raw, name, content, resign=False):
    src = zipfile.ZipFile(io.BytesIO(raw))
    files = {n: src.read(n) for n in src.namelist()}
    files[name] = content
    if resign:
        manifest = json.loads(files["manifest.json"])
        manifest["files"][name] = hashlib.sha256(content).hexdigest()
        stranger = Ed25519PrivateKey.generate()
        public = stranger.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        body = json.dumps(manifest["files"], sort_keys=True, separators=(",", ":")).encode()
        manifest["signature"] = {
            "algorithm": "Ed25519",
            "key_id": hashlib.sha256(public).hexdigest()[:16],
            "public_key": base64.b64encode(public).decode(),
            "signature": base64.b64encode(stranger.sign(body)).decode(),
        }
        files["manifest.json"] = json.dumps(manifest).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for n, b in files.items():
            z.writestr(n, b)
    return out.getvalue()


with open("pd_fit_2024.zip", "rb") as fh:
    raw = fh.read()
friendlier = json.dumps(
    {"beta0": -3.5, "beta1": 2.5035, "beta2": 0.9288, "beta3": -0.9123}
).encode()
with open("tampered.zip", "wb") as fh:
    fh.write(altered(raw, "model/parameters.json", friendlier))
with open("forged.zip", "wb") as fh:
    fh.write(altered(raw, "model/parameters.json", friendlier, resign=True))
print("written: tampered.zip, forged.zip")
```

You should see both files written:

```text
written: tampered.zip, forged.zip
```

First the tampered bundle, from the command line, showing only the checks that
did not pass. The verifier exits with an error when a bundle fails, so
`|| true` keeps the shell going:

```bash
# the tampered bundle, against the issuer's key
python -m maya.cli export verify tampered.zip --key "$ISSUER_KEY" | grep -v "\[ok\]" || true
```

You should see the changed file caught by its hash, and the model's outputs no
longer matching:

```text
  [FAIL] file hash model/parameters.json
  [FAIL] re-execution output hash
verified: False
```

Now the forgery. Open it with `maya.offline`, which runs the same checks in
Python, first without a key and then with the issuer's:

```python
# the forgery, opened without a key, then against the issuer's key
forged = maya.offline("forged.zip")
report = forged.verify()
print("no key: verified", report["verified"], "| authentic", report["authentic"])
for check in report["checks"]:
    if check["ok"] is not True:
        print(" ", check["check"], "->", check["ok"])
print("parameters it carries:", forged.parameters()["beta0"])
try:
    maya.offline("forged.zip", key=os.environ["ISSUER_KEY"])
except maya.ValidationFailed as exc:
    print("with the key:", type(exc).__name__, exc)
```

You should see the forgery *pass* without a key, with its friendlier intercept,
and refused against the issuer's key:

```text
no key: verified True | authentic None
  signed by a key you trust -> None
parameters it carries: -3.5
with the key: ValidationFailed The bundle failed verification and is refused: signed by the key you trust
```

Read the first line carefully. Without a key, the forgery is internally
consistent: every hash matches and the signature is valid, so `verified` is
`True`. MAYA says what it could not check (`None`: not checked), and nothing
more. Only the issuer's key exposes the forgery. Always verify with a key:
`--key` on the command line, `key=` in Python.

## Step 5 · Open the bundle as an offline MAYA

`maya.offline` opens a bundle with the same read API a live client has, on a
machine with no network. It verifies the bundle first and refuses one that
fails:

```python
# a read-only, network-free MAYA over the bundle
with maya.offline("pd_fit_2024.zip", key=os.environ["ISSUER_KEY"]) as off:
    report = off.verify()
    print("verified:", report["verified"], "| authentic:", report["authentic"])
    print(off.parameters())
    print("certificate:", off.certificate()["status"])
    table, data_manifest = off.training_data()
    print(table.num_rows, "rows")
    pd_ = off.predict({"utilisation": [0.20, 0.85], "dti": [0.25, 0.47], "bureau": [720, 590]})[
        "pd"
    ]
    print("PDs:", [round(float(p), 4) for p in pd_])
    try:
        off.execution.bundle("pd_live", "dev")
    except maya.MayaError as exc:
        print(type(exc).__name__, exc)
```

You should see the bundle verified and authentic, the approved parameters, the
certificate with its exception, all 1,200 rows of the pin, two PDs, a refusal
for anything a bundle does not hold:

```text
verified: True | authentic: True
{'beta0': -3.0367, 'beta1': 2.5035, 'beta2': 0.9288, 'beta3': -0.9123}
certificate: certified_with_exceptions
1200 rows
PDs: [0.0516, 0.7102]
NotInBundle execution.bundle() needs a live MAYA; this offline bundle holds warrant maya://warrant/train/credit/pd_fit_2024@v1 (its model, parameters and data)
```

`predict` evaluates the signed formula IR with MAYA's own evaluator. It never
imports `reference_model.py` or `artifact.py` from the bundle: opening a bundle
must not run code it carries. The bundle holds every row of the pin, the
escrowed holdout included, because a reviewer must be able to recompute
everything. Export it once the warrant is sealed, when no more parameters can
be uploaded under it.

## Step 6 · The bundled verifier

Inside the bundle is `verify.py`, a verifier that needs only Python, `pyarrow`
and `numpy`, for a reviewer who has no MAYA at all:

```bash
# unpack the bundle and run its own verifier, against the issuer's key
mkdir -p unpacked && cd unpacked
python -c "import zipfile; zipfile.ZipFile('../pd_fit_2024.zip').extractall()"
python verify.py ../pd_fit_2024.zip --key "$ISSUER_KEY" | tail -3
```

You should see the end of its JSON report:

```text
  "authentic": true,
  "verified": true
}
```

A changed bundle could carry a changed `verify.py`, one that always says
`true`. So run the bundled verifier only on a bundle whose origin you have
already checked, or treat its answer as a convenience. `python -m maya.cli
export verify --key`, with a MAYA you installed yourself, is the check to rely
on.

## Next steps

- [Tutorial 10 · A governed change](/help/guides/tutorial-10-governed-change)
  changes a feature under the live scorecard, and rehearses the change first.
- [Warrants](/help/warrants#bundles) describes every file in a bundle.

## If something goes wrong

| What you see | Why | What to do |
|---|---|---|
| `[n/a] signed by a key you trust` | No `--key` was given | Pass the issuer's key id or public key, obtained from the issuer |
| `[FAIL] signed by the key you trust` | The bundle was signed with another key | Treat it as a forgery, or check you have the right issuer's key |
| `[FAIL] file hash ...` | A file changed after signing | The bundle is not the one issued; ask the issuer for it again |
| `available: False` from `signing_key()` | No signing key is configured, so bundles are unsigned | Configure a signing key; unsigned bundles prove nothing about origin |
| `NotInBundle` | The call needs a live MAYA | Use a live client; a bundle holds one warrant and what it rests on |
