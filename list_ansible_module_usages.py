#!/usr/bin/env python3

import sys
import os
import glob
import yaml
import subprocess
import json
from collections import defaultdict

BOLD = '\033[1m'
RED = '\033[31m'
GREEN = '\033[32m'
YELLOW = '\033[33m'
BLUE = '\033[34m'
MAGENTA = '\033[35m'
CYAN = '\033[36m'
WHITE = '\033[37m'
RESET = '\033[0m'

IGNORED_FIELDS = {
    "name", "when", "tags", "register", "vars", "with_items", "loop", "become", "delegate_to", "ignore_errors",
    "notify", "args", "environment", "run_once", "retries", "delay", "until", "failed_when", "changed_when", "block",
    "always", "rescue", "import_tasks", "include_tasks", "import_playbook", "import_role", "include_role", "set_fact", "meta",
    "hosts", "roles", "tasks", "gather_facts", "vars_files", "pre_tasks", "post_tasks", "handlers"
}

def extract_module_and_params(task):
    for k in task:
        if k not in IGNORED_FIELDS:
            params = task[k] if isinstance(task[k], dict) else {'__value__': task[k]}
            yield k, params

def list_module_usages_in_playbook(yaml_file):
    try:
        with open(yaml_file, 'r') as f:
            content = yaml.safe_load(f)
    except Exception as e:
        return []
    usages = []
    if isinstance(content, dict) and "tasks" in content:
        tasks = content["tasks"]
    elif isinstance(content, list):
        tasks = []
        for item in content:
            if isinstance(item, dict) and "tasks" in item:
                tasks += item["tasks"]
            elif isinstance(item, dict):
                tasks.append(item)
    else:
        tasks = []
    for task in tasks:
        for mod, params in extract_module_and_params(task):
            usages.append((mod, params))
    return usages

def get_ansible_module_fqcns():
    try:
        out = subprocess.check_output(["ansible-doc", "--list", "--json"], text=True)
        data = json.loads(out)
    except Exception as e:
        print(RED + "Error running ansible-doc --list --json:" + RESET, e)
        sys.exit(2)
    mod_map = {}
    for fqcn, info in data.items():
        short_name = fqcn.split('.')[-1]
        mod_map[short_name] = fqcn
        mod_map[fqcn] = fqcn
    return mod_map

def find_yaml_files_in_directory(directory, recurse=True):
    patterns = ["*.yml", "*.yaml"]
    files = []
    for pattern in patterns:
        files.extend(glob.glob(os.path.join(directory, "**", pattern), recursive=True))
    for pattern in patterns:
        files.extend(glob.glob(os.path.join(directory, "roles", "*", "tasks", pattern)))
        files.extend(glob.glob(os.path.join(directory, "roles", "*", "handlers", pattern)))
    files = list(sorted(set(files)))
    return files

def print_params_tree(params, prefix="      "):
    if isinstance(params, dict):
        for k, v in params.items():
            print(f"{prefix}{BLUE}{k}{RESET}: {v}")
    else:
        print(f"{prefix}{params}")

def get_role_from_path(path):
    parts = path.split(os.sep)
    try:
        idx = parts.index('roles')
        if len(parts) > idx + 1:
            return parts[idx + 1]
    except ValueError:
        pass
    return None

def print_grouped_summary(role_to_modules):
    print(f"\n{BOLD}Module summary by role:{RESET}")
    for role in sorted(role_to_modules):
        rolename = role if role else "Not in role"
        print(f"{CYAN}Role: {rolename}{RESET}")
        for mod in sorted(role_to_modules[role]):
            print(f"  {YELLOW}{mod}{RESET}")

def build_tree(paths, base):
    tree = lambda: defaultdict(tree)
    root = tree()
    for f in paths:
        rel = os.path.relpath(f, start=base)
        parts = rel.split(os.sep)
        current = root
        for part in parts[:-1]:
            current = current[part]
        current[parts[-1]] = None
    return root

def render_tree(node, base_path, prefix="", parent_path="", is_last=True, unique_modules=None, fqcn_map=None, role_to_modules=None):
    items = list(node.items())
    files = [k for k, v in items if v is None]
    dirs = [k for k, v in items if v is not None]
    n_files = len(files)
    n_dirs = len(dirs)

    for i, name in enumerate(files):
        connector = "└── " if (i == n_files - 1 and n_dirs == 0) else "├── "
        print(f"{prefix}{connector}{BOLD}{WHITE}{name}{RESET}")
        abs_path = os.path.join(base_path, parent_path, name)
        usages = list_module_usages_in_playbook(abs_path)
        if usages:
            print(f"{prefix}    {MAGENTA}Found following modules with their parameters:{RESET}")
            for j, (m, params) in enumerate(usages):
                mod_connector = "└─" if j == len(usages) - 1 else "├─"
                fqcn = fqcn_map.get(m, m if '.' in m else "<unknown or custom module>")
                if unique_modules is not None:
                    unique_modules.add(fqcn)
                if role_to_modules is not None:
                    role = get_role_from_path(abs_path)
                    role_to_modules[role].add(fqcn)
                print(f"{prefix}    {mod_connector} {GREEN}{m}{RESET} ({YELLOW}{fqcn}{RESET})")
                print_params_tree(params, prefix + "      ")
        else:
            print(f"{prefix}    {RED}No modules found (or not an Ansible playbook).{RESET}")

    for i, dirname in enumerate(dirs):
        connector = "└── " if i == n_dirs - 1 else "├── "
        print(f"{prefix}{connector}{CYAN}{BOLD}{dirname}/{RESET}")
        new_prefix = prefix + ("    " if i == n_dirs - 1 else "│   ")
        render_tree(node[dirname], base_path, new_prefix, os.path.join(parent_path, dirname), is_last=(i == n_dirs - 1),
                    unique_modules=unique_modules, fqcn_map=fqcn_map, role_to_modules=role_to_modules)

