"""yunta/adapters.py — Adaptadores por lenguaje con carga bajo demanda (Lazy-Loading).

Proporciona parsers de símbolos y validadores sintácticos para múltiples
lenguajes (Python, JS/TS, Go, Rust, JSON, Universal) manteniendo el
minimalismo del core y cargando cada adaptador únicamente al ser requerido."""

import ast
import json
import re
import subprocess
import tempfile
import textwrap
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Type


def _run_cli_check(cmd_args: List[str], content: str, path: str) -> Optional[str]:
    """Ejecuta una comprobación de sintaxis/compilación CLI preservando el nombre de archivo.
    Devuelve None si el compilador aprobó el archivo o si la herramienta no está instalada (fallback).
    Devuelve la salida de error si el compilador reportó un fallo sintáctico."""
    filename = Path(path).name
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_file = Path(tmpdir) / filename
        tmp_file.write_text(content, encoding="utf-8")

        try:
            cmd = [arg.replace("{file}", str(tmp_file)) for arg in cmd_args]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if res.returncode != 0:
                raw_err = (res.stderr or res.stdout or "").replace("\x00", "").strip()
                err_lower = raw_err.lower()
                if (
                    "windows subsystem for linux" in err_lower
                    or "wsl.exe" in err_lower
                    or "not recognized as an internal" in err_lower
                    or "command not found" in err_lower
                ):
                    return None
                return raw_err or f"compilación falló con código {res.returncode}"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # Fallback gracioso si la herramienta del sistema no está instalada
            pass
    return None



class LanguageAdapter(ABC):
    """Interfaz base para adaptadores de lenguaje."""


    @abstractmethod
    def validate(self, content: str, path: str = "") -> None:
        """Valida la sintaxis del contenido; lanza ValueError si es inválido."""
        pass

    @abstractmethod
    def find_symbols(self, content: str, query: str = "") -> List[dict]:
        """Devuelve una lista de símbolos matching: [{name, type, line}]."""
        pass

    @abstractmethod
    def get_outline(self, content: str) -> List[str]:
        """Devuelve una lista de líneas representando el esquema/outline."""
        pass


class UniversalAdapter(LanguageAdapter):
    """Adaptador universal fallback con validación de balance de comillas/llaves."""

    def validate(self, content: str, path: str = "") -> None:
        pares = {"(": ")", "[": "]", "{": "}"}
        cierres = {v: k for k, v in pares.items()}
        stack = []
        quote = None
        escape = False
        for ch in content:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if quote:
                if ch == quote:
                    quote = None
                continue
            if ch in ("'", '"'):
                quote = ch
            elif ch in pares:
                stack.append(ch)
            elif ch in cierres:
                if not stack or stack[-1] != cierres[ch]:
                    raise ValueError(
                        f"contenido desbalanceado: '{ch}' inesperado (¿escritura truncada?)"
                    )
                stack.pop()
        if stack:
            raise ValueError(
                f"contenido desbalanceado: '{stack[-1]}' sin cerrar (¿escritura truncada?)"
            )
        if quote == '"':
            raise ValueError('contenido desbalanceado: comilla doble sin cerrar (¿escritura truncada?)')

    def find_symbols(self, content: str, query: str = "") -> List[dict]:
        query_lower = query.lower()
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            sline = line.strip()
            if not sline or sline.startswith("//") or sline.startswith("#"):
                continue
            if query_lower in sline.lower():
                results.append({"name": sline[:60], "type": "text", "line": idx})
        return results

    def get_outline(self, content: str) -> List[str]:
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            sline = line.strip()
            if sline.startswith("#") or sline.startswith("//") or sline.startswith("/*"):
                results.append(f"L{idx}: {sline}")
        return results


