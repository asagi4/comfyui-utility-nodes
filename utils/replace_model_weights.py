import folder_paths
import comfy.utils
from comfy.sd import CLIP


class MUReplaceModelWeights:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"model": ("MODEL",), "ckpt_name": (folder_paths.get_filename_list("checkpoints"),)}}

    RETURN_TYPES = ("MODEL", "CLIP")
    FUNCTION = "do"

    CATEGORY = "utils"

    def do(self, model, ckpt_name):
        ckpt_path = folder_paths.get_full_path("checkpoints", ckpt_name)
        sd = comfy.utils.load_torch_file(ckpt_path, safe_load=True)
        to_load = {}
        model = model.clone()
        # Reload clip
        clip_target = model.model.model_config.clip_target()
        clip_sd = model.model.model_config.process_clip_state_dict(sd)
        clip = CLIP(clip_target, embedding_directory=folder_paths.get_folder_paths("embeddings"))
        clip.load_sd(clip_sd, full_model=True)
        del clip_sd

        pfx = "model.diffusion_model."
        for k in list(sd.keys()):
            if k.startswith(pfx):
                to_load[k[len(pfx) :]] = sd.pop(k)
        print("Replacing weights with", ckpt_path)
        to_load = model.model.model_config.process_unet_state_dict(to_load)
        model.model.diffusion_model.load_state_dict(to_load, strict=False)
        del to_load

        return (model, clip)
