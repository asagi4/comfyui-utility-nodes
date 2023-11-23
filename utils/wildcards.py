import logging
from os import environ
import random
import re
from pathlib import Path
import json

from .parse import parse

import folder_paths

# from .parse import parse

log = logging.getLogger("comfyui-misc-utils")
log.setLevel(logging.INFO)

CLASS_NAME = "MUSimpleWildcard"


def get_lora_tags(lora_name):
    filenames = [Path(f) for f in folder_paths.get_filename_list("loras")]
    found = None
    for f in filenames:
        if f.stem == lora_name:
            found = f
            break
    if not found:
        return []
    meta = load_lora_meta(found)
    tags = json.loads(meta.get("ss_tag_frequency", "{}"))
    alltags = []
    tagcounts = {}
    for k in tags:
        for tag, count in tags[k].items():
            t = tag.strip().replace("_", " ")
            tagcounts[t] = tagcounts.get(t, 0) + count
    alltags = [(v, k) for k, v in tagcounts.items()]
    return sorted(alltags, reverse=True)


def load_lora_meta(filename):
    try:
        with open(filename, "r", encoding="utf8") as m:
            header = m.read(8)
            n = int.from_bytes(header, "little")
            metadata_bytes = m.read(n)
            return json.loads(metadata_bytes).get("__metadata__", {})
    except Exception as e:
        log.error("Metadata load failed for %s: %s", filename, e)
        return {}


def replace_lora_tags(text, seed):
    rand = random.Random(seed)
    func = re.compile(r"\bTAG<(?P<args>.*?)>")
    text, matches = find_and_remove(func, text, placeholder="WILDCARDLORA")
    for placeholder, value in matches.items():
        args = value["args"].strip().split(",")
        replacement = []
        count = 1
        mode = "t"
        try:
            loraname = args[0]
            if len(args) > 1:
                count = int(args[1])
            if len(args) > 2:
                mode = args[2].strip()
            tags = [t[1] for t in get_lora_tags(loraname)]
            if len(tags) <= count:
                replacement = tags
            elif mode == "r":
                # rand
                rand.sample(population=tags)
            else:
                # top
                replacement = tags[:count]
        except Exception as e:
            print("Error:", e)
            pass

        r = ", ".join(replacement)
        text = text.replace(placeholder, r)

    return text


def wildcard_prompt_handler(json_data):
    for node_id in json_data["prompt"].keys():
        if json_data["prompt"][node_id]["class_type"] == CLASS_NAME:
            handle_wildcard_node(json_data, node_id)
    return json_data


def handle_wildcard_node(json_data, node_id):
    wildcard_info = json_data.get("extra_data", {}).get("extra_pnginfo", {}).get(CLASS_NAME, {})
    n = json_data["prompt"][node_id]
    if not (n["inputs"].get("use_pnginfo") and node_id in wildcard_info):
        text = MUSimpleWildcard.select(n["inputs"]["text"], n["inputs"]["seed"])
        text = replace_lora_tags(text, n["inputs"]["seed"])

    if text.strip() != n["inputs"]["text"].strip():
        json_data["prompt"][node_id]["inputs"]["use_pnginfo"] = True
        wildcard_info[node_id] = text
        json_data["extra_data"]["extra_pnginfo"][CLASS_NAME] = wildcard_info
    return json_data


def read_preamble():
    curfile = Path(__file__)
    defaults = curfile.parent / "default_functions.txt"
    with open(defaults, "r") as f:
        return parse(f.read())[1]


def find_and_remove(regexp, text, placeholder=""):
    m = regexp.search(text)
    res = {}
    index = 0

    while m:
        index += 1
        ph = ""
        if placeholder:
            ph = "__" + placeholder + str(index) + "__"
            res[ph] = m.groupdict()
        else:
            res[m["name"]] = m.groupdict()
        s, e = m.span()
        text = text[:s] + ph + text[e:]
        m = regexp.search(text)
    return res, text


class MUSimpleWildcard:
    RAND = random.Random()

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text": ("STRING", {"default": "", "multiline": True}),
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
            log.warning("Wildcard file not found for %s", name)
            return [name]

    @classmethod
    def select(cls, text, seed):
        cls.RAND.seed(seed)
        wildcard_re = re.compile(r"\$(?P<name>[A-Za-z0-9_/.-]+)(\+(?P<offset>[0-9]+))?\$")
        matches, text = find_and_remove(wildcard_re, text, placeholder="MU_WILDCARD")
        for placeholder, value in matches.items():
            state = None
            ws = cls.read_wildcards(value["name"])
            offset = int(value["offset"] or 0)
            if offset:
                # advance the state once and store it so that the next non-offset result stays deterministic
                w = cls.RAND.choice(ws)
                state = cls.RAND.getstate()
                # advance the state until offset,
                for _ in range(offset):
                    w = cls.RAND.choice(ws)
            else:
                w = cls.RAND.choice(ws)
            text = text.replace(placeholder, w)
            log.info("Selected wildcard %s for %s", w, value["name"])
            if state:
                cls.RAND.setstate(state)

        return text.strip()

    def doit(self, text, seed, extra_pnginfo, unique_id, use_pnginfo=False):
        if use_pnginfo and unique_id in extra_pnginfo.get(CLASS_NAME, {}):
            text = extra_pnginfo[CLASS_NAME][unique_id]
            log.info("MUSimpleWildcard using prompt: %s", text)
        ctx = read_preamble()
        newtext, _ = parse(text, ctx)
        if newtext != text:
            log.info("MUSimpleWildcard result:\n%s", newtext)
        return (newtext,)


try:
    from server import PromptServer

    PromptServer.instance.add_on_prompt_handler(wildcard_prompt_handler)
except ImportError:
    print("Could not install wildcard prompt handler, node won't work")

if __name__ == "__main__":
    ctx = read_preamble()
