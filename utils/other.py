class MUStringConcat:
    @classmethod
    def INPUT_TYPES(s):
        t = ("STRING", {"default": ""})
        return {
            "optional": {
                "string1": t,
                "string2": t,
                "string3": t,
                "string4": t,
            }
        }

    RETURN_TYPES = ("STRING",)

    CATEGORY = "miscutils"
    FUNCTION = "cat"

    def cat(self, string1="", string2="", string3="", string4=""):
        return string1 + string2 + string3 + string4


class MUConditioningCutoff:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "conds": ("CONDITIONING",),
                "cutoff": ("FLOAT", {"min": 0.00, "max": 1.00, "default": 0.0, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("CONDITIONING",)
    CATEGORY = "miscutils"
    FUNCTION = "apply"

    def apply(self, conds, cutoff):
        res = []
        new_start = 1.0
        for c in conds:
            end = c[1].get("end_percent", 0.0)
            if 1.0 - end < cutoff:
                continue
            c = [c[0].clone(), c[1].copy()]
            c[1]["start_percent"] = new_start
            c[1]["end_percent"] = end
            new_start = end
            res.append(c)

        return (res,)
