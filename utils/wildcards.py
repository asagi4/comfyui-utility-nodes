import logging
from os import environ
import random
import re
from pathlib import Path
import json
import mmap

from .parse import parse


# from .parse import parse

log = logging.getLogger("comfyui-misc-utils")
log.setLevel(logging.INFO)

CLASS_NAME = "MUSimpleWildcard"


def get_lora_tags(lora_name):
    filenames = [Path(f) for f in folder_paths.get_filename_list("loras")]
    found = None
    for f in filenames:
        if f.stem == lora_name:
            found = folder_paths.get_full_path("loras", str(f))
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
        with open(filename, "r", encoding="utf8") as f:
            with mmap.mmap(f.fileno(), length=0, access=mmap.ACCESS_READ) as m:
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
    matches, text = find_and_remove(func, text, placeholder="WILDCARDLORA")
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
                replacement = rand.sample(population=tags, k=count)
            else:
                replacement = tags[:count]
        except Exception as e:
            print("Error selecting tags:", e)
            pass

        r = ", ".join(replacement)
        text = text.replace(placeholder, r)

    return text


global_ctx = None


def wildcard_prompt_handler(json_data):
    for node_id in json_data["prompt"].keys():
        if json_data["prompt"][node_id]["class_type"] == CLASS_NAME:
            handle_wildcard_node(json_data, node_id)
    return json_data


def handle_wildcard_node(json_data, node_id):
    global global_ctx
    wildcard_info = json_data.get("extra_data", {}).get("extra_pnginfo", {}).get(CLASS_NAME, {})
    n = json_data["prompt"][node_id]
    seed = n["inputs"]["seed"]
    if not (n["inputs"].get("use_pnginfo") and node_id in wildcard_info):
        text = MUSimpleWildcard.select(n["inputs"]["text"], seed)
        if not global_ctx or "$debugwc" in text:
            global_ctx = read_preamble()
        global_ctx.set("seed", lambda: str(seed))
        text, _ = parse(text, global_ctx)
        text = replace_lora_tags(text, seed)

    if text.strip() != n["inputs"]["text"].strip():
        json_data["prompt"][node_id]["inputs"]["use_pnginfo"] = True
        wildcard_info[node_id] = text
        json_data["extra_data"]["extra_pnginfo"][CLASS_NAME] = wildcard_info
    return json_data


def read_preamble():
    includes = environ.get("MU_WILDCARD_INCLUDE", "defaults")
    includes = [x.strip() for x in includes.split(";") if x.strip()]
    ctx = None
    for x in includes:
        file = Path(x)
        if x == "defaults":
            curfile = Path(__file__)
            file = curfile.parent / "default_functions.txt"
        try:
            with open(file, "r") as f:
                log.info("Reading functions from %s", file)
                ctx = parse(f.read(), ctx=ctx)[1]
        except Exception as e:
            log.error("Error reading definitions from %s: %s. Ignoring...", file, e)
    return ctx


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

    CATEGORY = "misc-utils"
    FUNCTION = "doit"

    @classmethod
    def read_wildcards(cls, name):
        path = environ.get("MU_WILDCARD_BASEDIR", "wildcards")
        r = name.split(":")
        name = r[0]
        filters = r[1:]

        def matches(x):
            for f in filters:
                if f.startswith("!") and f[1:] in x:
                    return False
                elif not f.startswith("!") and f not in x:
                    return False
            return True

        f = (Path(path) / Path(name)).with_suffix(".txt")
        try:
            with open(f, "r") as file:
                return [l.strip() for l in file.readlines() if l.strip() and matches(l)]
        except:
            log.warning("Wildcard file not found for %s", name)
            return [name]

    @classmethod
    def select(cls, text, seed):
        cls.RAND.seed(seed)
        wildcard_re = re.compile(r"\$(?P<name>[A-Za-z0-9_/.!:-]+)(\+(?P<offset>[0-9]+))?\$")
        matches, text = find_and_remove(wildcard_re, text, placeholder="MU_WILDCARD")
        for placeholder, value in matches.items():
            state = None
            ws = cls.read_wildcards(value["name"])
            offset = int(value["offset"] or 0)
            if ws and offset:
                # advance the state once and store it so that the next non-offset result stays deterministic
                w = cls.RAND.choice(ws)
                state = cls.RAND.getstate()
                # advance the state until offset,
                for _ in range(offset):
                    w = cls.RAND.choice(ws)
            elif ws:
                w = cls.RAND.choice(ws)
            else:
                log.warning("No wildcards found for %s", value["name"])
                w = ""
            text = text.replace(placeholder, w)
            log.info("Replaced wildcard %s with '%s'", value["name"], w)
            if state:
                cls.RAND.setstate(state)

        return text.strip()

    def doit(self, text, seed, extra_pnginfo, unique_id, use_pnginfo=False):
        if use_pnginfo and unique_id in extra_pnginfo.get(CLASS_NAME, {}):
            text = extra_pnginfo[CLASS_NAME][unique_id]
            log.info("MUSimpleWildcard using prompt: %s", text)
        return (text,)


try:
    from server import PromptServer
    import folder_paths

    PromptServer.instance.add_on_prompt_handler(wildcard_prompt_handler)
except ImportError:
    print("Could not install wildcard prompt handler, node won't work")

if __name__ == "__main__":
    print("Start parse")
    ctx = read_preamble()
    print("End parse")