class PythonAdapter(LanguageAdapter):
    """Adaptador específico para Python usando py_compile y ast."""

    def validate(self, content: str, path: str = "") -> None:
        import py_compile
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
            tf.write(content)
        try:
            py_compile.compile(tf.name, doraise=True)
        except py_compile.PyCompileError as e:
            raise ValueError(f"contenido con sintaxis Python inválida: {e}") from e
        finally:
            Path(tf.name).unlink(missing_ok=True)

    def find_symbols(self, content: str, query: str = "") -> List[dict]:
        try:
            tree = ast.parse(textwrap.dedent(content.lstrip("\r\n")))
        except SyntaxError:
            return []
        query_lower = query.lower()
        results = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not query_lower or query_lower in node.name.lower():
                    kind = "class" if isinstance(node, ast.ClassDef) else "function"
                    results.append({"name": node.name, "type": kind, "line": node.lineno})
        return sorted(results, key=lambda x: x["line"])

    def _format_args(self, args: ast.arguments) -> str:
        arg_names = [a.arg for a in args.args]
        if args.vararg:
            arg_names.append(f"*{args.vararg.arg}")
        if args.kwarg:
            arg_names.append(f"**{args.kwarg.arg}")
        return ", ".join(arg_names)

    def get_outline(self, content: str) -> List[str]:
        try:
            tree = ast.parse(textwrap.dedent(content.lstrip("\r\n")))
        except SyntaxError as e:
            return [f"error de sintaxis en línea {e.lineno}: {e.msg}"]

        outline = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    names = ", ".join(alias.name for alias in node.names)
                    outline.append(f"import {names}")
                else:
                    names = ", ".join(alias.name for alias in node.names)
                    outline.append(f"from {node.module or ''} import {names}")
            elif isinstance(node, ast.ClassDef):
                bases = ", ".join(b.id for b in node.bases if isinstance(b, ast.Name))
                base_str = f"({bases})" if bases else ""
                outline.append(f"class {node.name}{base_str}")
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        args_str = self._format_args(item.args)
                        prefix = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                        outline.append(f"  {prefix} {item.name}({args_str})")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args_str = self._format_args(node.args)
                prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                outline.append(f"{prefix} {node.name}({args_str})")
        return outline


class JavaScriptTSAdapter(UniversalAdapter):
    """Adaptador para JavaScript/TypeScript (.js, .jsx, .ts, .tsx)."""

    _SYMBOL_RE = re.compile(
        r"^\s*(export\s+)?(async\s+)?(function|class|interface|type|enum)\s+([A-Za-z0-9_$]+)"
        r"|^\s*(export\s+)?(const|let|var)\s+([A-Za-z0-9_$]+)\s*=\s*(async\s*)?\("
        r"|^\s*(async\s+)?([A-Za-z0-9_$]+)\s*\([^\)]*\)\s*\{",
        re.MULTILINE,
    )

    def validate(self, content: str, path: str = "") -> None:
        super().validate(content, path)
        err = _run_cli_check(["node", "--check", "{file}"], content, path or "file.js")
        if err:
            raise ValueError(f"contenido con sintaxis JS inválida: {err}")

    def find_symbols(self, content: str, query: str = "") -> List[dict]:
        query_lower = query.lower()
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            match = self._SYMBOL_RE.search(line)
            if match:
                groups = match.groups()
                name = groups[3] or groups[6] or groups[9]
                kind = groups[2] or groups[5] or "method"
                if name and (not query_lower or query_lower in name.lower()):
                    results.append({"name": name, "type": kind, "line": idx})
        return results

    def get_outline(self, content: str) -> List[str]:
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            match = self._SYMBOL_RE.search(line)
            if match:
                results.append(f"L{idx}: {line.strip()}")
        return results


class GoAdapter(UniversalAdapter):
    """Adaptador para Go (.go)."""

    _GO_RE = re.compile(
        r"^\s*func\s+(\([^\)]+\)\s+)?([A-Za-z0-9_]+)|^\s*type\s+([A-Za-z0-9_]+)\s+(struct|interface)",
        re.MULTILINE,
    )

    def validate(self, content: str, path: str = "") -> None:
        super().validate(content, path)
        err = _run_cli_check(["go", "vet", "{file}"], content, path or "main.go")
        if err:
            raise ValueError(f"contenido con sintaxis Go inválida: {err}")

    def find_symbols(self, content: str, query: str = "") -> List[dict]:
        query_lower = query.lower()
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            match = self._GO_RE.search(line)
            if match:
                groups = match.groups()
                name = groups[1] or groups[2]
                kind = "func" if groups[1] else (groups[3] or "type")
                if name and (not query_lower or query_lower in name.lower()):
                    results.append({"name": name, "type": kind, "line": idx})
        return results

    def get_outline(self, content: str) -> List[str]:
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            match = self._GO_RE.search(line)
            if match:
                results.append(f"L{idx}: {line.strip()}")
        return results


