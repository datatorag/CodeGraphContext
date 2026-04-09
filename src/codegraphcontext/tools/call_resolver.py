"""Per-language CALLS edge resolution.

Precision over recall: the graph supplements Claude Code (which can grep
to fill gaps). We only create CALLS edges we're confident about — false
positives waste tokens by sending Claude down wrong paths.

Each language subclass defines:
- SELF_KEYWORDS: self-reference keywords (self/cls for Python, this for JS)
- BUILTIN_NAMES: names to skip (builtins, stdlib globals)
- IMPORT_PATH_KEY: which import dict key holds the module path
- _resolve_dotted_call(): language-specific module.func() resolution
"""

import builtins
from typing import Dict, Optional


class BaseCallResolver:
    """Shared resolution framework. Subclasses override language-specific behavior."""

    SELF_KEYWORDS: frozenset = frozenset()
    BUILTIN_NAMES: frozenset = frozenset()
    MIN_NAME_LENGTH: int = 3  # skip <=2 char names (minified JS artifacts)
    IMPORT_PATH_KEY: str = 'full_import_name'  # key in import dicts for module path

    def build_local_imports(self, imports: list) -> dict:
        """Build {alias_or_name: import_path} from a file's import list.

        Override for languages with different import dict structures.
        """
        result = {}
        for imp in imports:
            key = imp.get('alias') or imp['name'].split('.')[-1]
            value = imp.get(self.IMPORT_PATH_KEY, imp.get('source', imp['name']))
            result[key] = value
        return result

    def resolve(self, call: Dict, caller_file_path: str, local_names: set,
                local_imports: dict, imports_map: dict,
                skip_external: bool) -> Optional[Dict]:
        """Resolve a single function call to its target.

        Returns a result dict or None if the call can't be confidently resolved.
        """
        called_name = call['name']

        # Skip builtins and very short names
        if called_name in self.BUILTIN_NAMES or len(called_name) < self.MIN_NAME_LENGTH:
            return None

        full_call = call.get('full_name', called_name)
        base_obj = full_call.split('.')[0] if '.' in full_call else None
        is_dotted = base_obj is not None
        is_self_call = base_obj in self.SELF_KEYWORDS
        dot_count = full_call.count('.') if is_dotted else 0

        resolved_path = None

        # Rule 1: self/this/super.method() → same file
        # Only single-dot (self.method), not chained (self.attr.method)
        if is_self_call and dot_count == 1:
            resolved_path = caller_file_path

        # Rule 2: Direct call func() where func is defined in this file
        elif not is_dotted and called_name in local_names:
            resolved_path = caller_file_path

        # Rule 3: Direct call func() where func is imported
        elif not is_dotted and called_name in local_imports:
            resolved_path = self._resolve_imported_call(
                called_name, local_imports, imports_map
            )

        # Rule 4: module.func() where module is imported (single dot only)
        elif (is_dotted and not is_self_call
              and base_obj in local_imports and dot_count == 1):
            resolved_path = self._resolve_dotted_call(
                called_name, base_obj, full_call, local_imports, imports_map
            )

        if not resolved_path:
            return None

        if skip_external and resolved_path != caller_file_path:
            if called_name not in local_imports and called_name not in local_names:
                return None

        return self._format_result(call, caller_file_path, resolved_path)

    def _resolve_imported_call(self, called_name: str, local_imports: dict,
                               imports_map: dict) -> Optional[str]:
        """Rule 3: Resolve a directly-imported function call."""
        import_path = local_imports[called_name]

        # 3a. Try full import path as key in imports_map
        if import_path in imports_map:
            paths = imports_map[import_path]
            if len(paths) == 1:
                return paths[0]

        # 3b. Match by name, filter by module path fragment
        possible_paths = imports_map.get(called_name, [])
        module_path = self._import_path_to_fs_fragment(import_path)
        if module_path:
            for p in possible_paths:
                if module_path in p:
                    return p

        # 3c. Unambiguous: name defined in exactly one file
        if len(possible_paths) == 1:
            return possible_paths[0]

        return None

    def _resolve_dotted_call(self, called_name: str, base_obj: str,
                             full_call: str, local_imports: dict,
                             imports_map: dict) -> Optional[str]:
        """Rule 4: Resolve module.func() where module is imported.

        Override per language for different import path conventions.
        """
        import_path = local_imports[base_obj]
        module_fragment = self._import_path_to_fs_fragment(import_path)
        if not module_fragment:
            return None

        candidate_paths = imports_map.get(called_name, [])

        # 4a. Find called_name in files under the imported module's path
        for p in candidate_paths:
            if module_fragment in p:
                return p

        # 4b. Match module's last component (package name)
        module_last = module_fragment.split('/')[-1]
        matches = [p for p in candidate_paths if module_last in p]
        if len(matches) == 1:
            return matches[0]

        # 4c. Unambiguous (1 definition) and base is imported
        if len(candidate_paths) == 1:
            return candidate_paths[0]

        return None

    def _import_path_to_fs_fragment(self, import_path: str) -> Optional[str]:
        """Convert an import path to a filesystem path fragment for matching.

        Python: 'webapp.services.user.authenticate' → 'webapp/services/user'
        (strips the function/class name to get the module directory)

        Override for languages with different conventions (JS relative paths, Go packages).
        """
        fs_path = import_path.replace('.', '/')
        parts = fs_path.rsplit('/', 1)
        return parts[0] if len(parts) > 1 else fs_path

    def _format_result(self, call: Dict, caller_file_path: str,
                       resolved_path: str) -> Dict:
        """Build the result dict consumed by _create_all_function_calls."""
        called_name = call['name']
        caller_context = call.get('context')

        if caller_context and len(caller_context) == 3 and caller_context[0] is not None:
            caller_name, _, caller_line_number = caller_context
            return {
                'type': 'function',
                'caller_name': caller_name,
                'caller_file_path': caller_file_path,
                'caller_line_number': caller_line_number,
                'called_name': called_name,
                'called_file_path': resolved_path,
                'line_number': call['line_number'],
                'args': call.get('args', []),
                'full_call_name': call.get('full_name', called_name),
            }
        else:
            return {
                'type': 'file',
                'caller_file_path': caller_file_path,
                'called_name': called_name,
                'called_file_path': resolved_path,
                'line_number': call['line_number'],
                'args': call.get('args', []),
                'full_call_name': call.get('full_name', called_name),
            }


