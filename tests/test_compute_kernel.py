"""
The compute-kernel wizard (§8.1, §28.6): written mathematics in, the typed IR and one
self-contained Python function out.

Two properties are worth a test of their own and are checked here by construction rather
than by reading the source. The kernel is *one* function — its imports and its helpers are
nested inside it, so nothing it defines can collide with whatever module it is pasted into.
And it computes what the IR says: the kernel and the reference module are generated from the
same tree by the same rules, so a divergence between them is a bug in one of the generators,
and the only way to know is to run both.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import re
import ast

import numpy as np
import pytest

from maya.core.errors import ValidationFailed
from maya.formula.codegen import compile_reference, to_python_kernel
from maya.formula.parse import parse_model
from tests.conftest import PASSWORD
from tests.test_web_journeys import Browser, site  # noqa: F401 - the shared estate fixture

BLACK_SCHOLES = r"""
d_1 = (\log(S/K) + (r + \sigma^2/2)T) / (\sigma\sqrt{T})
d_2 = d_1 - \sigma\sqrt{T}
price = S\,ncdf(d_1) - K e^{-rT} ncdf(d_2)
"""
BS_ROLES = {"sigma": "parameter", "r": "parameter"}


def run(source: str, name: str, X: dict, params: dict) -> dict:
    ns: dict = {}
    exec(compile(source, "<kernel>", "exec"), ns)  # noqa: S102  # nosec B102 - the code under test
    return ns[name](X, params)


def test_the_kernel_is_one_function_and_nothing_else():
    ir = parse_model(BLACK_SCHOLES, roles=BS_ROLES)
    source = to_python_kernel(ir, "black_scholes_call")
    module = ast.parse(source)
    assert [type(n).__name__ for n in module.body] == ["FunctionDef"]
    assert module.body[0].name == "black_scholes_call"
    # Everything the function needs is inside it: the imports are statements of its body,
    # not of the module, which is what lets the kernel be pasted anywhere at all.
    kinds = {type(n).__name__ for n in module.body[0].body}
    assert "Import" in kinds
    assert "FunctionDef" in kinds  # the normal CDF helper this formula needs


def test_a_formula_without_the_normal_distribution_does_not_import_math():
    ir = parse_model("y = a x + b", roles={"a": "parameter", "b": "parameter"})
    source = to_python_kernel(ir)
    assert "import math" not in source
    assert "import numpy as np" in source
    assert run(source, "compute", {"x": [2.0]}, {"a": 3.0, "b": 1.0})["y"] == pytest.approx([7.0])


def test_the_kernel_and_the_reference_module_compute_the_same_thing():
    ir = parse_model(BLACK_SCHOLES, roles=BS_ROLES)
    X = {"S": [100.0, 90.0, 120.0], "K": [100.0, 100.0, 100.0], "T": [1.0, 0.5, 2.0]}
    params = {"sigma": 0.2, "r": 0.03}
    kernel = run(to_python_kernel(ir), "compute", X, params)["price"]
    reference = compile_reference(ir)(X, params)["price"]
    assert np.allclose(kernel, reference)
    # And the value itself, so that a change agreeing with itself is still caught: an
    # at-the-money one-year call at 20% vol and 3% is worth a shade over nine.
    assert kernel[0] == pytest.approx(9.4134, abs=5e-4)


def test_a_kernel_is_refused_for_a_model_that_has_no_closed_form():
    with pytest.raises(ValidationFailed):
        to_python_kernel({"outputs": [{"name": "pd", "type": "float64"}], "inputs": [], "lets": {}})


def test_the_function_name_is_made_safe_rather_than_trusted():
    ir = parse_model("y = a x", roles={"a": "parameter"})
    assert ast.parse(to_python_kernel(ir, "2 weird-name")).body[0].name.isidentifier()


def test_the_service_translates_without_creating_anything(site):  # noqa: F811
    """The wizard's own call: nothing named, nothing stored, everything checked."""
    w, _ = site
    before = len(w.p.models.list(w.mona))
    out = w.p.models.kernel(w.mona, text=BLACK_SCHOLES, roles=BS_ROLES, name="bs")
    assert out["output"] == {"name": "price", "type": "float64"}
    assert out["lets"] == ["d1", "d2"]
    assert {i["name"]: i["role"] for i in out["inputs"]} == {
        "K": "feature",
        "S": "feature",
        "T": "feature",
        "r": "parameter",
        "sigma": "parameter",
    }
    assert out["latex"].startswith(r"\begin{aligned}")
    assert ast.parse(out["python"]).body[0].name == "bs"
    assert len(out["ir_hash"]) == 64
    # The translation is a read of nothing: no model appeared.
    assert len(w.p.models.list(w.mona)) == before


