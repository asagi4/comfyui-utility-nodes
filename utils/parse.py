import lark
import logging

logging.basicConfig(level=logging.DEBUG)
from lark.visitors import Interpreter, v_args

log = logging.getLogger("MUWildcard")

definition = r"""
%import common.NEWLINE
%import common.ESCAPED_STRING
%import common.WS_INLINE -> WS
quoted: ESCAPED_STRING
_WS: WS
start: (definition | expr )*
expr.0: prompt+
    | NEWLINE

definition.10: var _WS? "=" _WS? expr? _TERM?     -> var_definition
         | var argument_spec _WS? "=" _WS? function_body -> function_definition

!block: "(" expr? ")"
        | "{" expr? "}"

function_call.10: var argument_list | /\$/ argument_list
!prompt.0: quoted
    | function_call
    | var
    | block
    | STRING
    | WS+ -> ws
    | /[,;"]/

var.5: "$" "{" NAME "}" | "$" NAME
NAME: /[a-z]+/
argument_spec.10: "(" _WS? var? (_WS? _SEP _WS? var)* ")"
argument_list.10: "(" _WS? expr? (_WS? _SEP expr _WS?)*")"
function_body.20: "{" expr* "}"
_SEP.1: ","
_TERM.10: ";" | NEWLINE
STRING.0: /[^"$(){},;\n]+/
"""

from collections import ChainMap

from .jinja_render import render_jinja


def eval(x):
    return render_jinja(f"<={x}=>")


MAGIC_FUNCTIONS = {"$": eval}


def const(x):
    def f():
        return x

    return f


class Context:
    POISON = object()

    def __init__(self):
        self.vars = ChainMap()

    def __enter__(self):
        self.vars = self.vars.new_child()
        return self

    def __exit__(self, *exc):
        self.vars = self.vars.parents
        return False

    def set(self, name, value):
        self.vars[str(name)] = value

    def get(self, name, default=None):
        return self.vars.get(str(name), default)

    def poison(self, name):
        self.vars[str(name)] = self.POISON


def varname(x):
    if str(x) == "$":
        return str(x)
    return x.children[0].value


def flatten(seq):
    if isinstance(seq, str):
        yield seq
    elif seq is None:
        yield ""
    else:
        for x in seq:
            yield from flatten(x)


def prompt(seq):
    return "".join(flatten(seq))


def print_context_functions(ctx):
    for v, val in ctx.vars.items():
        print(val)
        if isinstance(tuple, val):
            print("function", v, val)


class TestVisitor(Interpreter):
    def __init__(self, ctx=None):
        super().__init__()
        self.ctx = ctx or Context()

    def __default__(self, tree):
        return self.visit_children(tree)

    @v_args(inline=True)
    def function_definition(self, var, argspec, function_body):
        var = varname(var)
        args = [varname(a) for a in argspec.children]
        with self.ctx as locals:
            res = (locals, args, function_body)
        self.ctx.set(var, res)

    @v_args(inline=True)
    def argument_list(self, *args):
        return [prompt(self.visit_children(x)) for x in args]

    @v_args(inline=True)
    def quoted(self, value):
        print("Quoted: '", value, "'")
        value = value.replace('\\"', '"')
        return value[1:][:-1]

    @v_args(inline=True)
    def function_call(self, var, arglist):
        var = varname(var)
        args = self.visit(arglist)

        if var in MAGIC_FUNCTIONS:
            return MAGIC_FUNCTIONS[var](*args)

        try:
            locals, params, function_body = self.ctx.get(var)
        except TypeError:
            raise TypeError(f"${var} is not a function")
            print_context_functions(self.ctx)
        with self.ctx as c:
            if len(params) != len(args):
                raise TypeError(f"Invalid number of arguments to function ${var}({','.join(f'${a}' for a in params)})")

            for k, v in locals.vars.items():
                c.set(k, v)

            for a, v in zip(params, args):
                c.set(a, const(v))

            return prompt(self.visit(function_body)).strip()

    @v_args(inline=True)
    def var(self, name):
        v = self.ctx.get(name)
        if isinstance(v, tuple):
            raise TypeError(f"${name} is a function, can't use as a variable")
        if v:
            return v()
        else:
            raise TypeError(f"${name} is undefined")

    @v_args(inline=True)
    def var_definition(self, var, definition=""):
        name = var.children[0].value

        if definition:

            def resolve():
                with self.ctx as c:
                    v = self.visit(definition)
                    c.set(name, const(v))
                    return v

        else:
            resolve = const("")

        self.ctx.set(name, resolve)

    def start(self, tree):
        result = self.visit_children(tree)
        final_prompt = "".join(flatten(result))
        return final_prompt, self.ctx


def parse(x, ctx=None):
    try:
        return TestVisitor(ctx).visit(raw_parse(x))
    except Exception as e:
        log.error("Error: %s", e)
        raise


def raw_parse(text, p="earley", **kwargs):
    x = lark.Lark(definition, parser=p, debug=True, **kwargs)
    return x.parse(text)


def pparse(text, p="earley", **kwargs):
    print(raw_parse(text, p, **kwargs).pretty())