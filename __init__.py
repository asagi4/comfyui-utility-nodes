from .utils import jinja_render as j
from .utils import wildcards as w
from .utils import other as o

NODE_CLASS_MAPPINGS = {
    "MUJinjaRender": j.MUJinjaRender,
    "MUSimpleWildcard": w.MUSimpleWildcard,
    "MUConditioningCutoff": o.MUConditioningCutoff,
    "MUStringConcat": o.MUStringConcat,
}
