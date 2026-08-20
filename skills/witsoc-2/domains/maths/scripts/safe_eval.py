#!/usr/bin/env python3
"""One evaluation namespace for the frozen `predicate` field.

Four scripts read that field — the bounded tier, the dialectic, and two
backends. When each carried its own namespace they disagreed, and the disagreement
was not cosmetic: a predicate using `all(...)` evaluated fine in one and raised
NameError in another, so the dialectic could refute a claim the bounded tier
could not read. A claim that means different things to two tools is not frozen.

So the namespace lives here, once.

Restricted rather than sandboxed: `__builtins__` is emptied and only the names
below are bound. That is adequate for locally authored claims and is NOT a
security boundary — a claim file arriving from anywhere untrusted needs a real
sandbox, not this.
"""

from __future__ import annotations

import math

NAMESPACE = {
    # arithmetic
    "abs": abs, "min": min, "max": max, "pow": pow, "sum": sum, "divmod": divmod,
    "int": int, "float": float, "round": round,
    # number theory
    "gcd": math.gcd, "sqrt": math.sqrt, "floor": math.floor, "ceil": math.ceil,
    "factorial": math.factorial, "isqrt": math.isqrt, "comb": math.comb,
    # logic and quantifiers — the ones most mathematical predicates need
    "all": all, "any": any,
    # collections
    "len": len, "range": range, "sorted": sorted, "set": set, "tuple": tuple,
    "list": list, "enumerate": enumerate, "zip": zip, "map": map, "filter": filter,
    "reversed": reversed,
}


class PredicateError(Exception):
    """The predicate could not be evaluated. Never silently a False."""


def evaluate(predicate: str, bindings: dict) -> bool:
    """Evaluate a frozen predicate. Raises rather than returning a default.

    An erroring predicate is not a failing one: treating a NameError as
    'the claim is false here' would manufacture counterexamples out of typos.
    """
    # One merged dict passed as GLOBALS, not a globals/locals pair. In
    # eval(expr, globals, locals) a generator expression or comprehension closes
    # over globals only, so `all(n % d for d in range(2, n))` cannot see an `n`
    # bound in locals and dies with NameError. Since comprehensions are how most
    # mathematical predicates are written, that split silently broke the common
    # case while simple predicates kept working.
    scope = {"__builtins__": {}, **NAMESPACE, **bindings}
    try:
        return bool(eval(predicate, scope))
    except Exception as exc:
        raise PredicateError(f"{type(exc).__name__}: {exc}") from exc
