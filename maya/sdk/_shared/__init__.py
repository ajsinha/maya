"""
Code the SDK and the server share, kept in the SDK because the SDK stands alone.

End users install the SDK without the rest of MAYA, yet a few things must behave identically
on both sides: the error hierarchy (so a refusal raised by the server is the same class the
client raises), canonical content hashing (so a pin's hash matches wherever it is computed),
archive reading (so a bundle is opened the same way) and the formula IR and its evaluator (so
a bundle scores offline exactly as MAYA scores it). They live here, once. The server's old
names -- ``maya.core.errors``, ``maya.core.canonical``, ``maya.core.archives``,
``maya.formula.ir``, ``maya.formula.evaluate`` -- are aliases of these modules, not copies.

Nothing in this package may import from MAYA outside ``maya.sdk``;
``tests/test_sdk_standalone.py`` imports and exercises the SDK with the rest blocked.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
