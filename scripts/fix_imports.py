import os
import re

def fix_imports_in_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # Patrones a reemplazar
    patterns = [
        (r'^from config import', 'from backend.config import'),
        (r'^from api import', 'from backend.api import'),
        (r'^from api\.', 'from backend.api.'),
        (r'^from mavlink import', 'from backend.mavlink import'),
        (r'^from mavlink\.', 'from backend.mavlink.'),
        (r'^from db import', 'from backend.db import'),
        (r'^from db\.', 'from backend.db.'),
        (r'^from schemas import', 'from backend.schemas import'),
        (r'^from schemas\.', 'from backend.schemas.'),
    ]
    
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'✅ Fixed: {filepath}')
        return True
    return False

def fix_all_imports(directory):
    fixed_count = 0
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                if fix_imports_in_file(filepath):
                    fixed_count += 1
    
    print(f'\n🎉 Fixed {fixed_count} files')

if __name__ == '__main__':
    fix_all_imports('backend')