class RustAdapter(UniversalAdapter):
    """Adaptador para Rust (.rs)."""

    _RUST_RE = re.compile(
        r"^\s*(pub\s+)?(fn|struct|enum|trait|impl)\s+([A-Za-z0-9_]+)",
        re.MULTILINE,
    )

    def validate(self, content: str, path: str = "") -> None:
        super().validate(content, path)
        err = _run_cli_check(["rustc", "--parse-only", "{file}"], content, path or "main.rs")
        if err:
            raise ValueError(f"contenido con sintaxis Rust inválida: {err}")

    def find_symbols(self, content: str, query: str = "") -> List[dict]:
        query_lower = query.lower()
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            match = self._RUST_RE.search(line)
            if match:
                groups = match.groups()
                kind = groups[1]
                name = groups[2]
                if name and (not query_lower or query_lower in name.lower()):
                    results.append({"name": name, "type": kind, "line": idx})
        return results

    def get_outline(self, content: str) -> List[str]:
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            match = self._RUST_RE.search(line)
            if match:
                results.append(f"L{idx}: {line.strip()}")
        return results



class JSONAdapter(LanguageAdapter):
    """Adaptador específico para JSON (.json)."""

    def validate(self, content: str, path: str = "") -> None:
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"contenido JSON inválido: {e}") from e

    def find_symbols(self, content: str, query: str = "") -> List[dict]:
        try:
            data = json.loads(content)
        except Exception:
            return []
        query_lower = query.lower()
        results = []
        if isinstance(data, dict):
            for k in data.keys():
                if not query_lower or query_lower in k.lower():
                    results.append({"name": k, "type": "key", "line": 1})
        return results

    def get_outline(self, content: str) -> List[str]:
        try:
            data = json.loads(content)
        except Exception:
            return ["JSON inválido"]
        if isinstance(data, dict):
            return [f"Key: {k}" for k in list(data.keys())[:20]]
        return [f"Array de {len(data)} elementos"] if isinstance(data, list) else ["Valor primitivo JSON"]


class JavaAdapter(UniversalAdapter):
    """Adaptador para Java (.java)."""

    _JAVA_RE = re.compile(
        r"^\s*(public|protected|private|static|final|abstract|\s)*\s*(class|interface|enum|record)\s+([A-Za-z0-9_$]+)"
        r"|^\s*(public|protected|private|static|final|\s)+\s*([A-Za-z0-9_<>\[\]]+)\s+([A-Za-z0-9_$]+)\s*\([^\)]*\)\s*\{",
        re.MULTILINE,
    )

    def validate(self, content: str, path: str = "") -> None:
        super().validate(content, path)
        err = _run_cli_check(["javac", "-d", tempfile.gettempdir(), "{file}"], content, path or "Main.java")
        if err:
            raise ValueError(f"contenido con sintaxis Java inválida: {err}")

    def find_symbols(self, content: str, query: str = "") -> List[dict]:
        query_lower = query.lower()
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            match = self._JAVA_RE.search(line)
            if match:
                groups = match.groups()
                name = groups[2] or groups[5]
                kind = groups[1] or "method"
                if name and (not query_lower or query_lower in name.lower()):
                    results.append({"name": name, "type": kind, "line": idx})
        return results

    def get_outline(self, content: str) -> List[str]:
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            match = self._JAVA_RE.search(line)
            if match:
                results.append(f"L{idx}: {line.strip()}")
        return results


