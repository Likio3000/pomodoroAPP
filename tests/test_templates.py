import os

def test_all_templates_load(test_app):
    templates_dir = os.path.join(test_app.root_path, test_app.template_folder)
    loaded = []
    for root, _, files in os.walk(templates_dir):
        for file in files:
            if file.endswith('.html'):
                rel_path = os.path.relpath(os.path.join(root, file), templates_dir)
                template_name = rel_path.replace(os.sep, '/')
                loaded.append(template_name)
                test_app.jinja_env.get_template(template_name)
    assert '400_csrf.html' in loaded
