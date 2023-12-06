import logging
import math
import re
from datetime import datetime
from jinja2 import Environment
from jinja2.exceptions import TemplateSyntaxError

log = logging.getLogger("comfyui-misc-utils")


def steps(start, end=None, step=0.1):
    if end is None:
        end = start
        start = step
    while start <= end:
        yield start
        start += step
        start = round(start, 2)


def template(template, sequence, *funcs):
    funcs = [lambda x: x] + list(*funcs)
    res = []
    for item in sequence:
        x = template
        for i, f in enumerate(funcs):
            x = x.replace(f"${i}", str(f(i)))
        res.append(x)

    return "".join(res)


def clamp(a, b, c):
    return max(a, min(b, c))


JINJA_ENV = {
    "pi": math.pi,
    "floor": math.floor,
    "ceil": math.ceil,
    "min": min,
    "max": max,
    "abs": abs,
    "clamp": clamp,
    "round": round,
    "template": template,
    "steps": steps,
    "datetime": datetime,
}

for fname in ["sqrt", "sin", "cos", "tan", "asin", "acos", "atan"]:
    f = getattr(math, fname)
    JINJA_ENV[fname] = lambda x: round(f(x), 2)


def render_jinja(text):
    jenv = Environment(
        block_start_string="<%",
        block_end_string="%>",
        variable_start_string="<=",
        variable_end_string="=>",
        comment_start_string="<#",
        comment_end_string="#>",
    )

    return jenv.from_string(text, globals=JINJA_ENV).render()


class MUJinjaRender:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"text": ("STRING", {"default": "", "multiline": True})}}

    RETURN_TYPES = ("STRING",)

    CATEGORY = "misc-utils"
    FUNCTION = "render"

    def render(self, text):
        t = text
        try:
            t = render_jinja(text)
        except TemplateSyntaxError as e:
            log.error("MUJinjaRender failed to render template: %s\n%s", e, text)
        if t.strip() != text.strip():
            log.info("Jinja render result: %s", re.sub("\s+", " ", t, flags=re.MULTILINE))
        return (t,)
