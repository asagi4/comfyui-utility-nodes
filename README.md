# ComfyUI utility nodes

A collection of miscellaneous nodes for ComfyUI

# Nodes

## MUSimpleWildcard

Expands wildcards, variables and functions (macros).

### Wildcards

Anything of the form `$name$` will look up `name.txt` in the directory specified by the environment variable `MU_WILDCARD_BASEDIR` (defaults to `wildcards` under the current working directory if unset) and randomly chooses one line from it as a replacement.

### Functions and variables
For example:
```
$z = realistic, photo
$foo($a, $b=sporty, $c=default thing) = { $c, $z, a $b $a  }
$foo(car, $c=another thing)
```

expands to `another thing, realistic, photo, a sporty car`

Variables can be defined inside functions and are local to the function.

You can define multiple variables per line by separating them with `;`

Note that variables and functions can be defined *anywhere* in the prompt, meaning that `a $foo = bar` will define `$foo` and expand into just `a `. This might cause weird behaviour if you want to do complicated things with `MUJinjaRender`.

Variables are **not** captured by function definitions. If you define a variable `$z`, then define `$f() { a $z }`, and then redefine `$z`, any calls to`$f` will use the *redefined* value.

`"text"` can be used to quote something when it would conflict with syntax, for example: `$func("parameter, with comma", second parameter)`. If you need a `"` by itself, use `""`.

#### Default functions
There are some default functions available. put `$help()` in your prompt to see a list of available functions.

You can control what is included by default with the environment variable `MU_WILDCARD_INCLUDE`. Set it to a string of paths separated by `;` and they will be read and parsed into a global context at startup. The filename `defaults` is special and reads the default prelude included with the custom node.

If unset, the default is `defaults`.

For example, set
`MU_WILDCARD_INCLUDE=""` to read nothing
`MU_WILDCARD_INCLUDE=defaults;/home/sd/my_functions.txt` to read both the defaults and `/home/sd/my_functions.txt`

Parsing can take some time, so the files are read only once at startup, but using the magic string `$debugwc` in your prompt will trigger a reload.

## MUJinjaRender
You can use this node to evaluate a string as a Jinja2 template. Note, however, that because ComfyUI's frontend uses `{}` for syntax, There are the following modifications to Jinja syntax:

- `{% %}` becomes `<% %>`
- `{{ }}` becomes `<= =>`
- `{# #}` becomes `<# #>`

### Functions in Jinja templates

The following functions and constants are available:

- `pi`
- `min`, `max`, `clamp(minimum, value, maximum)`,
- `abs`, `round`, `ceil`, `floor`
- `sqrt` `sin`, `cos`, `tan`, `asin`, `acos`, `atan`. These functions are rounded to two decimals


In addition, a special `steps` function exists.

The `steps` function will generate a list of steps for iterating. 

You can call it either as `steps(end)`, `steps(end, step=0.1)` or `steps(start, end, step)`. `step` is an optional parameter that defaults to `0.1`. It'll return steps *inclusive* of start and end as long as step doesn't go past the end. 
The second form is equivalent to `steps(step, end, step)`. i.e. it starts at the first step.