def test_a_formula_maya_cannot_read_is_refused_with_its_reason(site):  # noqa: F811
    w, _ = site
    with pytest.raises(ValidationFailed) as exc:
        w.p.models.kernel(w.mona, text="price = S*(")
    assert str(exc.value)


def test_the_wizard_page_translates_and_carries_its_work_to_the_designer(site):  # noqa: F811
    _, app = site
    mona = Browser(app, "mona", PASSWORD)
    page = mona.get("/models/kernel").text
    assert "Design your compute kernel" in page
    assert "Black" in page  # the worked examples are offered

    token = mona.csrf("/models/kernel")
    r = mona.c.post(
        "/ui/kernel",
        data={"formula": BLACK_SCHOLES, "roles": "sigma: parameter\nr: parameter", "name": "bs"},
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 200, r.text[:300]
    out = r.json()
    assert out["output"]["name"] == "price"
    assert ast.parse(out["python"]).body[0].name == "bs"

    # The designer accepts the wizard's work through the query string and shows it already
    # filled in, so the next click is "Create model" and not a retype.
    designer = mona.get("/models/new?formula=y+%3D+a+x&roles=a%3A+parameter").text
    assert "y = a x" in designer
    assert "a: parameter" in designer

    # And a formula MAYA cannot read comes back as a readable refusal, not a stack trace.
    bad = mona.c.post(
        "/ui/kernel",
        data={"formula": "price = S*(", "roles": "", "name": "compute"},
        headers={"X-CSRF-Token": mona.csrf("/models/kernel")},
    )
    assert bad.status_code >= 400
    assert bad.json()["error"]


def _mona(app):
    """Mona, whichever password an earlier test left her with (the estate forces a change)."""
    try:
        return Browser(app, "mona", PASSWORD)
    except AssertionError:
        return Browser(app, "mona", PASSWORD + "-2")


PD_LOGIT = """def pd_logit(income, utilisation, params):
    z = params["b0"] + params["b1"] * log(income) + params["b2"] * utilisation
    return 1 / (1 + exp(-z))
"""


def test_the_wizard_lifts_a_python_function_and_carries_it_to_the_designer(site):  # noqa: F811
    """A Python function goes through the same lifter a model definition uses; the names
    written ``params[...]`` become parameters, the rest features."""
    _, app = site
    mona = _mona(app)
    r = mona.c.post(
        "/ui/kernel",
        data={"python_source": PD_LOGIT, "name": "pd"},
        headers={"X-CSRF-Token": mona.csrf("/models/kernel")},
    )
    assert r.status_code == 200, r.text[:300]
    roles = {i["name"]: i["role"] for i in r.json()["inputs"]}
    assert roles == {
        "b0": "parameter",
        "b1": "parameter",
        "b2": "parameter",
        "income": "feature",
        "utilisation": "feature",
    }
    assert ast.parse(r.json()["python"]).body[0].name == "pd"
    loop = mona.c.post(
        "/ui/kernel",
        data={"python_source": "def f(x):\n    for i in x:\n        pass\n    return x\n"},
        headers={"X-CSRF-Token": mona.csrf("/models/kernel")},
    )
    assert loop.status_code >= 400 and "line" in loop.json()["error"]
    designer = mona.get("/models/new?python=def+f%28x%29%3A%0A++++return+2*x").text
    assert 'value="python" selected' in designer and "return 2*x" in designer


def test_every_authoring_screen_says_what_it_needs(site):  # noqa: F811
    _, app = site
    mona = _mona(app)
    for path, heading in (
        ("/models/kernel", "What the Python function needs"),
        ("/models/new", "What the definition needs"),
        ("/workbench/features/new", "What a feature needs"),
        ("/workbench/featuresets/new", "What a feature set needs"),
        ("/warrants/training/new", "What a training warrant needs"),
        ("/warrants/execution/new", "What an execution warrant needs"),
    ):
        page = mona.get(path).text
        assert heading in page, path
        assert re.search(r"/help/designers#[a-z0-9-]+\"", page), path
    guide = mona.get("/help/designers").text
    for anchor in (
        "the-python-artifact",
        "features",
        "feature-sets",
        "training-warrants",
        "execution-warrants",
    ):
        assert f'id="{anchor}"' in guide


def test_every_generated_implementation_is_one_function(site):  # noqa: F811
    """The rule is not the wizard's: it is the platform's.

    Whatever MAYA generates from an IR — the wizard's kernel, the reference implementation
    on a model's Code tab, the file in a release bundle — is one portable object. A module
    that defines `_ncdf` and `_erfc` beside `predict` cannot be pasted into a codebase that
    has its own; a function that carries them inside it can go anywhere."""
    from maya.formula.codegen import to_python, to_python_composite

    closed = parse_model(BLACK_SCHOLES, roles=BS_ROLES)
    module = ast.parse(to_python(closed))
    assert [type(n).__name__ for n in module.body] == ["FunctionDef"]
    assert module.body[0].name == "predict"

    base = parse_model("y = a x", roles={"a": "parameter"})
    skew = parse_model("y = ncdf(b x)", roles={"b": "parameter"})
    composite = {
        "outputs": [{"name": "p", "type": "float64"}],
        "inputs": [],
        "composite": {
            "kind": "ensemble",
            "members": [{"alias": "base", "ref": "m1"}, {"alias": "skew", "ref": "m2"}],
            "combine": {"op": "add", "args": [{"ref": "base.y"}, {"ref": "skew.y"}]},
        },
    }
    source = to_python_composite(composite, {"base": base, "skew": skew})
    tree = ast.parse(source)
    assert [type(n).__name__ for n in tree.body] == ["FunctionDef"]
    # The members are functions of `predict`, not of the module beside it.
    inner = {n.name for n in tree.body[0].body if isinstance(n, ast.FunctionDef)}
    assert {"_member_base", "_member_skew", "_member_params", "_ncdf"} <= inner
    ns: dict = {}
    exec(compile(source, "<composite>", "exec"), ns)  # noqa: S102  # nosec B102 - the code under test
    got = ns["predict"]({"x": [1.0, 2.0]}, {"base.a": 2.0, "skew.b": 0.5})["p"]
    assert got == pytest.approx([2.6915, 4.8413], abs=5e-4)


def test_the_front_door_is_the_landing_page_until_somebody_signs_in(site):  # noqa: F811
    """A visitor is told what MAYA is; a password box answers a question nobody asked yet."""
    _, app = site
    from starlette.testclient import TestClient

    anon = TestClient(app)
    front = anon.get("/")
    assert front.status_code == 200
    assert "MAYA keeps the answer" in front.text
    assert 'href="/login"' in front.text
    # Help and About have to be readable by somebody with no account at all, or the
    # landing page points at two doors that are locked.
    assert anon.get("/help").status_code == 200
    assert anon.get("/about").status_code == 200

    signed_in = Browser(app, "devi", PASSWORD)
    assert "MAYA keeps the answer" not in signed_in.get("/").text  # the dashboard, not the pitch

    out = signed_in.c.post(
        "/logout",
        data={"csrf_token": signed_in.csrf("/")},
        follow_redirects=False,
    )
    assert out.status_code == 303
    assert out.headers["location"] == "/?signed_out=1"  # the landing page, with a note
    assert "MAYA keeps the answer" in signed_in.c.get(out.headers["location"]).text
