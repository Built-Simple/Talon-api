#!/usr/bin/env python3
"""
Talon API - Now with Smart Auto-Fix Capability
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import re
import os
from datetime import datetime
import logging

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory usage tracking
user_db = {}

# Python built-ins and common functions
PYTHON_BUILTINS = {
    'True', 'False', 'None', 'print', 'len', 'str', 'int', 'float', 'bool',
    'list', 'dict', 'set', 'tuple', 'range', 'sum', 'min', 'max', 'abs',
    'round', 'sorted', 'reversed', 'enumerate', 'zip', 'map', 'filter',
    'any', 'all', 'open', 'input', 'type', 'isinstance', 'hasattr',
    'getattr', 'setattr', 'delattr', 'callable', 'iter', 'next',
    'Exception', 'ValueError', 'TypeError', 'KeyError', 'IndexError'
}

@app.route('/')
def home():
    return jsonify({
        'service': 'Talon Error Prevention API',
        'version': '3.0.0',
        'features': ['error_detection', 'smart_auto_fix', 'context_aware'],
        'status': 'healthy'
    })

@app.route('/v1/analyze', methods=['POST', 'OPTIONS'])
def analyze_code():
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        data = request.json or {}
        code = data.get('code', '')
        fix_errors = data.get('fix_errors', False)
        
        if not code:
            return jsonify({'error': 'No code provided'}), 400
        
        # Rate limiting
        user_id = request.remote_addr
        current_month = datetime.now().strftime('%Y-%m')
        user_key = f"{user_id}:{current_month}"
        
        if user_key not in user_db:
            user_db[user_key] = 0
            
        if user_db[user_key] >= 100:
            auth = request.headers.get('Authorization')
            if not auth:
                return jsonify({
                    'error': 'Free tier limit reached',
                    'upgrade_url': 'https://marketplace.visualstudio.com/items?itemName=talon.error-prevention'
                }), 429
        
        user_db[user_key] += 1
        
        # Detect errors with context-aware analysis
        context = analyze_code_context(code)
        errors = detect_errors_with_context(code, context)
        
        # Apply fixes if requested
        fixed_code = code
        if fix_errors and errors:
            fixed_code = apply_smart_fixes(code, errors, context)
        
        return jsonify({
            'errors': errors,
            'analyzed_lines': len(code.split('\n')),
            'tier': 'free',
            'usage': user_db[user_key],
            'fixed_code': fixed_code if fix_errors else None,
            'fixes_applied': len(errors) if fix_errors else 0
        })
        
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return jsonify({'error': 'Analysis failed'}), 500

def analyze_code_context(code):
    """Analyze code to understand context"""
    context = {
        'defined_vars': set(),
        'imported_modules': set(),
        'functions': set(),
        'classes': set(),
        'loop_vars': {},  # line -> set of vars
        'function_params': {},  # function_name -> params
        'imports': {}  # module -> line
    }
    
    lines = code.split('\n')
    current_indent = 0
    in_function = None
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
            
        # Track indentation
        indent = len(line) - len(line.lstrip())
        
        # Import statements
        import_match = re.match(r'^import\s+(\w+)', stripped)
        if import_match:
            module = import_match.group(1)
            context['imported_modules'].add(module)
            context['imports'][module] = i
            
        from_import = re.match(r'^from\s+(\w+)\s+import\s+(.+)', stripped)
        if from_import:
            module = from_import.group(1)
            imports = from_import.group(2).split(',')
            context['imported_modules'].add(module)
            for imp in imports:
                context['defined_vars'].add(imp.strip())
        
        # Function definitions
        func_match = re.match(r'^def\s+(\w+)\s*\((.*?)\):', stripped)
        if func_match:
            func_name = func_match.group(1)
            params = func_match.group(2)
            context['functions'].add(func_name)
            context['defined_vars'].add(func_name)
            in_function = func_name
            
            # Parse parameters
            if params:
                param_list = []
                for param in params.split(','):
                    param = param.strip()
                    if '=' in param:
                        param = param.split('=')[0].strip()
                    if param and param != 'self':
                        param_list.append(param)
                        context['defined_vars'].add(param)
                context['function_params'][func_name] = param_list
        
        # Class definitions
        class_match = re.match(r'^class\s+(\w+)', stripped)
        if class_match:
            class_name = class_match.group(1)
            context['classes'].add(class_name)
            context['defined_vars'].add(class_name)
        
        # For loops
        for_match = re.match(r'^for\s+(\w+)\s+in\s+', stripped)
        if for_match:
            loop_var = for_match.group(1)
            context['defined_vars'].add(loop_var)
            if i not in context['loop_vars']:
                context['loop_vars'][i] = set()
            context['loop_vars'][i].add(loop_var)
        
        # Variable assignments
        assign_match = re.match(r'^(\w+)\s*=', stripped)
        if assign_match:
            var_name = assign_match.group(1)
            context['defined_vars'].add(var_name)
        
        # Multiple assignments
        multi_assign = re.match(r'^([^=]+)=', stripped)
        if multi_assign:
            left_side = multi_assign.group(1)
            # Handle tuple unpacking
            if ',' in left_side:
                for var in left_side.split(','):
                    var = var.strip()
                    if var and var.isidentifier():
                        context['defined_vars'].add(var)
    
    return context

def detect_errors_with_context(code, context):
    """Detect errors using context information"""
    errors = []
    lines = code.split('\n')
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        
        # Import errors
        import_match = re.match(r'^(\s*)import\s+(\w+)', line)
        if import_match:
            indent, module = import_match.groups()
            if module in ['pandas', 'numpy', 'requests', 'matplotlib', 'seaborn', 'scipy', 'sklearn']:
                errors.append({
                    'type': 'ModuleNotFoundError',
                    'message': f"Module '{module}' might not be installed",
                    'line': i,
                    'column': len(indent),
                    'prevention': f"Use 'pip install {module}'",
                    'fix': {
                        'type': 'add_comment',
                        'line': i,
                        'new_line': f"{line}  # Run: pip install {module}"
                    }
                })
        
        # None attribute access
        none_attr_match = re.search(r'(\w+)\.(\w+)', line)
        if none_attr_match:
            var, attr = none_attr_match.groups()
            # Only check if variable is explicitly set to None
            if any(f"{var} = None" in prev_line for prev_line in lines[:i]):
                errors.append({
                    'type': 'AttributeError',
                    'message': f"'{var}' might be None",
                    'line': i,
                    'column': line.index(var),
                    'prevention': 'Check if object is None first',
                    'fix': {
                        'type': 'wrap_with_check',
                        'line': i,
                        'var': var,
                        'original': line
                    }
                })
        
        # Undefined variables - SMART detection
        # Find all variable references in the line
        var_refs = re.findall(r'\b([a-zA-Z_]\w*)\b', line)
        
        for var in var_refs:
            # Skip if it's a known entity
            if (var in context['defined_vars'] or
                var in context['imported_modules'] or
                var in context['functions'] or
                var in context['classes'] or
                var in PYTHON_BUILTINS):
                continue
            
            # Skip if it's a method call (preceded by .)
            if re.search(rf'\.{var}\b', line):
                continue
            
            # Skip if it's a function/class definition
            if re.match(rf'^(def|class)\s+{var}', stripped):
                continue
            
            # Skip if it's being defined in this line
            if re.match(rf'^{var}\s*=', stripped) or re.match(rf'^for\s+{var}\s+in', stripped):
                continue
            
            # Skip if it's in quotes (string)
            if re.search(rf'["\'].*{var}.*["\']', line):
                continue
            
            # This is likely an undefined variable
            errors.append({
                'type': 'NameError',
                'message': f"'{var}' is not defined",
                'line': i,
                'column': line.index(var) if var in line else 0,
                'prevention': 'Define variable before use',
                'fix': {
                    'type': 'define_variable',
                    'line': i,
                    'var': var
                }
            })
            break  # Only report first undefined var per line
        
        # Division by zero
        div_match = re.search(r'/\s*(\w+|\d+)', line)
        if div_match:
            divisor = div_match.group(1)
            if divisor == '0' or any(f"{divisor} = 0" in prev_line for prev_line in lines[:i]):
                errors.append({
                    'type': 'ZeroDivisionError',
                    'message': "Possible division by zero",
                    'line': i,
                    'column': line.index('/'),
                    'prevention': 'Check divisor before division',
                    'fix': {
                        'type': 'wrap_division',
                        'line': i,
                        'original': line
                    }
                })
        
        # File operations
        file_match = re.search(r'open\s*\(\s*[\'"]([^\'"]+)[\'"]', line)
        if file_match:
            filename = file_match.group(1)
            errors.append({
                'type': 'FileNotFoundError',
                'message': f"File '{filename}' might not exist",
                'line': i,
                'column': line.index('open'),
                'prevention': 'Check file exists before opening',
                'fix': {
                    'type': 'safe_file_open',
                    'line': i,
                    'filename': filename
                }
            })
    
    return errors

def apply_smart_fixes(code, errors, context):
    """Apply fixes intelligently using context"""
    lines = code.split('\n')
    
    # Track what we've added to avoid duplicates
    added_imports = set()
    defined_vars = set()
    
    # Sort errors by line number in reverse order
    errors_by_line = sorted(errors, key=lambda x: x['line'], reverse=True)
    
    for error in errors_by_line:
        fix = error.get('fix')
        if not fix:
            continue
            
        line_num = error['line']
        
        if fix['type'] == 'add_comment':
            lines[line_num] = fix['new_line']
            
        elif fix['type'] == 'wrap_with_check':
            # Smart None check that preserves indentation
            var = fix['var']
            original_line = lines[line_num]
            indent = len(original_line) - len(original_line.lstrip())
            indent_str = ' ' * indent
            
            new_lines = [
                f"{indent_str}if {var} is not None:",
                f"{indent_str}    {original_line.strip()}",
                f"{indent_str}else:",
                f"{indent_str}    print(f'Error: {var} is None')"
            ]
            lines[line_num:line_num+1] = new_lines
            
        elif fix['type'] == 'define_variable':
            # Only add if not already defined
            var = fix['var']
            if var not in defined_vars and var not in context['defined_vars']:
                # Find appropriate place to insert
                insert_line = find_insertion_point(lines, line_num)
                indent = get_line_indent(lines[line_num])
                lines.insert(insert_line, f"{' ' * indent}{var} = None  # TODO: Initialize this variable")
                defined_vars.add(var)
            
        elif fix['type'] == 'wrap_division':
            original_line = lines[line_num]
            indent = len(original_line) - len(original_line.lstrip())
            indent_str = ' ' * indent
            
            new_lines = [
                f"{indent_str}try:",
                f"{indent_str}    {original_line.strip()}",
                f"{indent_str}except ZeroDivisionError:",
                f"{indent_str}    result = 0  # Handle division by zero"
            ]
            lines[line_num:line_num+1] = new_lines
            
        elif fix['type'] == 'safe_file_open':
            # Add os import if needed
            if 'os' not in context['imported_modules'] and 'os' not in added_imports:
                lines.insert(0, 'import os')
                added_imports.add('os')
            
            original_line = lines[line_num]
            indent = len(original_line) - len(original_line.lstrip())
            indent_str = ' ' * indent
            
            safe_lines = [
                f"{indent_str}if os.path.exists('{fix['filename']}'):",
                f"{indent_str}    {original_line.strip()}",
                f"{indent_str}else:",
                f"{indent_str}    print(f'File not found: {fix['filename']}')"
            ]
            lines[line_num:line_num+1] = safe_lines
    
    return '\n'.join(lines)

def find_insertion_point(lines, error_line):
    """Find appropriate place to insert variable definition"""
    # Look backwards for the start of the current block
    current_indent = get_line_indent(lines[error_line])
    
    for i in range(error_line - 1, -1, -1):
        line = lines[i]
        if not line.strip():
            continue
            
        line_indent = get_line_indent(line)
        
        # If we find a line with less indentation, insert after it
        if line_indent < current_indent:
            return i + 1
            
        # If we find a function/class definition at same level, insert after it
        if line_indent == current_indent and re.match(r'^(def|class)\s+', line.strip()):
            return i + 1
    
    # Default: insert at beginning
    return 0

def get_line_indent(line):
    """Get indentation level of a line"""
    return len(line) - len(line.lstrip())

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)