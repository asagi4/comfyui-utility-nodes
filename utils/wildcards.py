import logging
from os import environ
import random
import re
from pathlib import Path
from server import PromptServer

log = logging.getLogger("comfyui-misc-utils")

CLASS_NAME = "MUSimpleWildcard"


def wildcard_prompt_handler(json_data):
    log.info("Resolving wildcards...")
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


PromptServer.instance.add_on_prompt_handler(wildcard_prompt_handler)


def variable_substitution(text):
    var_re = re.compile(r"(\$[a-z]+)\s*=([^;\n]*);?")
    m = var_re.search(text)
    while m:
        var = m[1]
        sub = m[2]
        s, e = m.span()
        text = text[:s] + text[e:]
        log.info("Substituting %s with '%s'", var, sub)
        text = text.replace(var, sub)
        m = var_re.search(text)
    return text


class MUSimpleWildcard:
    RAND = random.Random()

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text": ("STRING", {"default": ""}),
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
            return [name]

    @classmethod
    def select(cls, text, seed):
        cls.RAND.seed(seed)
        matches = re.findall(r"(\$([A-Za-z0-9_/.-]+)(\+[0-9]+)?\$)", text)
        for placeholder, wildcard, offset in matches:
            if offset:
                offset = int(offset[1:])
                cls.RAND.seed(seed + offset)
            w = cls.RAND.choice(cls.read_wildcards(wildcard))
            text = text.replace(placeholder, w, 1)
            log.info("Selected wildcard %s for %s", w, placeholder)
            if offset:
                cls.RAND.seed(seed)
        return text

    def doit(self, text, seed, extra_pnginfo, unique_id, use_pnginfo=False):
        if use_pnginfo and unique_id in extra_pnginfo.get(CLASS_NAME, {}):
            text = extra_pnginfo[CLASS_NAME][unique_id]
            log.info("MUSimpleWildcard using prompt: %s", text)
        text = variable_substitution(text)
        return (text,)