def tree_view(files, fqcn_map):
    unique_modules = set()
    role_to_modules = defaultdict(set)
    if not files:
        print(f"{RED}No YAML files found.{RESET}")
        return

    if len(files) == 1:
        file = files[0]
        print(f"{BOLD}{WHITE}{os.path.basename(file)}{RESET}")
        usages = list_module_usages_in_playbook(file)
        if usages:
            print(f"{MAGENTA}Found following modules with their parameters:{RESET}")
            for j, (m, params) in enumerate(usages):
                mod_connector = "└─" if j == len(usages) - 1 else "├─"
                fqcn = fqcn_map.get(m, m if '.' in m else "<unknown or custom module>")
                unique_modules.add(fqcn)
                role = get_role_from_path(file)
                role_to_modules[role].add(fqcn)
                print(f"{mod_connector} {GREEN}{m}{RESET} ({YELLOW}{fqcn}{RESET})")
                print_params_tree(params, "    ")
        else:
            print(f"{RED}No modules found (or not an Ansible playbook).{RESET}")
        print(f"\n{BOLD}Total unique modules: {len(unique_modules)}{RESET}")
        print_grouped_summary(role_to_modules)
        return

    root_dir = os.path.commonpath(files)
    tree = build_tree(files, root_dir)
    print(f"{CYAN}{BOLD}{os.path.basename(root_dir)}/{RESET}")
    render_tree(tree, root_dir, prefix="", parent_path="", is_last=True, unique_modules=unique_modules, fqcn_map=fqcn_map, role_to_modules=role_to_modules)
    print(f"\n{BOLD}Total unique modules: {len(unique_modules)}{RESET}")
    print_grouped_summary(role_to_modules)

def flat_view(files, fqcn_map):
    unique_modules = set()
    role_to_modules = defaultdict(set)
    for filename in files:
        print(f"\n{BOLD}{WHITE}Analyzing playbook file: {filename}{RESET}\n")
        usages = list_module_usages_in_playbook(filename)
        if usages:
            print(f"{MAGENTA}Found following modules with their parameters:{RESET}\n")
            for m, params in usages:
                fqcn = fqcn_map.get(m, m if '.' in m else "<unknown or custom module>")
                unique_modules.add(fqcn)
                role = get_role_from_path(filename)
                role_to_modules[role].add(fqcn)
                print(f"{GREEN}{m}{RESET} ({YELLOW}{fqcn}{RESET}):")
                print_params_tree(params)
                print()
        else:
            print(f"{RED}No modules found (or not an Ansible playbook).{RESET}")
    print(f"\n{BOLD}Total unique modules: {len(unique_modules)}{RESET}")
    print_grouped_summary(role_to_modules)

def summary_view(files, fqcn_map):
    mod_to_files = {}
    role_to_modules = defaultdict(set)
    for filename in files:
        usages = list_module_usages_in_playbook(filename)
        for m, _ in usages:
            fqcn = fqcn_map.get(m, m if '.' in m else "<unknown or custom module>")
            mod_to_files.setdefault(fqcn, set()).add(filename)
            role = get_role_from_path(filename)
            role_to_modules[role].add(fqcn)
    print(f"{MAGENTA}Summary of modules used across files:{RESET}")
    for fqcn, fileset in sorted(mod_to_files.items()):
        print(f"{YELLOW}{fqcn}{RESET}:")
        for f in sorted(fileset):
            print(f"    {f}")
    print(f"\n{BOLD}Total unique modules: {len(mod_to_files)}{RESET}")
    print_grouped_summary(role_to_modules)

def output_json(files, fqcn_map):
    data = []
    unique_modules = set()
    role_to_modules = defaultdict(set)
    for filename in files:
        usages = list_module_usages_in_playbook(filename)
        for m, params in usages:
            fqcn = fqcn_map.get(m, m if '.' in m else "<unknown or custom module>")
            unique_modules.add(fqcn)
            role = get_role_from_path(filename)
            role_to_modules[role].add(fqcn)
            data.append({
                "file": filename,
                "module": m,
                "fqcn": fqcn,
                "params": params,
                "role": role
            })
    print(json.dumps(data, indent=2))
    print(f"\nTotal unique modules: {len(unique_modules)}")
    print("\nModule summary by role:")
    for role in sorted(role_to_modules):
        rolename = role if role else "Not in role"
        print(f"Role: {rolename}")
        for mod in sorted(role_to_modules[role]):
            print(f"  {mod}")

