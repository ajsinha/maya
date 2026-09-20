"""The typesetting seam: the draft renderer is labelled, watermarked on every page, and
says so; and a true build runs under the §17.1 caps, with no network and no inherited
environment, recording what it was allowed to do."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from maya.core.typeset import (
    WATERMARK,
    Caps,
    build_env,
    detect,
    parse_blocks,
    pdf_text,
    render_pdf,
)
from maya.formula.parse import parse_model
from maya.formula.specdoc import default_document, expand_macros


def _long_doc() -> str:
    ir = parse_model("price = S*a", roles={"a": "parameter"})
    doc = expand_macros(default_document("toy_model", ir), ir)
    filler = " ".join(["The limitation paragraph repeats to force pagination."] * 40)
    return doc.replace(
        r"\section{Scope and Limitations}",
        r"\section{Scope and Limitations}" + "\n" + "\n\n".join([filler] * 6),
    )


def test_draft_render_is_labelled_and_watermarked_on_every_page() -> None:
    pdf, meta = render_pdf(_long_doc(), force_draft=True)
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    assert meta["draft_render"] is True and meta["backend"] == "draft"
    pages = pdf_text(pdf).split("\f")
    assert len(pages) >= 2
    for page in pages:
        assert WATERMARK in page
    text = pdf_text(pdf)
    assert "Scope and Limitations" in text and "Change Log" in text and "toy_model" in text
    assert "price = S" in text  # the formula, rendered as its LaTeX source


def test_detect_reports_backend() -> None:
    info = detect()
    assert info["backend"] in ("tectonic", "draft") and info["detail"]


def test_parse_blocks_structure() -> None:
    blocks = parse_blocks(
        r"\title{T}\begin{document}\section{A} hello \[x^2\] \begin{itemize}\item one\end{itemize}\end{document}"
    )
    kinds = [k for k, _ in blocks]
    assert kinds == ["title", "section", "para", "math", "item"]


needs_tectonic = __import__("pytest").mark.skipif(
    detect()["backend"] != "tectonic", reason="Tectonic is not installed here"
)


@needs_tectonic
def test_a_true_build_is_a_real_pdf_without_the_draft_watermark() -> None:
    pdf, meta = render_pdf(_long_doc())
    assert meta == {**meta, "draft_render": False, "backend": "tectonic"}
    assert pdf.startswith(b"%PDF-") and WATERMARK.encode() not in pdf
    assert len(pdf) > 5000


@needs_tectonic
def test_broken_latex_fails_with_the_tex_log() -> None:
    import pytest

    from maya.core.errors import ValidationFailed

    with pytest.raises(ValidationFailed, match="LaTeX build failed") as info:
        render_pdf("\\documentclass{article}\\begin{document}\\undefinedmacro\\end{document}")
    assert "undefinedmacro" in info.value.context["log"] or "Undefined" in info.value.context["log"]


@needs_tectonic
def test_approval_accepts_a_true_build_when_one_is_required() -> None:
    from tests.conftest import World, build_platform

    platform = build_platform(["--typeset.require_true_build=true"])
    try:
        w = World(platform)
        platform.access.create_namespace(w.admin, name="tx")
        platform.models.create(
            w.mona, namespace="tx", name="lin", formula="y = a*x", roles={"a": "parameter"}
        )
        out = platform.models.render_spec(w.mona, "tx/lin", 1)
        assert out["draft_render"] is False and out["backend"] == "tectonic"
        version = platform.models.get(w.mona, "tx/lin")["versions"][0]
        ok, why = platform.models.check_true_build(None, {"row": version})
        assert ok and why == "PDF is a true LaTeX build"
    finally:
        platform.shutdown()


@needs_tectonic
def test_a_fragment_is_wrapped_in_the_standard_preamble() -> None:
    from maya.core.typeset import as_document

    pdf, meta = render_pdf("\\section{Purpose}\nThe model prices $x^2$.")
    assert meta["draft_render"] is False and pdf.startswith(b"%PDF-")
    whole = "\\documentclass{article}\\begin{document}x\\end{document}"
    assert as_document(whole) == whole


# -- §17.1: capped, no network, and honest about both ----------------------------------
def test_the_build_environment_carries_nothing_of_mayas_own(monkeypatch) -> None:
    """A TeX build has no business with MAYA's credentials, and a proxy variable is the one
    way a cached-only build could still open a socket."""
    for name, value in {
        "HTTPS_PROXY": "http://proxy.internal:3128",
        "http_proxy": "http://proxy.internal:3128",
        "AWS_SECRET_ACCESS_KEY": "not-for-tex",
        "MAYA_ADMIN_PASSWORD": "not-for-tex",
        "TECTONIC_CACHE_DIR": "/var/cache/tectonic",
    }.items():
        monkeypatch.setenv(name, value)
    env = build_env()
    assert "PATH" in env, "the engine still has to be findable"
    assert env["TECTONIC_CACHE_DIR"] == "/var/cache/tectonic", "a warmed bundle stays reachable"
    for leaked in ("HTTPS_PROXY", "http_proxy", "AWS_SECRET_ACCESS_KEY", "MAYA_ADMIN_PASSWORD"):
        assert leaked not in env, leaked


def test_a_build_is_asked_for_only_cached_and_untrusted_under_its_jail(monkeypatch) -> None:
    """The two flags that keep a build offline and unable to shell out, and the jail the
    caller hands in — asserted on the argv, because that is where they are or are not."""
    seen: dict[str, object] = {}

    def fake_run(argv, **kw):
        seen["argv"] = list(argv)
        seen["env"] = kw["env"]
        seen["timeout"] = kw["timeout"]
        raise RuntimeError("stop here: the argv is what this test is about")

    monkeypatch.setattr("maya.core.typeset.detect", lambda: {"backend": "tectonic", "detail": ""})
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError):
        render_pdf("\\section{A}\nx", caps=Caps(seconds=7), jail=("/usr/bin/bwrap", "--"))
    argv = seen["argv"]
    assert argv[:2] == ["/usr/bin/bwrap", "--"], "the jail wraps the engine"
    assert "--only-cached" in argv and "--untrusted" in argv
    assert seen["timeout"] == 7
    assert "PATH" in seen["env"] and "HTTPS_PROXY" not in seen["env"]


def test_a_host_that_can_compile_nothing_degrades_to_the_draft_renderer(monkeypatch) -> None:
    """§17.1's own degradation rule. A build may not fetch its support bundle, so a host
    nobody has warmed produces a watermarked draft — refused wherever a PDF is evidence —
    rather than an error that reads like a broken document.

    The fork is decided by whether TeX left a log, not by matching the engine's wording:
    here it leaves none, because it never got as far as running."""

    def never_ran(argv, **kw):
        return subprocess.CompletedProcess(
            argv,
            1,
            stdout="note: using only cached resource files\n",
            stderr="error: cannot open the bundle\n",
        )

    monkeypatch.setattr("maya.core.typeset.detect", lambda: {"backend": "tectonic", "detail": ""})
    monkeypatch.setattr(subprocess, "run", never_ran)
    pdf, meta = render_pdf(_long_doc())
    assert meta["draft_render"] is True and meta["backend"] == "draft"
    assert "bundle fetch" in meta["log"], "the operator is told how to warm it"
    assert "cannot open the bundle" in meta["log"], "and what the engine actually said"
    assert WATERMARK in pdf_text(pdf)


def test_a_broken_document_is_still_refused_not_quietly_drafted(monkeypatch) -> None:
    """The other side of the same fork: TeX ran and left its log, so the document is what
    failed. That is the author's problem and is named, not turned into a draft that looks
    like an outage."""
    from maya.core.errors import ValidationFailed

    def compiled_and_failed(argv, **kw):
        (Path(kw["cwd"]) / "doc.log").write_text("! Undefined control sequence.\n")
        return subprocess.CompletedProcess(
            argv, 1, stdout="", stderr="error: Undefined control sequence \\nope\n"
        )

    monkeypatch.setattr("maya.core.typeset.detect", lambda: {"backend": "tectonic", "detail": ""})
    monkeypatch.setattr(subprocess, "run", compiled_and_failed)
    with pytest.raises(ValidationFailed, match="LaTeX build failed") as info:
        render_pdf("\\section{A}\n\\nope")
    assert "Undefined control sequence" in info.value.message


@needs_tectonic
def test_a_true_build_records_the_caps_it_ran_under() -> None:
    """A model version says what its build was allowed to do, not what today's
    configuration says. On POSIX that includes the rlimits that were really set; on
    Windows the list is empty, which is the honest answer rather than an implied cap."""
    _, meta = render_pdf("\\section{A}\nThe model prices $x^2$.", caps=Caps(memory_mb=1536))
    caps = meta["caps"]
    assert caps["memory_mb"] == 1536 and caps["seconds"] == 120 and caps["output_mb"] == 64
    assert {"RLIMIT_AS", "RLIMIT_CPU", "RLIMIT_FSIZE"} <= set(caps["rlimits"])
    assert caps["network"] in ("namespace (no interfaces)", "--only-cached, fixed env")


@needs_tectonic
def test_a_runaway_build_is_stopped_by_its_time_cap() -> None:
    """The cap is a cap, not a suggestion: an endless macro ends, and the refusal names the
    limit rather than reporting a mysterious failure."""
    from maya.core.errors import ValidationFailed

    endless = "\\documentclass{article}\\begin{document}\\def\\spin{\\spin}\\spin\\end{document}"
    with pytest.raises(ValidationFailed) as info:
        render_pdf(endless, caps=Caps(seconds=5))
    assert "cap" in info.value.message


def test_a_models_pdf_records_its_caps_on_the_version() -> None:
    """The caps travel with the evidence: a reviewer reading a sealed version next year
    sees the limits and the network mode that PDF was built under."""
    from tests.conftest import World, build_platform

    platform = build_platform(["--typeset.memory_mb=1024", "--typeset.output_mb=16"])
    try:
        w = World(platform)
        platform.access.create_namespace(w.admin, name="tcaps")
        platform.models.create(
            w.mona, namespace="tcaps", name="lin", formula="y = a*x", roles={"a": "parameter"}
        )
        platform.models.render_spec(w.mona, "tcaps/lin", 1)
        version = platform.models.get(w.mona, "tcaps/lin")["versions"][0]
        caps = version["spec_state"]["caps"]
        assert caps["memory_mb"] == 1024 and caps["output_mb"] == 16
        assert "network" in caps and "rlimits" in caps
    finally:
        platform.shutdown()
