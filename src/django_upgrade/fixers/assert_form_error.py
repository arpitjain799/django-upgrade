"""
Update calls to assertFormError() / assertFormSetError() to pass the
form/formset instead of the response.

https://docs.djangoproject.com/en/4.1/releases/4.1/#tests
"""
from __future__ import annotations

import ast
from functools import partial
from typing import Iterable

from tokenize_rt import UNIMPORTANT_WS, Offset, Token, tokens_to_src

from django_upgrade.ast import ast_start_offset
from django_upgrade.data import Fixer, State, TokenFunc
from django_upgrade.tokens import (
    OP,
    PHYSICAL_NEWLINE,
    consume,
    find_final_token,
    find_first_token,
    reverse_consume,
)

fixer = Fixer(
    __name__,
    min_version=(4, 1),
)


@fixer.register(ast.Call)
def visit_Call(
    state: State,
    node: ast.Call,
    parents: list[ast.AST],
) -> Iterable[tuple[Offset, TokenFunc]]:
    if (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "assertFormError"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
        and len(node.args) in (4, 5)
        and len(node.keywords) == 0
        and isinstance((first_arg := node.args[0]), ast.Name)
        # Heuristically detect response arguments
        # Better would be to backtrack to try spot assignment from call to
        # self.client.*
        and ("response" in first_arg.id or first_arg.id in ("resp", "res", "r"))
        and (
            (
                isinstance((second_arg := node.args[1]), ast.Constant)
                and isinstance(second_arg.value, str)
            )
            or isinstance(second_arg, ast.Name)
        )
    ):
        yield ast_start_offset(first_arg), partial(
            rewrite_args,
            response_arg=first_arg,
            form_arg=second_arg,
        )


def rewrite_args(
    tokens: list[Token],
    i: int,
    *,
    response_arg: ast.Name,
    form_arg: ast.Constant | ast.Name,
) -> None:
    j = find_first_token(tokens, i, node=form_arg)
    k = find_final_token(tokens, j, node=form_arg)
    ftokens = tokens[j:k]
    k = consume(tokens, k, name=OP, src=",")
    k = consume(tokens, k, name=UNIMPORTANT_WS)
    if tokens[k + 1].name == PHYSICAL_NEWLINE:
        j = reverse_consume(tokens, j, name=UNIMPORTANT_WS)
        j = reverse_consume(tokens, j, name=PHYSICAL_NEWLINE)
    del tokens[j : k + 1]
    rtoken = tokens[i]
    tokens[i] = rtoken._replace(
        src=rtoken.src + ".context[" + tokens_to_src(ftokens) + "]",
    )