class CSharpAdapter(UniversalAdapter):
    """Adaptador para .NET / C# (.cs)."""

    _CSHARP_RE = re.compile(
        r"^\s*(public|protected|private|internal|static|abstract|sealed|partial|\s)*\s*(class|interface|enum|struct|record)\s+([A-Za-z0-9_$]+)"
        r"|^\s*(public|protected|private|internal|static|async|\s)+\s*([A-Za-z0-9_<>\[\]]+)\s+([A-Za-z0-9_$]+)\s*\([^\)]*\)\s*\{",
        re.MULTILINE,
    )

    def find_symbols(self, content: str, query: str = "") -> List[dict]:
        query_lower = query.lower()
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            match = self._CSHARP_RE.search(line)
            if match:
                groups = match.groups()
                name = groups[2] or groups[5]
                kind = groups[1] or "method"
                if name and (not query_lower or query_lower in name.lower()):
                    results.append({"name": name, "type": kind, "line": idx})
        return results

    def get_outline(self, content: str) -> List[str]:
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            match = self._CSHARP_RE.search(line)
            if match:
                results.append(f"L{idx}: {line.strip()}")
        return results


class PHPAdapter(UniversalAdapter):
    """Adaptador para PHP (.php)."""

    _PHP_RE = re.compile(
        r"\b(function|class|trait|interface|enum)\s+([A-Za-z0-9_$]+)",
        re.MULTILINE,
    )

    def validate(self, content: str, path: str = "") -> None:
        super().validate(content, path)
        err = _run_cli_check(["php", "-l", "{file}"], content, path or "file.php")
        if err:
            raise ValueError(f"contenido con sintaxis PHP inválida: {err}")

    def find_symbols(self, content: str, query: str = "") -> List[dict]:
        query_lower = query.lower()
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            for match in self._PHP_RE.finditer(line):
                kind = match.group(1)
                name = match.group(2)
                if name and (not query_lower or query_lower in name.lower()):
                    results.append({"name": name, "type": kind, "line": idx})
        return results

    def get_outline(self, content: str) -> List[str]:
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            if self._PHP_RE.search(line):
                results.append(f"L{idx}: {line.strip()}")
        return results


class RubyAdapter(UniversalAdapter):
    """Adaptador para Ruby (.rb)."""

    _RUBY_RE = re.compile(
        r"\b(class|module|def)\s+([A-Za-z0-9_::!?]+)",
        re.MULTILINE,
    )

    def validate(self, content: str, path: str = "") -> None:
        super().validate(content, path)
        err = _run_cli_check(["ruby", "-c", "{file}"], content, path or "file.rb")
        if err:
            raise ValueError(f"contenido con sintaxis Ruby inválida: {err}")

    def find_symbols(self, content: str, query: str = "") -> List[dict]:
        query_lower = query.lower()
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            for match in self._RUBY_RE.finditer(line):
                kind = match.group(1)
                name = match.group(2)
                if name and (not query_lower or query_lower in name.lower()):
                    results.append({"name": name, "type": kind, "line": idx})
        return results

    def get_outline(self, content: str) -> List[str]:
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            if self._RUBY_RE.search(line):
                results.append(f"L{idx}: {line.strip()}")
        return results


class SwiftAdapter(UniversalAdapter):
    """Adaptador para Swift / Apple (.swift)."""

    _SWIFT_RE = re.compile(
        r"\b(func|class|struct|enum|protocol|extension)\s+([A-Za-z0-9_]+)",
        re.MULTILINE,
    )

    def find_symbols(self, content: str, query: str = "") -> List[dict]:
        query_lower = query.lower()
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            for match in self._SWIFT_RE.finditer(line):
                kind = match.group(1)
                name = match.group(2)
                if name and (not query_lower or query_lower in name.lower()):
                    results.append({"name": name, "type": kind, "line": idx})
        return results

    def get_outline(self, content: str) -> List[str]:
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            if self._SWIFT_RE.search(line):
                results.append(f"L{idx}: {line.strip()}")
        return results


class ShellAdapter(UniversalAdapter):
    """Adaptador para Shell/Bash/Powershell (.sh, .bash, .zsh, .ps1)."""

    _SHELL_RE = re.compile(
        r"(?:function\s+)?([A-Za-z0-9_\-]+)\s*\(\)|function\s+([A-Za-z0-9_\-]+)",
        re.MULTILINE,
    )

    def validate(self, content: str, path: str = "") -> None:
        super().validate(content, path)
        err = _run_cli_check(["bash", "-n", "{file}"], content, path or "script.sh")
        if err:
            raise ValueError(f"contenido con sintaxis Shell inválida: {err}")

    def find_symbols(self, content: str, query: str = "") -> List[dict]:
        query_lower = query.lower()
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            for match in self._SHELL_RE.finditer(line):
                name = match.group(1) or match.group(2)
                if name and name not in ("if", "then", "else", "fi", "for", "while", "do", "done") and (not query_lower or query_lower in name.lower()):
                    results.append({"name": name, "type": "function", "line": idx})
        return results


    def get_outline(self, content: str) -> List[str]:
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            if self._SHELL_RE.search(line):
                results.append(f"L{idx}: {line.strip()}")
        return results