def output_csv(files, fqcn_map):
    import csv
    import sys
    unique_modules = set()
    role_to_modules = defaultdict(set)
    writer = csv.writer(sys.stdout)
    writer.writerow(["file", "module", "fqcn", "param", "value", "role"])
    for filename in files:
        usages = list_module_usages_in_playbook(filename)
        for m, params in usages:
            fqcn = fqcn_map.get(m, m if '.' in m else "<unknown or custom module>")
            unique_modules.add(fqcn)
            role = get_role_from_path(filename)
            role_to_modules[role].add(fqcn)
            if isinstance(params, dict):
                for k, v in params.items():
                    writer.writerow([filename, m, fqcn, k, v, role])
            else:
                writer.writerow([filename, m, fqcn, '', params, role])
    print(f"\nTotal unique modules: {len(unique_modules)}", file=sys.stderr)
    print("\nModule summary by role:", file=sys.stderr)
    for role in sorted(role_to_modules):
        rolename = role if role else "Not in role"
        print(f"Role: {rolename}", file=sys.stderr)
        for mod in sorted(role_to_modules[role]):
            print(f"  {mod}", file=sys.stderr)

def output_html(files, fqcn_map):
    unique_modules = set()
    role_to_modules = defaultdict(set)
    rows = []
    for filename in files:
        usages = list_module_usages_in_playbook(filename)
        for m, params in usages:
            fqcn = fqcn_map.get(m, m if '.' in m else "<unknown or custom module>")
            unique_modules.add(fqcn)
            role = get_role_from_path(filename)
            role_to_modules[role].add(fqcn)
            if isinstance(params, dict):
                for k, v in params.items():
                    rows.append((filename, m, fqcn, k, v, role))
            else:
                rows.append((filename, m, fqcn, '', params, role))

    print("<!DOCTYPE html>")
    print("<html><head><meta charset='utf-8'><title>Ansible Module Usage</title>")
    print("<style>body {font-family: sans-serif;} table {border-collapse:collapse;} th,td {border:1px solid #aaa; padding:4px;} th {background:#eee;}</style>")
    print("</head><body>")
    print("<h2>Ansible Module Usage Report</h2>")
    print(f"<p><strong>Total unique modules:</strong> {len(unique_modules)}</p>")
    print("<table>")
    print("<tr><th>File</th><th>Module</th><th>FQCN</th><th>Parameter</th><th>Value</th><th>Role</th></tr>")
    for row in rows:
        print("<tr>" + "".join(f"<td>{str(x)}</td>" for x in row) + "</tr>")
    print("</table>")
    print("<h3>Module summary by role:</h3>")
    print("<ul>")
    for role in sorted(role_to_modules):
        rolename = role if role else "Not in role"
        print(f"<li><strong>{rolename}</strong><ul>")
        for mod in sorted(role_to_modules[role]):
            print(f"<li>{mod}</li>")
        print("</ul></li>")
    print("</ul></body></html>")

if __name__ == "__main__":
    input_path = None
    view = "tree"
    output_format = "text"
    args = list(sys.argv[1:])
    if not args:
        print("Usage: python list_ansible_module_usages.py <file_or_directory> [--view tree|flat|summary] [--output text|json|csv|html]")
        sys.exit(1)
    if args[0].startswith("-"):
        print("Please specify a file or directory as the first argument.")
        sys.exit(1)
    input_path = args[0]
    if "--view" in args:
        idx = args.index("--view")
        if len(args) > idx+1:
            view = args[idx+1]
    if "--output" in args:
        idx = args.index("--output")
        if len(args) > idx+1:
            output_format = args[idx+1]

    fqcn_map = get_ansible_module_fqcns()
    files = []
    if os.path.isdir(input_path):
        files = find_yaml_files_in_directory(input_path, recurse=True)
        files = [os.path.abspath(f) for f in files]
    elif os.path.isfile(input_path):
        files = [os.path.abspath(input_path)]
    else:
        print(f"{input_path} is neither a file nor a directory.")
        sys.exit(1)
    if not files:
        print("No YAML files found.")
        sys.exit(0)

    if output_format == "json":
        output_json(files, fqcn_map)
    elif output_format == "csv":
        output_csv(files, fqcn_map)
    elif output_format == "html":
        output_html(files, fqcn_map)
    else:
        if view == "tree":
            tree_view(files, fqcn_map)
        elif view == "flat":
            flat_view(files, fqcn_map)
        elif view == "summary":
            summary_view(files, fqcn_map)
        else:
            print(f"Unknown view: {view}")
            sys.exit(1)
