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
    | SINGLES

var.5: "$" "{" NAME "}" | "$" NAME
NAME: /[a-z]+/
argument_spec.10: "(" _WS? argument? (_WS? _SEP _WS? argument)* ")"
argument.10: var _WS? ["=" _WS? expr]
argvalue.10: var _WS? "=" expr | expr
argument_list.10: "(" _WS? argvalue? _WS? ( _SEP _WS? argvalue _WS?)* ")"
function_body.20: "{" (definition | expr)* "}"
_SEP.1: ","
_TERM.10: ";" | NEWLINE
STRING.0: /[^"$(){},;\n]+/
SINGLES.-10: /[,;]/
"""

from collections import ChainMap

from .jinja_render import render_jinja
from jinja2.exceptions import TemplateSyntaxError


def eval(ctx, x):
    try:
        return render_jinja(f"<={x}=>")
    except TemplateSyntaxError as e:
        log.error("MUSimpleWildcard Jinja eval failed: %s\n%s", e, x)
        return ""


def const(x):
    def f():
        return x

    return f


class Context:
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


def showarg(a):
    name, val = a
    if val is None:
        return f"${name}"
    return f"${name}={val}"


def print_context_functions(ctx):
    def p(x):
        print("MUWildcard help:", x)

    p("Functions available:")
    p("- $help(), shows this help")
    p("- $($expr), evaluates $expr as jinja")
    for v, val in ctx.vars.items():
        if isinstance(val, tuple) and "hidden" not in [a[0] for a in val[1]]:
            p(f"- ${v}({','.join(showarg(a) for a in val[1])})")


def debug(ctx, x):
    print("MUWildCard Debug:", x)


MAGIC_FUNCTIONS = {"$": eval, "help": print_context_functions, "debug": debug}


class TestVisitor(Interpreter):
    def __init__(self, ctx=None):
        super().__init__()
        self.ctx = ctx or Context()

    def __default__(self, tree):
        return self.visit_children(tree)

    @v_args(inline=True)
    def function_definition(self, var, argspec, function_body):
        var = varname(var)
        args = self.visit_children(argspec)
        found_defval = None
        args = []
        with self.ctx as c:
            for arg in argspec.children:
                x, defval = self.visit(arg)
                if found_defval and not defval:
                    raise TypeError(f"Invalid function definition for {var}, must define default for {x}")
                found_defval = defval
                args.append((x, defval))
                # Allow $fn($a=1, $b=$a)
                if x not in c.vars:
                    c.set(x, defval)
        with self.ctx as locals:
            res = (locals, args, function_body)
        self.ctx.set(var, res)
        return ""

    @v_args(inline=True)
    def argument(self, var, defval):
        n = varname(var)
        if defval:
            defval = prompt(self.visit(defval)).strip()
        return n, defval

    @v_args(inline=True)
    def argument_list(self, *args):
        positional = []
        named = {}
        for arg in args:
            name, value = self.visit(arg)
            if not name and named:
                raise TypeError("Can't have positional arguments after named arguments!")
            if name:
                named[name] = value
            else:
                positional.append(value)
        return positional, named

    @v_args(inline=True)
    def argvalue(self, var_or_expr, expr=None):
        if expr:
            return (varname(var_or_expr), prompt(self.visit(expr)))
        return (None, prompt(self.visit(var_or_expr)))

    @v_args(inline=True)
    def quoted(self, value):
        value = value.replace('\\"', '"')
        if value == '""':
            return '"'
        return value[1:][:-1]

    @v_args(inline=True)
    def function_call(self, var, arglist):
        var = varname(var)
        positional, named = self.visit(arglist)

        if var in MAGIC_FUNCTIONS:
            return MAGIC_FUNCTIONS[var](self.ctx, *positional, **named)

        try:
            locals, params, function_body = self.ctx.get(var)
        except TypeError:
            print_context_functions(self.ctx)
            raise TypeError(f"${var} is not a function")
        with self.ctx as c:
            if len(positional) > len(params):
                raise TypeError(f"Invalid number of arguments to function ${var}({','.join(f'${a}' for a in params)})")

            # Fill in with defaults
            positional = positional + [p[1] for p in params][len(positional) :]

            for k, v in locals.vars.items():
                c.set(k, v)

            set_args = {}

            for a, v in zip(params, positional):
                set_args[a[0]] = v

            for k, v in named.items():
                set_args[k] = v

            for p in params:
                if p[0] not in set_args or set_args[p[0]] is None:
                    raise TypeError(
                        f"Missing argument ${p[0]} to function ${var}({','.join(showarg(a) for a in params)})"
                    )
                c.set(p[0], const(set_args[p[0]]))

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
        return ""

    def start(self, tree):
        result = self.visit_children(tree)
        final_prompt = "".join(flatten(result))
        return final_prompt, self.ctx


parser = lark.Lark(definition, parser="earley")


def parse(x, ctx=None):
    try:
        r = TestVisitor(ctx).visit(parser.parse(x))
        if r is None:
            return x, None
        return r
    except Exception as e:
        log.error("Parse error: %s", e)
        return x, None


def debug_parse(text, p="earley", **kwargs):
    x = lark.Lark(definition, parser=p, debug=True)
    return x.parse(text)


def pparse(text, p="earley", **kwargs):
    print(debug_parse(text, p, **kwargs).pretty())
