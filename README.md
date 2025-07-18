# Ansible Module Usage Scanner

A Python script to analyze and summarize module usage in Ansible playbooks and roles.  
Supports color output, tree/flat/summary views, output in text, CSV, JSON, or HTML, and groups module usage by role.

## Features

- Recursively scans playbooks and roles for all module usage
- Grouped summary by role and total unique module count
- Outputs: colored text (tree/flat/summary), JSON, CSV, HTML
- No nonstandard dependencies (just PyYAML and a working `ansible-doc`)

## Usage

```bash
python3 list_ansible_module_usages.py <file_or_directory> [--view tree|flat|summary] [--output text|json|csv|html]

## Examples
```bash
python3 list_ansible_module_usages.py . --output html > report.html
python3 list_ansible_module_usages.py myplaybook.yml --view summary
