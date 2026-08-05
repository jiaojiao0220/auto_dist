import io, sys

# 读取要删除的精确打印行（已 strip）
delete = set()
with io.open("delete_log_lines.txt", encoding="utf-8") as f:
    for line in f:
        s = line.rstrip("\n")
        if s.strip():
            delete.add(s.strip())

files = [
    "plugins/book118.py",
    "plugins/ec3d50e9.py",
    "plugins/csdn_template.py",
]

for fp in files:
    with io.open(fp, encoding="utf-8") as f:
        lines = f.readlines()
    out = []
    removed = 0
    replaced_pass = 0
    for line in lines:
        stripped = line.strip()
        if stripped in delete:
            # 计算缩进
            indent = line[: len(line) - len(line.lstrip())]
            # 如果是某一行块的“唯一语句”，删除后会变成空块 -> 用 pass 兜底
            # 简单策略：所有命中行都替换为 pass（无害，保持结构合法）
            out.append(indent + "pass\n")
            replaced_pass += 1
            removed += 1
        else:
            out.append(line)
    with io.open(fp, "w", encoding="utf-8") as f:
        f.writelines(out)
    print(f"{fp}: 命中 {removed} 行 -> 改写为 pass")
