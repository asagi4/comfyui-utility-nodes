import gc
import comfy.model_management
import logging

log = logging.getLogger("comfyui-misc-utils")


class MUForceCacheClear:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"model": ("MODEL",)}}

    NOT_IDEMPOTENT = True
    RETURN_TYPES = ("MODEL",)
    FUNCTION = "do"

    CATEGORY = "utils"

    def do(self, model):
        log.info("Running Python GC and clearing CUDA cache")
        gc.collect()
        comfy.model_management.soft_empty_cache(True)
        return (model,)
