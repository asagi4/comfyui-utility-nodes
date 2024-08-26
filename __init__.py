from .utils import jinja_render as j
from .utils import wildcards as w
from .utils import memory as m
from .utils import replace_model_weights as r
from .utils import cond as c

NODE_CLASS_MAPPINGS = {
    "MUJinjaRender": j.MUJinjaRender,
    "MUSimpleWildcard": w.MUSimpleWildcard,
    "MUForceCacheClear": m.MUForceCacheClear,
    "MUReplaceModelWeights": r.MUReplaceModelWeights,
    "MUConditioningCutoff": c.MUConditioningCutoff,
    "MURemoveControlNet": c.MURemoveControlNet,
}