class SQLAdapter(UniversalAdapter):
    """Adaptador para SQL (.sql)."""

    _SQL_RE = re.compile(
        r"\b(CREATE|ALTER|DROP)\s+(TABLE|VIEW|INDEX|PROCEDURE|FUNCTION|TRIGGER|SCHEMA)\s+([A-Za-z0-9_\".]+)",
        re.IGNORECASE | re.MULTILINE,
    )

    def find_symbols(self, content: str, query: str = "") -> List[dict]:
        query_lower = query.lower()
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            for match in self._SQL_RE.finditer(line):
                kind = f"{match.group(1).upper()} {match.group(2).upper()}"
                name = match.group(3)
                if name and (not query_lower or query_lower in name.lower()):
                    results.append({"name": name, "type": kind, "line": idx})
        return results

    def get_outline(self, content: str) -> List[str]:
        results = []
        for idx, line in enumerate(content.splitlines(), 1):
            if self._SQL_RE.search(line):
                results.append(f"L{idx}: {line.strip()}")
        return results



class LanguageAdapterRegistry:
    """Registro con Carga Bajo Demanda (Lazy Loading) de adaptadores por extensión."""

    _EXTENSION_MAP: Dict[str, Type[LanguageAdapter]] = {
        # Python
        ".py": PythonAdapter,
        ".pyw": PythonAdapter,
        # JS / TS / Web
        ".js": JavaScriptTSAdapter,
        ".jsx": JavaScriptTSAdapter,
        ".ts": JavaScriptTSAdapter,
        ".tsx": JavaScriptTSAdapter,
        ".mjs": JavaScriptTSAdapter,
        ".cjs": JavaScriptTSAdapter,
        # Go & Rust
        ".go": GoAdapter,
        ".rs": RustAdapter,
        # JVM Stack (Java, Kotlin, Scala, Groovy)
        ".java": JavaAdapter,
        ".kt": JavaAdapter,
        ".kts": JavaAdapter,
        ".scala": JavaAdapter,
        ".groovy": JavaAdapter,
        # .NET & C/C++ Stack (C#, F#, C++, C, Headers)
        ".cs": CSharpAdapter,
        ".fs": CSharpAdapter,
        ".vb": CSharpAdapter,
        ".cpp": CSharpAdapter,
        ".cxx": CSharpAdapter,
        ".cc": CSharpAdapter,
        ".c": CSharpAdapter,
        ".h": CSharpAdapter,
        ".hpp": CSharpAdapter,
        # Scripting & Mobile
        ".php": PHPAdapter,
        ".rb": RubyAdapter,
        ".swift": SwiftAdapter,
        ".sh": ShellAdapter,
        ".bash": ShellAdapter,
        ".zsh": ShellAdapter,
        ".ps1": ShellAdapter,
        # Databases & Config
        ".sql": SQLAdapter,
        ".json": JSONAdapter,
    }

    def __init__(self):
        self._instances: Dict[str, LanguageAdapter] = {}

    def get_adapter(self, path: str) -> LanguageAdapter:
        ext = Path(path).suffix.lower()
        adapter_cls = self._EXTENSION_MAP.get(ext, UniversalAdapter)
        cls_name = adapter_cls.__name__

        if cls_name not in self._instances:
            self._instances[cls_name] = adapter_cls()

        return self._instances[cls_name]

    def loaded_adapter_names(self) -> List[str]:
        """Devuelve los nombres de los adaptadores instanciados en memoria (para tests)."""
        return list(self._instances.keys())


# Instancia singleton del registro de adaptadores
registry = LanguageAdapterRegistry()


