from .utils import jinja_render as j
from .utils import wildcards as w

NODE_CLASS_MAPPINGS = {
    "MUJinjaRender": j.MUJinjaRender,
    "MUSimpleWildcard": w.MUSimpleWildcard,
}
