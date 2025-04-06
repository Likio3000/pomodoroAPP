import os
import pyperclip
import argparse

# --- Configuration ---

# Add file extensions you want to include (lowercase)
ALLOWED_EXTENSIONS = {
    '.py', '.js', '.jsx', '.ts', '.tsx', '.html', '.htm', '.css', '.scss', '.sass',
    '.json', '.yaml', '.yml', '.xml', '.md', '.txt', '.sh', '.bash', '.zsh',
    '.java', '.cs', '.cpp', '.c', '.h', '.hpp', '.go', '.rs', '.php', '.rb',
    '.sql', '.dockerfile', 'docker-compose.yml', '.env.example', # Add more as needed
    '.gitignore', # Often useful to see what's excluded
    # Add configuration files but BE CAREFUL ABOUT SECRETS
    'requirements.txt', 'package.json', 'composer.json', 'pom.xml', 'gemfile'
}

# Add directory names to completely exclude
EXCLUDED_DIRS = {
    '.git', '.svn', '.hg', '__pycache__', 'node_modules', 'vendor',
    'target', 'build', 'dist', 'out', 'bin', 'obj', '.vscode', '.idea',
    'venv', '.env', 'env' # Exclude common virtual environment names
    # Add others like 'logs', 'temp', 'coverage', etc. if needed
}

# Add specific filenames to exclude (regardless of extension)
EXCLUDED_FILES = {
    '.env', 'credentials.json', 'secrets.yaml', # Add known sensitive files
    'package-lock.json', 'yarn.lock', 'composer.lock' # Lock files are usually very large
}

# Maximum individual file size to include (in bytes) to prevent huge files
MAX_FILE_SIZE_BYTES = 1 * 1024 * 1024 # 1 MB limit per file (adjust as needed)


# --- Script Logic ---

def collect_project_contents(project_dir):
    """
    Collects relevant text file contents from a project directory.
    """
    all_contents = []
    project_dir = os.path.abspath(project_dir) # Get absolute path

    if not os.path.isdir(project_dir):
        return f"Error: Directory not found: {project_dir}", False

    print(f"Scanning directory: {project_dir}")
    print("Ignoring directories:", EXCLUDED_DIRS)
    print("Ignoring files:", EXCLUDED_FILES)
    print("Including extensions:", ALLOWED_EXTENSIONS)
    print("-" * 30)

    total_files_scanned = 0
    included_files_count = 0
    excluded_by_type = 0
    excluded_by_name = 0
    excluded_by_dir = 0
    excluded_by_size = 0
    read_errors = 0

    for root, dirs, files in os.walk(project_dir, topdown=True):
        # Modify dirs in-place to prevent walking into excluded directories
        dirs[:] = [d for d in dirs if d.lower() not in EXCLUDED_DIRS]
        # Check if the current root itself is within an excluded path segment
        relative_root = os.path.relpath(root, project_dir)
        if any(excluded_dir in relative_root.lower().split(os.sep) for excluded_dir in EXCLUDED_DIRS if excluded_dir != '.'):
             excluded_by_dir += len(files) + len(dirs) # Count nested items as excluded by dir
             dirs[:] = [] # Don't descend further
             continue


        for filename in files:
            total_files_scanned += 1
            file_path = os.path.join(root, filename)
            relative_path = os.path.relpath(file_path, project_dir)
            _, extension = os.path.splitext(filename)
            extension = extension.lower()

            # --- Exclusion Checks ---
            if filename.lower() in EXCLUDED_FILES:
                # print(f"Skipping [Excluded Name]: {relative_path}")
                excluded_by_name += 1
                continue

            # Check extension (allow files with no extension if explicitly listed, e.g., Dockerfile)
            if not (extension in ALLOWED_EXTENSIONS or filename in ALLOWED_EXTENSIONS):
                # print(f"Skipping [Wrong Type]: {relative_path}")
                excluded_by_type += 1
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
                   # Decide if you want to include empty files, here we do.
            except OSError as e:
                print(f"Error getting size for {relative_path}: {e}")
                read_errors += 1
                continue


            # --- Read File Content ---
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                # Add header and content
                header = f"--- START FILE: {relative_path} ---\n"
                footer = f"\n--- END FILE: {relative_path} ---\n\n"
                all_contents.append(header + content + footer)
                included_files_count += 1
                # print(f"Including: {relative_path}")

            except Exception as e:
                print(f"Error reading file {relative_path}: {e}")
                read_errors += 1
                # Optionally add a marker for files that couldn't be read
                # all_contents.append(f"--- ERROR READING FILE: {relative_path} ({e}) ---\n\n")

    # --- Summary ---
    print("-" * 30)
    print(f"Scan Summary:")
    print(f"  Total items scanned (approx): {total_files_scanned}")
    print(f"  Files included: {included_files_count}")
    print(f"  Files excluded (wrong type/ext): {excluded_by_type}")
    print(f"  Files excluded (specific name): {excluded_by_name}")
    print(f"  Files/Dirs excluded (in excluded dir): {excluded_by_dir}")
    print(f"  Files excluded (too large): {excluded_by_size}")
    print(f"  File read errors: {read_errors}")
    print("-" * 30)


    if not all_contents:
        return "No relevant files found or collected.", True # True indicates success, just no files

    final_output = "".join(all_contents)
    return final_output, True


# --- Main Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect contents of text files in a project directory and copy to clipboard.")
    parser.add_argument("project_dir", nargs='?', default='.', help="Path to the project directory (default: current directory)")
    args = parser.parse_args()

    output_string, success = collect_project_contents(args.project_dir)

    if success:
        try:
            pyperclip.copy(output_string)
            print(f"Collected content copied to clipboard ({len(output_string)} characters).")
            if not output_string or output_string == "No relevant files found or collected.":
                 print("NOTE: The clipboard might be empty or only contain the 'no files found' message.")
            else:
                 # Show a snippet
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
            print("Consider saving the output to a file instead.")
            # Optionally, you could add logic here to save to a file if clipboard fails
            # with open("project_contents.txt", "w", encoding="utf-8") as outfile:
            #     outfile.write(output_string)
            # print("Output saved to project_contents.txt")
        except Exception as e:
            print(f"\nAn unexpected error occurred during clipboard copy: {e}")
    else:
        # Output contains the error message from the function
        print(output_string)
