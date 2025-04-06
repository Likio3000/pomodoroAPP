import os
import pyperclip
import argparse

try:
    import pathspec
except ImportError:
    pathspec = None
    print("Warning: 'pathspec' library not found. .gitignore support will be disabled.")

# --- Configuration ---

# Add file extensions you want to include (lowercase)
ALLOWED_EXTENSIONS = {
    '.py', '.js', '.jsx', '.ts', '.tsx', '.html', '.htm', '.css', '.scss', '.sass',
    '.json', '.yaml', '.yml', '.xml', '.md', '.txt', '.sh', '.bash', '.zsh',
    '.java', '.cs', '.cpp', '.c', '.h', '.hpp', '.go', '.rs', '.php', '.rb',
    '.sql', '.dockerfile', 'docker-compose.yml', '.env.example',
    '.gitignore',  # Often useful to see what's excluded
    # Configuration files but BE CAREFUL ABOUT SECRETS
    'requirements.txt', 'package.json', 'composer.json', 'pom.xml', 'gemfile'
}

# Add directory names to completely exclude
EXCLUDED_DIRS = {
    '.git', '.svn', '.hg', '__pycache__', 'node_modules', 'vendor', "egg-info",
    'target', 'build', 'dist', 'out', 'bin', 'obj', '.vscode', '.idea',
    'venv', '.env', 'env'  # Exclude common virtual environment names
}

# Add specific filenames to exclude (regardless of extension)
EXCLUDED_FILES = {
    '.env', 'credentials.json', 'secrets.yaml',
    'package-lock.json', 'yarn.lock', 'composer.lock'
}

# Maximum individual file size to include (in bytes) to prevent huge files
MAX_FILE_SIZE_BYTES = 1 * 1024 * 1024  # 1 MB limit per file (adjust as needed)


def load_gitignore(project_dir):
    """
    Load .gitignore from the project directory if available.
    Returns a compiled pathspec object or None.
    """
    gitignore_path = os.path.join(project_dir, '.gitignore')
    if os.path.exists(gitignore_path) and pathspec:
        try:
            with open(gitignore_path, 'r', encoding='utf-8', errors='ignore') as f:
                gitignore_lines = f.readlines()
            spec = pathspec.PathSpec.from_lines('gitwildmatch', gitignore_lines)
            print("Loaded .gitignore patterns.")
            return spec
        except Exception as e:
            print(f"Error loading .gitignore: {e}")
    return None


# --- Script Logic ---