# ---------------------------------------------------------------------------
# Language-specific resolvers
# ---------------------------------------------------------------------------

class PythonCallResolver(BaseCallResolver):
    SELF_KEYWORDS = frozenset({'self', 'cls', 'super', 'super()'})
    BUILTIN_NAMES = frozenset(dir(builtins))
    IMPORT_PATH_KEY = 'full_import_name'


class JavaScriptCallResolver(BaseCallResolver):
    """For JavaScript and TypeScript."""
    SELF_KEYWORDS = frozenset({'this', 'super'})
    BUILTIN_NAMES = frozenset({
        'console', 'Math', 'JSON', 'Object', 'Array', 'Promise', 'Error',
        'Date', 'RegExp', 'Map', 'Set', 'WeakMap', 'WeakSet', 'Number',
        'String', 'Boolean', 'Symbol', 'BigInt', 'parseInt', 'parseFloat',
        'setTimeout', 'setInterval', 'clearTimeout', 'clearInterval',
        'fetch', 'alert', 'confirm', 'require', 'module', 'exports',
        'process', 'Buffer', 'global', 'globalThis', 'window', 'document',
        'undefined', 'NaN', 'Infinity',
    })
    IMPORT_PATH_KEY = 'source'

    def _import_path_to_fs_fragment(self, import_path: str) -> Optional[str]:
        """JS imports use relative paths like './utils' or package names like 'react'.

        Strip leading './' and return the path for matching against file paths.
        """
        path = import_path.lstrip('./')
        # For bare package names (no path separator), return as-is
        return path if path else None


class GoCallResolver(BaseCallResolver):
    """For Go. No self/this keywords. Always package.Func() pattern."""
    SELF_KEYWORDS = frozenset()  # Go has no self/this
    BUILTIN_NAMES = frozenset({
        'len', 'cap', 'make', 'new', 'append', 'copy', 'close', 'delete',
        'panic', 'recover', 'print', 'println', 'complex', 'real', 'imag',
        'clear', 'min', 'max', 'error',
    })
    IMPORT_PATH_KEY = 'source'

    def build_local_imports(self, imports: list) -> dict:
        """Go imports: name is last path component, source is full package path."""
        result = {}
        for imp in imports:
            # Go parser sets name = last component (e.g., 'fmt' from 'fmt')
            key = imp.get('alias') or imp.get('name', '')
            value = imp.get('source', imp.get('name', ''))
            if key:
                result[key] = value
        return result

    def _import_path_to_fs_fragment(self, import_path: str) -> Optional[str]:
        """Go import paths map directly to directory structure."""
        return import_path if import_path else None


class JVMCallResolver(BaseCallResolver):
    """For Java, Kotlin, Scala. Uses this/super, dotted import paths."""
    SELF_KEYWORDS = frozenset({'this', 'super'})
    BUILTIN_NAMES = frozenset({
        'System', 'String', 'Integer', 'Boolean', 'Double', 'Float',
        'Object', 'Math', 'Collections', 'Arrays', 'Thread', 'Runnable',
        'Override', 'Deprecated',
    })
    IMPORT_PATH_KEY = 'full_import_name'


class GenericCallResolver(BaseCallResolver):
    """Conservative fallback for languages without specific resolvers.

    Only resolves same-file calls and directly imported names.
    Rule 4 (dotted calls) is disabled — too risky without language knowledge.
    """
    SELF_KEYWORDS = frozenset({'self', 'this', 'super'})
    BUILTIN_NAMES = frozenset()
    IMPORT_PATH_KEY = 'full_import_name'

    def build_local_imports(self, imports: list) -> dict:
        """Try full_import_name first, fall back to source, then name."""
        result = {}
        for imp in imports:
            key = imp.get('alias') or imp['name'].split('.')[-1]
            value = (imp.get('full_import_name')
                     or imp.get('source')
                     or imp['name'])
            result[key] = value
        return result

    def _resolve_dotted_call(self, called_name, base_obj, full_call,
                             local_imports, imports_map):
        """Disabled for generic resolver — too risky without language knowledge."""
        return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_RESOLVER_MAP = {
    'python': PythonCallResolver,
    'javascript': JavaScriptCallResolver,
    'typescript': JavaScriptCallResolver,
    'go': GoCallResolver,
    'java': JVMCallResolver,
    'kotlin': JVMCallResolver,
    'scala': JVMCallResolver,
}

_RESOLVER_CACHE: dict = {}


def get_resolver(lang: str) -> BaseCallResolver:
    """Get a cached resolver instance for the given language."""
    if lang not in _RESOLVER_CACHE:
        cls = _RESOLVER_MAP.get(lang, GenericCallResolver)
        _RESOLVER_CACHE[lang] = cls()
    return _RESOLVER_CACHE[lang]
