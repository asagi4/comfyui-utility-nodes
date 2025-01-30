import logging

log = logging.getLogger("comfyui-misc-utils")


class MURemoveControlNet:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "conds": ("CONDITIONING",),
            }
        }

    RETURN_TYPES = ("CONDITIONING",)
    CATEGORY = "misc-utils"
    FUNCTION = "apply"

    def apply(self, conds):
        res = []
        for c in conds:
            c = [c[0].clone(), c[1].copy()]
            if "control" in c[1]:
                del c[1]["control"]
            if "control_apply_to_uncond" in c[1]:
                del c[1]["control_apply_to_uncond"]
            res.append(c)
        return (res,)


class MUConditioningCutoff:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "conds": ("CONDITIONING",),
                "start_cutoff": ("FLOAT", {"min": 0.00, "max": 1.00, "default": 0.0, "step": 0.01}),
                "end_cutoff": ("FLOAT", {"min": 0.00, "max": 1.00, "default": 1.0, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("CONDITIONING",)
    CATEGORY = "misc-utils"
    FUNCTION = "apply"

    def apply(self, conds, start_cutoff, end_cutoff):
        res = []
        for c in conds:
            start = c[1].get("start_percent", 0.0)
            end = c[1].get("end_percent", 1.0)
            if end < start_cutoff:
                log.debug("Chose to remove prompt '%s'", c[1].get("prompt", "N/A"))
                continue
            if start >= end_cutoff:
                log.debug("Chose to remove prompt '%s'", c[1].get("prompt", "N/A"))
                continue
            if end >= end_cutoff:
                end = 1.0
            if start <= start_cutoff:
                start = 0.0
            c = [c[0].clone(), c[1].copy()]
            c[1]["start_percent"] = start
            c[1]["end_percent"] = end
            res.append(c)

        if len(res) == 0:
            log.warn("Cutoff would filter all conds, using the last one")
            c = conds[-1]
            c = [c[0], c[1].copy()]
            c[1]["start_percent"] = 0.0
            c[1]["end_percent"] = 1.0
            res.append(c)

        return (res,)
