from .utils import jinja_render as j
from .utils import wildcards as w
from .utils import memory as m

NODE_CLASS_MAPPINGS = {
    "MUJinjaRender": j.MUJinjaRender,
    "MUSimpleWildcard": w.MUSimpleWildcard,
    "MUForceCacheClear": m.MUForceCacheClear,
}
