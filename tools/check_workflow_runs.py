#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 workbuddy.yml 里所有 run 块的 shell 语法（if/fi 配平、引号闭合）。

用法: python check_workflow_runs.py [workflow.yml]
无 bash 的 Windows 环境用引号/结构检查代替 bash -n。
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("workbuddy.yml")


def iter_run_blocks(steps):
    for st in steps or []:
        run = st.get("run")
        if isinstance(run, str):
            yield st.get("name", "<unnamed>"), run


def collect(node, out, trail=""):
    if isinstance(node, dict):
        if "steps" in node and isinstance(node["steps"], list):
            out.extend(iter_run_blocks(node["steps"]))
        for k, v in node.items():
            if k == "steps":
                continue
            collect(v, out, trail)
    elif isinstance(node, list):
        for v in node:
            collect(v, out, trail)


def structural_check(script: str):
    """无需 bash 的静态检查：if/then/fi 配平、括号配平。"""
    problems = []
    # 去掉行注释，避免把注释里的括号算进去
    lines = []
    for ln in script.splitlines():
        s = ln.strip()
        if s.startswith("#"):
            continue
        # 行尾注释
        s = re.sub(r"\s+#.*$", "", ln)
        lines.append(s)
    body = "\n".join(lines)

    # 剥掉单引号字符串，避免其中内容干扰
    stripped = re.sub(r"'[^']*'", "''", body)

    ifs = len(re.findall(r"^\s*if\b", stripped, re.M))
    fis = len(re.findall(r"^\s*fi\s*$", stripped, re.M))
    thens = len(re.findall(r"\bthen\b", stripped))
    elses_ = len(re.findall(r"^\s*else\s*$", stripped, re.M))

    if ifs != fis:
        problems.append(f"if({ifs}) / fi({fis}) 不配平")
    if ifs != thens:
        problems.append(f"if({ifs}) / then({thens}) 不配平")
    if elses_ > ifs:
        problems.append(f"else({elses_}) 多于 if({ifs})")

    if stripped.count("(") != stripped.count(")"):
        problems.append(f"括号不配平: ( ={stripped.count('(')} ) ={stripped.count(')')}")
    if stripped.count('"') % 2 != 0:
        problems.append("双引号数量为奇数，可能未闭合")

    return problems


def main():
    data = yaml.safe_load(PATH.read_text(encoding="utf-8"))
    blocks = []
    collect(data.get("jobs", {}), blocks)

    bash = shutil.which("bash")
    failures = 0
    for name, script in blocks:
        print(f"\n=== {name} ===")
        probs = structural_check(script)
        if probs:
            failures += 1
            for p in probs:
                print(f"  ✗ {p}")
            continue
        if bash:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".sh", delete=False, encoding="utf-8", newline="\n"
            ) as f:
                f.write("#!/bin/bash\n" + script if "set -" not in script else script)
                tmp = f.name
            r = subprocess.run([bash, "-n", tmp], capture_output=True, text=True)
            if r.returncode != 0:
                failures += 1
                print(f"  ✗ bash -n 失败: {r.stderr.strip()}")
                continue
        print("  ✓ 通过")

    print(f"\n{'=' * 40}")
    print(f"共检查 {len(blocks)} 个 run 块，失败 {failures} 个")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
