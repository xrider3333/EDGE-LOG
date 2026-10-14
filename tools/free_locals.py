# Insert "a = b = None" lines into one big straight-line function so each local array is released right after its LAST use
# (top-level statement order). Values are untouched, so the output is identical by construction; only peak memory drops.
# Never clears: parameters, closure (cell) variables, names never assigned in the function, names used by the final statement.
#   python free_locals.py <src.py> <func> <out.py>
import ast, sys

src_path, func, out_path = sys.argv[1:4]
src = open(src_path, encoding="utf-8", newline="").read()
src = "".join(ln for ln in src.splitlines(keepends=True) if not ln.rstrip().endswith("= None  # free"))   # idempotent
tree = ast.parse(src)
fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func)
code = compile(tree, src_path, "exec")


def find_code(co, name):
    for c in co.co_consts:
        if hasattr(c, "co_name"):
            if c.co_name == name:
                return c
            r = find_code(c, name)
            if r is not None:
                return r


fco = find_code(code, func)
cells = set(fco.co_cellvars)
params = {a.arg for a in fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs}
if fn.args.vararg: params.add(fn.args.vararg.arg)
if fn.args.kwarg: params.add(fn.args.kwarg.arg)
if "locals" in {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)} or "eval" in src[fn.col_offset:]:
    pass
assigned = set(fco.co_varnames) - params          # true locals of the function (compiler's view)
body = fn.body
last = {}
for i, st in enumerate(body):
    for n in ast.walk(st):
        if isinstance(n, ast.Name):
            last[n.id] = i
        elif isinstance(n, ast.arg):
            pass
clear_at = {}
for name, i in last.items():
    if name in assigned and name not in cells and name not in params and i < len(body) - 1:
        clear_at.setdefault(i, []).append(name)
# insertion line for statement i: its end line, pushed past any statement sharing that line
ends = {}
for i in sorted(clear_at):
    j = i
    while j + 1 < len(body) and body[j + 1].lineno <= body[j].end_lineno:
        j += 1
    if isinstance(body[j], (ast.Return, ast.Raise)):
        continue
    ends.setdefault(body[j].end_lineno, []).extend(sorted(clear_at[i]))
lines = src.splitlines(keepends=True)
indent = " " * body[0].col_offset
nl = "\r\n" if "\r\n" in src else "\n"
out = []
for k, ln in enumerate(lines, 1):
    out.append(ln)
    if k in ends:
        names = ends[k]
        for c0 in range(0, len(names), 8):
            out.append(indent + " = ".join(names[c0:c0 + 8]) + " = None  # free" + nl)
open(out_path, "w", encoding="utf-8", newline="").write("".join(out))
print("cleared %d names at %d points; cells kept %d; params %d" % (sum(len(v) for v in ends.values()), len(ends), len(cells), len(params)))
