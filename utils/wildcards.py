import logging
from os import environ
import random
import re
from pathlib import Path
from collections import ChainMap

from .jinja_render import render_jinja
from .parse import parse, pparse

# from .parse import parse

log = logging.getLogger("comfyui-misc-utils")
log.setLevel(logging.INFO)

CLASS_NAME = "MUSimpleWildcard"


def wildcard_prompt_handler(json_data):
    for node_id in json_data["prompt"].keys():
        if json_data["prompt"][node_id]["class_type"] == CLASS_NAME:
            handle_wildcard_node(json_data, node_id)
    return json_data


def handle_wildcard_node(json_data, node_id):
    wildcard_info = json_data.get("extra_data", {}).get("extra_pnginfo", {}).get(CLASS_NAME, {})
    n = json_data["prompt"][node_id]
    if not (n["inputs"].get("use_pnginfo") and node_id in wildcard_info):
        text = MUSimpleWildcard.select(n["inputs"]["text"], n["inputs"]["seed"])

    if text.strip() != n["inputs"]["text"].strip():
        json_data["prompt"][node_id]["inputs"]["use_pnginfo"] = True
        wildcard_info[node_id] = text
        json_data["extra_data"]["extra_pnginfo"][CLASS_NAME] = wildcard_info
    return json_data


def find_and_remove(regexp, text, placeholder=""):
    m = regexp.search(text)
    res = {}
    index = 0

    while m:
        index += 1
        ph = ""
        if placeholder:
            ph = "__" + placeholder + str(index) + "__"
            res[ph] = m.groupdict()
        else:
            res[m["name"]] = m.groupdict()
        s, e = m.span()
        text = text[:s] + ph + text[e:]
        m = regexp.search(text)
    return res, text


def function_definitions(text):
    # $foo($a, $b...) { bodygoeshere \} }
    func_re = re.compile(
        r"def(?P<jinja>j?)\s+(?P<name>\$[a-z]+)\((?P<vars>(\s*\$[a-z]+\s*;)*(\s*\$[a-z]+\s*)?)\)\s*\{(?P<body>.*?)(?<!\\)}",
        flags=re.MULTILINE | re.S,
    )
    found, text = find_and_remove(func_re, text)
    res = {}
    for k, v in found.items():
        res[k] = {}
        vars = [x.strip() for x in v["vars"].split(";") if x.strip()]
        if len(vars) != len(set(vars)):
            log.warning("Ignoring invalid function definition, duplicate vars: %s", vars)
            continue
        res[k]["vars"] = vars
        res[k]["body"] = v["body"].strip()
        res[k]["jinja"] = v["jinja"]
    return res, text


def function_calls(text):
    call_re = re.compile(r"(?P<name>\$[a-z]+)\((?P<args>.*?)(?<!\\)\)")
    res, text = find_and_remove(call_re, text, placeholder="FUNC")
    for k, v in res.items():
        args = [x.strip().replace(r"\;", ";") for x in re.split(r"(?<!\\);", v["args"])]
        res[k]["args"] = args
    return res, text


def variable_definitions(text):
    # name because find_and_remove expects t
    var_re = re.compile(r"var\s+(?P<name>(\s*?\$[a-z]+\s*=[^;\n]*;?)+)")
    defs, text = find_and_remove(var_re, text)
    res = {}
    for k, v in defs.items():
        for d in (x for x in v["name"].strip().split(";") if x.strip()):
            name, value = d.split("=", 1)
            res[name.strip()] = value.strip()
    return res, text


def push_context(ctx):
    for k in ctx.keys():
        ctx[k] = ctx[k].new_child()


def pop_context(ctx):
    for k in ctx.keys():
        ctx[k] = ctx[k].parents


def parent_context(ctx):
    new_ctx = {}
    for k in ctx.keys():
        new_ctx[k] = ctx[k].parents
    return new_ctx


class Nothing:
    def __repr__(self):
        return "Nothing"


RECURSIVE_VARIABLE = Nothing()


def read_preamble():
    curfile = Path(__file__)
    defaults = curfile.parent / "default_functions.txt"
    with open(defaults, "r") as f:
        defs = f.read()
        _, defs = find_and_remove(re.compile("^#.*"), defs)
        return defs


def read_preamble_new(func):
    curfile = Path(__file__)
    defaults = curfile.parent / "default_functions2.txt"
    with open(defaults, "r") as f:
        return func(f.read())


def init_context():
    ctx = {"funcs": ChainMap(), "vars": ChainMap()}
    curfile = Path(__file__)
    defaults = curfile.parent / "default_functions.txt"
    with open(defaults, "r") as f:
        defs = f.read()
        _, defs = find_and_remove(re.compile("^#.*"), defs)
        funcs, _ = function_definitions(defs)
        ctx["funcs"].update(funcs)
    return ctx