def collect_project_contents(project_dir):
    """
    Collects relevant text file contents from a project directory.
    """
    all_contents = []
    project_dir = os.path.abspath(project_dir)  # Get absolute path

    if not os.path.isdir(project_dir):
        return f"Error: Directory not found: {project_dir}", False

    print(f"Scanning directory: {project_dir}")
    print("Ignoring directories:", EXCLUDED_DIRS)
    print("Ignoring files:", EXCLUDED_FILES)
    print("Including extensions:", ALLOWED_EXTENSIONS)
    print("-" * 30)

    # Load .gitignore if available
    gitignore_spec = load_gitignore(project_dir)

    total_files_scanned = 0
    included_files_count = 0
    excluded_by_type = 0
    excluded_by_name = 0
    excluded_by_dir = 0
    excluded_by_size = 0
    excluded_by_gitignore = 0
    excluded_egg_info = 0
    read_errors = 0

    for root, dirs, files in os.walk(project_dir, topdown=True):
        # Modify dirs in-place to prevent walking into excluded directories
        dirs[:] = [d for d in dirs if d.lower() not in EXCLUDED_DIRS]
        # Check if the current root itself is within an excluded path segment
        relative_root = os.path.relpath(root, project_dir)
        if any(excluded_dir in relative_root.lower().split(os.sep) for excluded_dir in EXCLUDED_DIRS if excluded_dir != '.'):
            excluded_by_dir += len(files) + len(dirs)  # Count nested items as excluded by dir
            dirs[:] = []  # Don't descend further
            continue

        for filename in files:
            total_files_scanned += 1
            file_path = os.path.join(root, filename)
            relative_path = os.path.relpath(file_path, project_dir)
            _, extension = os.path.splitext(filename)
            extension = extension.lower()

            # --- Exclusion Checks ---

            # Skip files with 'egg-info' in their filename
            if 'egg-info' in filename.lower():
                excluded_egg_info += 1
                print(f"Skipping [Egg-Info File]: {relative_path}")
                continue

            if filename.lower() in EXCLUDED_FILES:
                excluded_by_name += 1
                continue

            # Check extension (allow files with no extension if explicitly listed, e.g., Dockerfile)
            if not (extension in ALLOWED_EXTENSIONS or filename in ALLOWED_EXTENSIONS):
                excluded_by_type += 1
                continue

            # --- Gitignore Check ---
            if gitignore_spec and gitignore_spec.match_file(relative_path):
                excluded_by_gitignore += 1
                print(f"Skipping [Gitignore]: {relative_path}")
                continue

            # --- Size Check ---
            try:
                file_size = os.path.getsize(file_path)
                if file_size > MAX_FILE_SIZE_BYTES:
                    print(f"Skipping [Too Large: {file_size / 1024:.1f} KB]: {relative_path}")
                    excluded_by_size += 1
                    continue
                if file_size == 0:
                    print(f"Including [Empty File]: {relative_path}")
            except OSError as e:
                print(f"Error getting size for {relative_path}: {e}")
                read_errors += 1
                continue

            # --- Read File Content ---
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                header = f"--- START FILE: {relative_path} ---\n"
                footer = f"\n--- END FILE: {relative_path} ---\n\n"
                all_contents.append(header + content + footer)
                included_files_count += 1

            except Exception as e:
                print(f"Error reading file {relative_path}: {e}")
                read_errors += 1

    # --- Summary ---
    print("-" * 30)
    print("Scan Summary:")
    print(f"  Total items scanned (approx): {total_files_scanned}")
    print(f"  Files included: {included_files_count}")
    print(f"  Files excluded (wrong type/ext): {excluded_by_type}")
    print(f"  Files excluded (specific name): {excluded_by_name}")
    print(f"  Files/Dirs excluded (in excluded dir): {excluded_by_dir}")
    print(f"  Files excluded (too large): {excluded_by_size}")
    print(f"  Files excluded by .gitignore: {excluded_by_gitignore}")
    print(f"  Files excluded (egg-info): {excluded_egg_info}")
    print(f"  File read errors: {read_errors}")
    print("-" * 30)

    if not all_contents:
        return "No relevant files found or collected.", True

    final_output = "".join(all_contents)
    return final_output, True


# --- Main Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Collect contents of text files in a project directory and copy to clipboard."
    )
    parser.add_argument("project_dir", nargs='?', default='.', help="Path to the project directory (default: current directory)")
    args = parser.parse_args()

    # Prompt user about including tests
    include_tests = input("Include tests directory in the copy? (y/n): ").strip().lower()
    if include_tests == 'n':
        EXCLUDED_DIRS.add('tests')

    output_string, success = collect_project_contents(args.project_dir)

    if success:
        try:
            pyperclip.copy(output_string)
            print(f"Collected content copied to clipboard ({len(output_string)} characters).")
            if not output_string or output_string == "No relevant files found or collected.":
                print("NOTE: The clipboard might be empty or only contain the 'no files found' message.")
            else:
                snippet = (output_string[:300] + '...') if len(output_string) > 300 else output_string
                print("\n--- Start of Clipboard Content Snippet ---")
                print(snippet)
                print("--- End of Snippet ---")

            print("\n*** SECURITY WARNING ***")
            print("Please REVIEW the clipboard contents CAREFULLY before pasting!")
            print("Ensure no sensitive data (passwords, API keys, secrets) is included.")

        except pyperclip.PyperclipException as e:
            print(f"\nError: Could not copy to clipboard: {e}")
            print("The output may be too large for the clipboard.")
        except Exception as e:
            print(f"\nAn unexpected error occurred during clipboard copy: {e}")
    else:
        print(output_string)
