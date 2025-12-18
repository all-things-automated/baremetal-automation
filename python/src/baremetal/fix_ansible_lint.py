#!/usr/bin/env python3
"""
Ansible-lint fixer for trailing whitespace issues.

This script runs ansible-lint on Ansible roles or playbooks directories and 
automatically fixes trailing whitespace issues reported by the 
yaml[trailing-spaces] rule.

Usage:
    python fix_ansible_lint.py ../roles      # Lint all roles in roles/
    python fix_ansible_lint.py ../playbooks  # Lint all playbooks in playbooks/
    python fix_ansible_lint.py ../roles ../playbooks
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


class AnsibleLintFixer:
    """Fixes ansible-lint issues automatically."""

    def __init__(self, target_path: str):
        self.target_path = Path(target_path).resolve()
        self.target_type = self._detect_target_type()
        self.targets = self._expand_targets()
        self.trailing_spaces_pattern = re.compile(
            r"yaml\[trailing-spaces\]: Trailing spaces\n(.+):(\d+)"
        )
    
    def _detect_target_type(self) -> str:
        """
        Detect if target is a roles or playbooks directory.
        
        Returns:
            String indicating target type: 'roles_dir', 'playbooks_dir', 'unknown'
        """
        if not self.target_path.exists():
            return 'unknown'
        
        if not self.target_path.is_dir():
            return 'unknown'
        
        # Check directory name to determine type
        if self.target_path.name == 'roles':
            return 'roles_dir'
        elif self.target_path.name == 'playbooks':
            return 'playbooks_dir'
        
        return 'unknown'
    
    def _expand_targets(self) -> List[Path]:
        """
        Expand target directory into individual roles or playbook files.
        
        Returns:
            List of paths to lint (individual roles or playbook files)
        """
        if self.target_type == 'roles_dir':
            # Get all subdirectories in roles/ that have tasks/main.yml
            roles = []
            for item in self.target_path.iterdir():
                if item.is_dir() and (item / 'tasks' / 'main.yml').exists():
                    roles.append(item)
            return sorted(roles)
        
        elif self.target_type == 'playbooks_dir':
            # Get all .yml and .yaml files in playbooks/
            playbooks = []
            for item in self.target_path.iterdir():
                if item.is_file() and item.suffix in ['.yml', '.yaml']:
                    playbooks.append(item)
            return sorted(playbooks)
        
        return []

    def run_ansible_lint(self, lint_target: Path) -> Tuple[int, str]:
        """
        Run ansible-lint on a specific target.

        Args:
            lint_target: Path to lint (role directory or playbook file)

        Returns:
            Tuple of (return_code, output)
        """
        try:
            result = subprocess.run(
                ["ansible-lint", str(lint_target)],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode, result.stdout + result.stderr
        except FileNotFoundError:
            print("[ERROR] ansible-lint command not found. Please install ansible-lint.")
            sys.exit(1)

    def parse_trailing_spaces_errors(self, lint_output: str, lint_target: Path) -> List[Tuple[Path, int]]:
        """
        Parse ansible-lint output for trailing spaces errors.

        Args:
            lint_output: Output from ansible-lint
            lint_target: The target that was linted (for resolving relative paths)

        Returns:
            List of (file_path, line_number) tuples with Path objects
        """
        errors = []
        lines = lint_output.split("\n")

        for i, line in enumerate(lines):
            if "yaml[trailing-spaces]" in line:
                # Next line should contain the file path and line number
                if i + 1 < len(lines):
                    match = re.match(r"^(.+):(\d+)", lines[i + 1])
                    if match:
                        file_path_str = match.group(1)
                        line_num = int(match.group(2))
                        
                        # ansible-lint outputs just the filename when linting a single file
                        # It outputs relative paths when linting a role directory
                        
                        # For single file playbooks: ansible-lint reports just the filename
                        # We need to use the lint_target directly, NOT resolve it again
                        if lint_target.is_file() and file_path_str == lint_target.name:
                            resolved_path = lint_target
                        else:
                            # For roles or other cases with path components
                            path_obj = Path(file_path_str)
                            if path_obj.is_absolute():
                                resolved_path = path_obj
                            else:
                                # Resolve relative to appropriate directory
                                if lint_target.is_file():
                                    resolved_path = (lint_target.parent / path_obj).resolve()
                                else:
                                    resolved_path = (lint_target / path_obj).resolve()
                        
                        errors.append((resolved_path, line_num))

        return errors

    def fix_trailing_spaces_in_file(
        self, file_path: str, line_numbers: List[int]
    ) -> int:
        """
        Remove trailing spaces from specific lines in a file.

        Args:
            file_path: Path to the file (string)
            line_numbers: List of line numbers (1-indexed) to fix

        Returns:
            Number of lines fixed
        """
        file_path_obj = Path(file_path)

        if not file_path_obj.exists():
            print(f"[WARNING] File not found: {file_path_obj}")
            # Try to provide helpful debug info
            if file_path_obj.is_absolute():
                print(f"[DEBUG] Absolute path doesn't exist")
            else:
                print(f"[DEBUG] Relative path: {file_path_obj}")
                print(f"[DEBUG] Current directory: {Path.cwd()}")
            return 0

        try:
            with open(file_path_obj, "r", encoding="utf-8") as f:
                lines = f.readlines()

            fixed_count = 0
            for line_num in sorted(set(line_numbers)):
                if 1 <= line_num <= len(lines):
                    idx = line_num - 1  # Convert to 0-indexed
                    original = lines[idx]
                    fixed = original.rstrip() + "\n" if original.endswith("\n") else original.rstrip()
                    
                    if original != fixed:
                        lines[idx] = fixed
                        fixed_count += 1
                        print(f"  Fixed line {line_num}: removed {len(original) - len(fixed)} trailing spaces")

            if fixed_count > 0:
                with open(file_path_obj, "w", encoding="utf-8") as f:
                    f.writelines(lines)

            return fixed_count

        except Exception as e:
            print(f"[ERROR] Failed to fix {file_path_obj}: {e}")
            return 0

    def fix_all_trailing_spaces(self) -> int:
        """
        Run ansible-lint on all targets and fix trailing spaces errors.

        Returns:
            Total number of lines fixed across all targets
        """
        if not self.targets:
            print(f"[WARNING] No valid targets found in {self.target_path}")
            return 0
        
        total_fixed = 0
        target_type_label = "roles" if self.target_type == "roles_dir" else "playbooks"
        
        print(f"Found {len(self.targets)} {target_type_label} to process")
        
        for idx, lint_target in enumerate(self.targets, 1):
            print(f"\n--- {idx}/{len(self.targets)}: {lint_target.name} ---")
            
            returncode, output = self.run_ansible_lint(lint_target)

            if returncode == 0:
                print("[OK] No ansible-lint errors found")
                continue

            # Parse trailing spaces errors
            errors = self.parse_trailing_spaces_errors(output, lint_target)

            if not errors:
                print("No trailing spaces errors found")
                continue

            # Group errors by file
            files_to_fix = {}
            for file_path, line_num in errors:
                file_path_str = str(file_path)
                if file_path_str not in files_to_fix:
                    files_to_fix[file_path_str] = []
                files_to_fix[file_path_str].append(line_num)

            # Fix each file
            print(f"Found trailing spaces errors in {len(files_to_fix)} file(s):")
            for file_path, line_numbers in files_to_fix.items():
                print(f"\n{file_path} ({len(line_numbers)} line(s)):")
                fixed = self.fix_trailing_spaces_in_file(file_path, line_numbers)
                total_fixed += fixed

        return total_fixed


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fix ansible-lint trailing whitespace errors automatically",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s ../roles              # Lint all roles in roles/ directory
  %(prog)s ../playbooks          # Lint all playbooks in playbooks/ directory
  %(prog)s ../roles ../playbooks # Lint both roles and playbooks
  
  # Dry run mode
  %(prog)s --dry-run ../roles
  
  # Verify fixes
  %(prog)s --verify ../roles ../playbooks
        """,
    )
    parser.add_argument(
        "target_paths",
        nargs="+",
        help="Path(s) to roles/ or playbooks/ directories",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fixed without making changes",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run ansible-lint again after fixing to verify",
    )

    args = parser.parse_args()

    total_fixed = 0
    failed_targets = []

    for target_path in args.target_paths:
        print(f"\n{'=' * 70}")
        print(f"Processing: {target_path}")
        print('=' * 70)

        fixer = AnsibleLintFixer(target_path)
        
        if fixer.target_type == 'unknown':
            print(f"[WARNING] '{target_path}' is not a recognized roles/ or playbooks/ directory")
            continue
        
        if not fixer.targets:
            print(f"[WARNING] No valid targets found in {target_path}")
            continue
        
        # Show what we found
        target_label = "roles" if fixer.target_type == "roles_dir" else "playbooks"
        print(f"Detected: {target_label.title()} directory with {len(fixer.targets)} {target_label}")

        if args.dry_run:
            print("\nDRY RUN MODE: No files will be modified\n")
            for lint_target in fixer.targets:
                print(f"Would lint: {lint_target.name}")
                _, output = fixer.run_ansible_lint(lint_target)
                errors = fixer.parse_trailing_spaces_errors(output, lint_target)
                if errors:
                    print(f"  Would fix {len(errors)} trailing spaces error(s)")
            continue

        # Fix trailing spaces
        fixed_count = fixer.fix_all_trailing_spaces()
        total_fixed += fixed_count

        if fixed_count > 0:
            print(f"\n[OK] Fixed {fixed_count} line(s) with trailing spaces")

            if args.verify:
                print("\nVerifying fixes with ansible-lint...")
                verify_errors = 0
                for lint_target in fixer.targets:
                    returncode, output = fixer.run_ansible_lint(lint_target)
                    errors = fixer.parse_trailing_spaces_errors(output, lint_target)
                    verify_errors += len(errors)
                
                if verify_errors > 0:
                    print(f"[WARNING] Still have {verify_errors} trailing spaces error(s)")
                    failed_targets.append(target_path)
                else:
                    print("[OK] All trailing spaces errors fixed!")
        else:
            print("\n[OK] No trailing spaces to fix")

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print('=' * 70)
    print(f"Directories processed: {len(args.target_paths)}")
    print(f"Total lines fixed: {total_fixed}")
    
    if failed_targets:
        print(f"\n[WARNING] Directories with remaining issues ({len(failed_targets)}):")
        for target in failed_targets:
            print(f"  - {target}")
        return 1
    elif total_fixed > 0:
        print("\n[OK] All fixes applied successfully!")
    else:
        print("\n[OK] No trailing spaces found!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