def variable_substitution(text, ctx=None, allow_definitions=True, jinja_render=False):
    if ctx is None:
        ctx = init_context()

    funcs, text = function_definitions(text)
    if allow_definitions:
        ctx["funcs"].update(funcs)
    vars, text = variable_definitions(text)
    ctx["vars"].update(vars)
    calls, text = function_calls(text)

    regex = re.compile(r"(?P<name>\$[a-z]+)(?!\()\b")
    vars, text = find_and_remove(regex, text, placeholder="VARIABLE")

    for placeholder, var in vars.items():
        value = ctx["vars"].get(var["name"])
        name = var["name"]
        if value is None:
            raise ValueError(f"Undefined variable {name}")
        if value is RECURSIVE_VARIABLE:
            raise ValueError(f"Recursive variable in definition of {name}")
        push_context(ctx)
        ctx["vars"][name] = RECURSIVE_VARIABLE
        value = variable_substitution(value, ctx, allow_definitions=False)
        pop_context(ctx)
        text = text.replace(placeholder, value)

    for k, v in calls.items():
        f = ctx["funcs"].get(v["name"])
        if not f:
            text = text.replace(k, "")
            log.warning("Function %s not found, ignoring", v["name"])
            continue
        if len(v["args"]) != len(f["vars"]):
            log.warning("Invalid function call to %s, ignoring", v["name"])
            ex = "; ".join(f["vars"])
            log.warning("Call syntax: %s(%s)", v["name"], ex)

            continue

        push_context(ctx)
        for var, val in zip(f["vars"], v["args"]):
            r = variable_substitution(val, parent_context(ctx))
            r = r.replace("\(", "(").replace("\)", ")")
            ctx["vars"][var] = r

        j = f.get("jinja")
        replacement = variable_substitution(f["body"], ctx, jinja_render=j)
        text = text.replace(k, replacement)
        pop_context(ctx)

    if jinja_render:
        t = render_jinja(text)
        if t.strip() != text.strip():
            text = t

    return text.strip()


class MUSimpleWildcard:
    RAND = random.Random()

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text": ("STRING", {"default": "", "multiline": True}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
            },
            "optional": {"use_pnginfo": ("BOOLEAN", {"default": False})},
            "hidden": {
                "extra_pnginfo": "EXTRA_PNGINFO",
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING",)

    CATEGORY = "promptcontrol/tools"
    FUNCTION = "doit"

    @classmethod
    def read_wildcards(cls, name):
        path = environ.get("MU_WILDCARD_BASEDIR", "wildcards")

        f = (Path(path) / Path(name)).with_suffix(".txt")
        try:
            with open(f, "r") as file:
                return [l.strip() for l in file.readlines() if l.strip()]
        except:
            log.warning("Wildcard file not found for %s", name)
            return [name]

    @classmethod
    def select(cls, text, seed):
        cls.RAND.seed(seed)
        wildcard_re = re.compile(r"\$(?P<name>[A-Za-z0-9_/.-]+)(\+(?P<offset>[0-9]+))?\$")
        matches, text = find_and_remove(wildcard_re, text, placeholder="MU_WILDCARD")
        for placeholder, value in matches.items():
            state = None
            ws = cls.read_wildcards(value["name"])
            offset = int(value["offset"] or 0)
            if offset:
                # advance the state once and store it so that the next non-offset result stays deterministic
                w = cls.RAND.choice(ws)
                state = cls.RAND.getstate()
                # advance the state until offset,
                for _ in range(offset):
                    w = cls.RAND.choice(ws)
            else:
                w = cls.RAND.choice(ws)
            text = text.replace(placeholder, w)
            log.info("Selected wildcard %s for %s", w, value["name"])
            if state:
                cls.RAND.setstate(state)

        return text.strip()

    def doit(self, text, seed, extra_pnginfo, unique_id, use_pnginfo=False):
        if use_pnginfo and unique_id in extra_pnginfo.get(CLASS_NAME, {}):
            text = extra_pnginfo[CLASS_NAME][unique_id]
            log.info("MUSimpleWildcard using prompt: %s", text)
        newtext = variable_substitution(text)
        if newtext != text:
            log.info("MUSimpleWildcard result:\n%s", newtext)
        return (newtext,)


try:
    from server import PromptServer

    PromptServer.instance.add_on_prompt_handler(wildcard_prompt_handler)
except ImportError:
    print("Could not install wildcard prompt handler, node won't work")

if __name__ == "__main__":
    _, ctx = read_preamble_new(parse)
    pparse("")
