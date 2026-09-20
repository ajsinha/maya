"""
Parse mathematics as people write it into the formula IR (§28.6).

Nobody authors the IR by hand. This parser accepts both Python-ish text
(``S*ncdf(d1) - K*exp(-r*T)*ncdf(d2)``) and the LaTeX people already write
(``S N(d_1) - K e^{-rT} N(d_2)``, ``\\frac{a}{b}``, ``\\sqrt{T}``, ``\\sigma``),
including implicit multiplication. Anything it cannot read is refused with
the position named, never guessed.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from maya.core.errors import ValidationFailed

GREEK = {
    "alpha",
    "beta",
    "gamma",
    "delta",
    "epsilon",
    "zeta",
    "eta",
    "theta",
    "iota",
    "kappa",
    "lambda",
    "mu",
    "nu",
    "xi",
    "pi",
    "rho",
    "sigma",
    "tau",
    "upsilon",
    "phi",
    "chi",
    "psi",
    "omega",
    "Gamma",
    "Delta",
    "Theta",
    "Lambda",
    "Xi",
    "Sigma",
    "Upsilon",
    "Omega",
    "Psi",
}
FUNCS = {
    "exp": "exp",
    "log": "log",
    "ln": "log",
    "sqrt": "sqrt",
    "abs": "abs",
    "ncdf": "ncdf",
    "N": "ncdf",
    "Phi": "ncdf",
    "npdf": "npdf",
    "max": "max",
    "min": "min",
    "where": "where",
}
IGNORED_CMDS = {"left", "right", ",", ";", "!", "quad", "displaystyle", "mathrm"}
MUL_CMDS = {"cdot", "times"}
CMP = {
    "<": "lt",
    ">": "gt",
    "<=": "le",
    ">=": "ge",
    "==": "eq",
    "\\le": "le",
    "\\ge": "ge",
    "\\leq": "le",
    "\\geq": "ge",
}

_TOKEN = re.compile(
    r"\s*(?:(?P<num>\d+\.\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?|\d+(?:[eE][+-]?\d+)?)"
    # A command may carry the same subscript a name may: ``\sigma_{atm}`` is how a quant
    # writes an at-the-money volatility, and leaving the subscript stranded made it
    # unparseable while the non-command ``sigma_{atm}`` parsed fine.
    r"|(?P<cmd>\\[A-Za-z]+(?:_(?:\{[A-Za-z0-9]+\}|[A-Za-z0-9]))?|\\[,;!])"
    r"|(?P<name>[A-Za-z][A-Za-z0-9]*(?:_(?:\{[A-Za-z0-9]+\}|[A-Za-z0-9]))?(?:\.[A-Za-z_][A-Za-z0-9_]*)?)"
    r"|(?P<op>\*\*|<=|>=|==|[-+*/^(){},<>=|]))"
)


@dataclass
class Tok:
    kind: str
    text: str
    pos: int
    atomic: bool = False


def _normalise_name(raw: str) -> str:
    return raw.replace("_{", "").replace("}", "").replace("_", "")


def tokenize(text: str) -> list[Tok]:
    """Split text into tokens, refusing any character it does not understand."""
    toks: list[Tok] = []
    pos = 0
    text = text.rstrip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise ValidationFailed(
                f"cannot parse formula at position {pos}: {text[pos : pos + 12]!r}", position=pos
            )
        kind = m.lastgroup or "op"
        val = m.group(kind)
        if kind == "cmd":
            name = val[1:]
            if name in IGNORED_CMDS:
                pos = m.end()
                continue
        atomic = kind == "name" and not val.isalpha()
        if kind == "name":
            val = _normalise_name(val)
        toks.append(Tok(kind, val, m.start(kind), atomic))
        pos = m.end()
    return toks


def _flat(op: str, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    args = (a["args"] if a.get("op") == op else [a]) + [b]
    return {"op": op, "args": args}


class _Parser:
    def __init__(self, text: str, known: set[str]) -> None:
        self.toks = tokenize(text)
        self.i = 0
        self.text = text
        self.known = known
        self.latex_mode = "\\" in text or "{" in text

    def peek(self) -> Tok | None:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self) -> Tok:
        tok = self.peek()
        if tok is None:
            raise ValidationFailed("formula ended unexpectedly", text=self.text)
        self.i += 1
        return tok

    def expect(self, text: str) -> None:
        tok = self.take()
        if tok.text != text:
            raise ValidationFailed(
                f"expected '{text}' at position {tok.pos}, found '{tok.text}'", position=tok.pos
            )

    def parse(self) -> dict[str, Any]:
        node = self.comparison()
        tok = self.peek()
        if tok is not None:
            raise ValidationFailed(
                f"unexpected '{tok.text}' at position {tok.pos}", position=tok.pos
            )
        return node

    def comparison(self) -> dict[str, Any]:
        left = self.additive()
        tok = self.peek()
        if tok and tok.text in CMP:
            self.take()
            return {"op": CMP[tok.text], "args": [left, self.additive()]}
        return left

    def additive(self) -> dict[str, Any]:
        node = self.term()
        while (tok := self.peek()) and tok.text in "+-" and tok.kind == "op":
            self.take()
            rhs = self.term()
            node = (
                _flat("add", node, rhs) if tok.text == "+" else {"op": "sub", "args": [node, rhs]}
            )
        return node

    def _starts_atom(self, tok: Tok | None) -> bool:
        if tok is None:
            return False
        if tok.kind in ("num", "name"):
            return True
        if tok.kind == "cmd":
            return tok.text[1:] not in MUL_CMDS and tok.text not in CMP
        return tok.text in ("(", "{")

    def term(self) -> dict[str, Any]:
        node = self.unary()
        while True:
            tok = self.peek()
            if tok and (tok.text in ("*", "/") or tok.text[1:] in MUL_CMDS and tok.kind == "cmd"):
                self.take()
                rhs = self.unary()
                node = (
                    {"op": "div", "args": [node, rhs]}
                    if tok.text == "/"
                    else _flat("mul", node, rhs)
                )
            elif self._starts_atom(tok):
                node = _flat("mul", node, self.power())
            else:
                return node

    def unary(self) -> dict[str, Any]:
        tok = self.peek()
        if tok and tok.text == "-" and tok.kind == "op":
            self.take()
            inner = self.unary()
            if "const" in inner:
                return {"const": -inner["const"]}
            return {"op": "neg", "args": [inner]}
        if tok and tok.text == "+" and tok.kind == "op":
            self.take()
            return self.unary()
        return self.power()

    def power(self) -> dict[str, Any]:
        tok = self.peek()
        if tok and tok.kind == "name" and tok.text == "e" and "e" not in self.known:
            nxt = self.toks[self.i + 1] if self.i + 1 < len(self.toks) else None
            if nxt and nxt.text in ("^", "**"):
                self.take()
                self.take()
                return {"op": "exp", "args": [self.exponent()]}
        base = self.atom()
        tok = self.peek()
        if tok and tok.text in ("^", "**"):
            self.take()
            return {"op": "pow", "args": [base, self.exponent()]}
        return base

    def exponent(self) -> dict[str, Any]:
        tok = self.peek()
        if tok and tok.text == "{":
            return self.group("{", "}")
        return self.unary()

    def group(self, open_: str, close: str) -> dict[str, Any]:
        self.expect(open_)
        node = self.comparison()
        self.expect(close)
        return node

    def call_args(self) -> list[dict[str, Any]]:
        self.expect("(")
        args = [self.comparison()]
        while (tok := self.peek()) and tok.text == ",":
            self.take()
            args.append(self.comparison())
        self.expect(")")
        return args

    def atom(self) -> dict[str, Any]:
        tok = self.take()
        if tok.kind == "num":
            val = float(tok.text)
            return {
                "const": int(val)
                if val.is_integer() and "." not in tok.text and "e" not in tok.text.lower()
                else val
            }
        if tok.kind == "cmd":
            return self.command(tok)
        if tok.kind == "name":
            return self.name(tok)
        if tok.text == "(":
            node = self.comparison()
            self.expect(")")
            return node
        if tok.text == "{":
            node = self.comparison()
            self.expect("}")
            return node
        if tok.text == "|":
            node = self.additive()
            self.expect("|")
            return {"op": "abs", "args": [node]}
        raise ValidationFailed(f"unexpected '{tok.text}' at position {tok.pos}", position=tok.pos)

    def name(self, tok: Tok) -> dict[str, Any]:
        nxt = self.peek()
        if tok.text in FUNCS and tok.text not in self.known and nxt and nxt.text == "(":
            return {"op": FUNCS[tok.text], "args": self.call_args()}
        if (
            self.latex_mode
            and not tok.atomic
            and len(tok.text) > 1
            and tok.text not in self.known
            and tok.text not in GREEK
        ):
            # LaTeX convention: adjacent single letters multiply (``rT`` is r*T)
            node: dict[str, Any] = {"ref": tok.text[0]}
            for ch in tok.text[1:]:
                node = _flat("mul", node, {"ref": ch})
            return node
        return {"ref": tok.text}

    def command(self, tok: Tok) -> dict[str, Any]:
        name = tok.text[1:]
        if name == "frac":
            num = self.group("{", "}")
            den = self.group("{", "}")
            return {"op": "div", "args": [num, den]}
        if name == "sqrt":
            return {"op": "sqrt", "args": [self.group("{", "}")]}
        if name in ("ln", "log", "exp"):
            op = "log" if name in ("ln", "log") else "exp"
            nxt = self.peek()
            arg = self.group("{", "}") if nxt and nxt.text == "{" else self.power()
            return {"op": op, "args": [arg]}
        if name in ("max", "min"):
            return {"op": name, "args": self.call_args()}
        if name == "Phi":
            return {"op": "ncdf", "args": self.call_args()}
        base, _, subscript = name.partition("_")
        if base in GREEK:
            # ``\sigma_{atm}`` is one symbol, so it is atomic: without that the multi-letter
            # reading below would take 'sigmaatm' for a product of eight single letters.
            return self.name(Tok("name", _normalise_name(name), tok.pos, atomic=bool(subscript)))
        raise ValidationFailed(
            f"unsupported LaTeX command '{tok.text}' at position {tok.pos}", position=tok.pos
        )


def parse_formula(text: str, *, inputs: list[str] | set[str] | None = None) -> dict[str, Any]:
    r"""Parse one expression into an IR node.

    ``inputs`` are normalised the way names in the text are, so a caller may declare
    ``sigma_{atm}`` or ``\sigma_{atm}`` and have it recognised as the one symbol it is."""
    if not text or not text.strip():
        raise ValidationFailed("empty formula")
    return _Parser(text, {_normalise_name(str(i).lstrip("\\")) for i in inputs or ()}).parse()


def _split_statements(text: str) -> list[tuple[str, str]]:
    out = []
    for raw in re.split(r"[\n;]|\\\\", text):
        line = raw.strip().rstrip(",").strip()
        if not line or line.startswith("#") or line.startswith("%"):
            continue
        line = line.replace("&=", "=").replace("&", "")
        m = re.match(r"^([A-Za-z\\][A-Za-z0-9_{}\\]*)\s*=(?!=)\s*(.+)$", line)
        if not m:
            raise ValidationFailed(f"expected 'name = expression', got {line!r}")
        lhs = _normalise_name(m.group(1).lstrip("\\"))
        out.append((lhs, m.group(2)))
    return out


def parse_model(
    text: str, *, roles: dict[str, str] | None = None, output_type: str = "float64"
) -> dict[str, Any]:
    """Parse ``let = ...`` lines then a final ``output = ...`` line into a full IR."""
    from maya.formula.ir import refs_of, validate_ir

    # Role keys are normalised like the names in the text, so a model may declare
    # {"\\sigma_{atm}": "parameter"} and have the subscripted symbol found.
    roles = {_normalise_name(str(k).lstrip("\\")): v for k, v in (roles or {}).items()}
    stmts = _split_statements(text)
    if not stmts:
        raise ValidationFailed("a model needs at least one 'output = expression' line")
    # A name is read as one symbol only if it is known; anything else is a product of
    # single letters, which is the right reading of LaTeX (`xy` is x times y). An
    # intermediate line's own name has to join that set as soon as it is defined, or a
    # model can define `annuity = ...` and then not refer to it: the next line silently
    # reads a·n·n·u·i·t·y and asks for seven features nobody has.
    known = set(roles)
    lets: dict[str, Any] = {}
    for name, expr in stmts[:-1]:
        lets[name] = parse_formula(expr, inputs=known)
        known.add(name)
    out_name, body_text = stmts[-1]
    body = parse_formula(body_text, inputs=known)
    free: set[str] = refs_of(body)
    for node in lets.values():
        free |= refs_of(node)
    free -= set(lets)
    inputs = [{"name": n, "type": "float64", "role": roles.get(n, "feature")} for n in sorted(free)]
    ir: dict[str, Any] = {
        "outputs": [{"name": out_name, "type": output_type}],
        "inputs": inputs,
        "lets": lets,
        "body": body,
    }
    errors = validate_ir(ir)
    if errors:
        raise ValidationFailed("parsed formula is not a valid IR", errors=errors)
    from maya.formula.latex import to_latex

    ir["latex"] = to_latex(ir)
    return ir
