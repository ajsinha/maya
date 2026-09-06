"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What the bytes actually are.

The format of an artifact was a **claim** from beginning to end. The uploader
named it on `POST /artifacts`, the version's kernel named it again, and nothing
ever opened the file. The format is not a label: it decides which runtime loads
the artifact and whether that load path executes code the platform did not
write. `EXECUTES_ON_LOAD` exists precisely because two of these formats run
somebody's code on open — so an artifact declared `onnx` and actually a
TorchScript archive is a request to run code outside the sandbox that isolates
it.

This does not try to identify every file. It answers one question: **do the
first bytes definitively say this is some OTHER known format?** A positive
contradiction is refused; anything it cannot place is left alone, because a
sniffer that guesses produces false refusals and a control people route around
is worse than no control.
"""
from __future__ import annotations

import struct
from typing import Optional

from core.artifacts.common import (GGUF, JSON_MODEL, PFA, PMML, SAFETENSORS,
                                   TARBALL, TORCHSCRIPT)

#: Enough for every signature below. `ustar` sits at offset 257 in a tar header,
#: which is the furthest any of them reaches.
HEAD = 512


def looks_like(head: bytes) -> Optional[str]:
    """The format these bytes announce themselves as, or None if unplaceable.

    None is the honest answer far more often than it looks: ONNX is protobuf and
    protobuf has no magic number, so an ONNX graph is recognised only by the
    shape of its first field and that recognition is deliberately weak.
    """
    if not head:
        return None

    # GGUF states its own name in the first four bytes. The only unambiguous one.
    if head[:4] == b"GGUF":
        return GGUF

    # A ZIP local file header. TorchScript archives are ZIPs; so are a few other
    # things, but none of the other formats here.
    if head[:4] == b"PK\x03\x04":
        return TORCHSCRIPT

    # gzip, or `ustar` in the POSIX tar header at offset 257.
    if head[:2] == b"\x1f\x8b" or head[257:262] == b"ustar":
        return TARBALL

    # safetensors: eight little-endian bytes of header length, then that many
    # bytes of JSON beginning `{`. Checking the length is plausible as well as
    # the brace is what separates it from an arbitrary binary that happens to
    # have a `{` in the ninth byte.
    if len(head) > 8:
        (declared,) = struct.unpack("<Q", head[:8])
        if 0 < declared < 100_000_000 and head[8:9] == b"{":
            return SAFETENSORS

    stripped = head.lstrip()
    if stripped[:1] == b"<":
        # PMML and PFA are both documents; PMML is XML and says so.
        if b"<PMML" in head[:HEAD]:
            return PMML
        return None                      # some other XML: not ours to name
    if stripped[:1] in (b"{", b"["):
        # PFA is a JSON document too, and distinguishing it from a rule set by
        # its keys would be guessing. Both are reported as `json`, and the
        # comparison below treats them as compatible.
        return JSON_MODEL

    # ONNX is deliberately absent, and it is the most instructive entry.
    #
    # It is a protobuf `ModelProto`, and protobuf has no magic number: field 1
    # is a varint, so a serialised graph usually begins `0x08` — and so does an
    # enormous amount of other binary data. Recognising it that way was tried,
    # and it refused its first real upload within a minute: a TorchScript
    # fixture whose bytes happened to start `0x08` was reported as "you declared
    # torchscript and the first bytes are an onnx".
    #
    # That is the failure this module was written to avoid. One byte is not a
    # signature, and a control that refuses correct uploads is one people route
    # around. ONNX is therefore stored on the uploader's word, and the formats
    # with real signatures — including both of the ones that execute code on
    # load — are the ones this can speak about.
    return None


#: Formats that cannot be told apart from their first bytes, and must not be
#: reported as contradicting each other. PFA is JSON; a rule set is JSON; the
#: sniffer sees `{` for both and guessing between them would be inventing
#: certainty.
INTERCHANGEABLE = ({JSON_MODEL, PFA},)


def contradicts(declared: str, sniffed: Optional[str]) -> bool:
    """Whether the bytes definitively say something other than what was declared.

    Unplaceable bytes never contradict. Neither do two formats this cannot
    distinguish. Everything else does, and the caller refuses.
    """
    if sniffed is None or sniffed == declared:
        return False
    return not any({declared, sniffed} <= pair for pair in INTERCHANGEABLE)
