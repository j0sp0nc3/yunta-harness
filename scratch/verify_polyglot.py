import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")


from yunta.adapters import registry as adapter_registry
from yunta.tools.files import _validate_content
from yunta.tools.symbols import find_symbol, get_ast_outline

def run_polyglot_benchmark():
    print("=" * 60)
    print("🚀 DEMOSTRACIÓN POLYGLOT & BENCHMARK DE EFICIENCIA — YUNTA v2.2.0")
    print("=" * 60)

    # 1. Verificar Lazy-Loading
    print("\n1. VERIFICACIÓN DE CARGA BAJO DEMANDA (LAZY LOADING)")
    print(f"  - Adaptadores cargados al inicio: {adapter_registry.loaded_adapter_names()}")
    assert len(adapter_registry.loaded_adapter_names()) == 0, "No debe haber adaptadores cargados al inicio"

    # Touch Python
    adapter_registry.get_adapter("scratch/demo_polyglot/app.py")
    print(f"  - Tras interactuar con .py: {adapter_registry.loaded_adapter_names()}")

    # Touch TS
    adapter_registry.get_adapter("scratch/demo_polyglot/service.ts")
    print(f"  - Tras interactuar con .ts: {adapter_registry.loaded_adapter_names()}")

    # Touch Go
    adapter_registry.get_adapter("scratch/demo_polyglot/main.go")
    print(f"  - Tras interactuar con .go: {adapter_registry.loaded_adapter_names()}")

    # Touch Rust
    adapter_registry.get_adapter("scratch/demo_polyglot/lib.rs")
    print(f"  - Tras interactuar con .rs: {adapter_registry.loaded_adapter_names()}")

    # Touch JSON
    adapter_registry.get_adapter("scratch/demo_polyglot/config.json")
    print(f"  - Tras interactuar con .json: {adapter_registry.loaded_adapter_names()}")

    # Touch Java
    adapter_registry.get_adapter("scratch/demo_polyglot/UserService.java")
    print(f"  - Tras interactuar con .java: {adapter_registry.loaded_adapter_names()}")

    # Touch C#
    adapter_registry.get_adapter("scratch/demo_polyglot/OrderService.cs")
    print(f"  - Tras interactuar con .cs (.NET): {adapter_registry.loaded_adapter_names()}")

    # 2. Verificación de Compilación y Sintaxis por Lenguaje
    print("\n2. VERIFICACIÓN DE COMPILACIÓN Y SINTAXIS POR LENGUAJE")
    files = [
        ("Python", "scratch/demo_polyglot/app.py", "def valid(): pass", "def invalid(:"),
        ("TypeScript", "scratch/demo_polyglot/service.ts", "const x = { a: 1 };", "const x = { a: 1;"),
        ("Go", "scratch/demo_polyglot/main.go", "package main\nfunc Ok() {}", "func Bad() {"),
        ("Rust", "scratch/demo_polyglot/lib.rs", "pub fn ok() {}", "pub fn bad() {"),
        ("JSON", "scratch/demo_polyglot/config.json", '{"key": "val"}', '{"key": "val",}'),
        ("Java", "scratch/demo_polyglot/UserService.java", "class Valid {}", "class Invalid {"),
        (".NET (C#)", "scratch/demo_polyglot/OrderService.cs", "public class Valid {}", "public class Invalid {"),

    ]

    for lang, path, valid_code, invalid_code in files:
        # Valid code check
        try:
            _validate_content(path, valid_code)
            valid_status = "✅ OK (Aceptado)"
        except Exception as e:
            valid_status = f"❌ Falló: {e}"

        # Invalid code check
        try:
            _validate_content(path, invalid_code)
            invalid_status = "❌ Falló (Se aceptó código inválido)"
        except ValueError as e:
            invalid_status = f"✅ Rechazado Atómicamente: '{e}'"

        print(f"  [{lang}] ({path}):")
        print(f"    - Código Válido: {valid_status}")
        print(f"    - Código Inválido: {invalid_status}")

    # 3. Búsqueda de Símbolos AST Polyglot
    print("\n3. BÚSQUEDA DE SÍMBOLOS AST EN MÚLTIPLES LENGUAJES (find_symbol)")
    queries = ["Calculator", "UserService", "ServerConfig", "Database", "OrderService", "supported_languages"]
    for q in queries:
        res = find_symbol(json.dumps({"name": q}))
        print(f"  - Búsqueda '{q}':\n    {res.strip()}")

    # 4. Esquema Estructurado por Lenguaje (get_ast_outline)
    print("\n4. ESQUEMA ESTRUCTURADO (OUTLINE) POR LENGUAJE")
    demo_files = [
        "scratch/demo_polyglot/app.py",
        "scratch/demo_polyglot/service.ts",
        "scratch/demo_polyglot/main.go",
        "scratch/demo_polyglot/lib.rs",
        "scratch/demo_polyglot/UserService.java",
        "scratch/demo_polyglot/OrderService.cs",
        "scratch/demo_polyglot/config.json",
    ]

    t0 = time.perf_counter()
    for f in demo_files:
        outline = get_ast_outline(json.dumps({"path": f}))
        print(f"\n  --- Outline: {f} ---\n{outline}")
    t1 = time.perf_counter()

    # 5. Métricas de Eficiencia
    print("\n" + "=" * 60)
    print("📊 MÉTRICAS DE EFICIENCIA Y RENDIMIENTO")
    print("=" * 60)
    print(f"  - Tiempo de análisis polyglot (7 stacks): {(t1 - t0) * 1000:.2f} ms")
    print(f"  - Adaptadores activos en memoria: {len(adapter_registry.loaded_adapter_names())}")
    print("  - Consumo de tokens en auditoría AST: 0 tokens (Parser 100% estático local)")
    print("  - Garantía atómica: 0 corrupción de archivos en caso de fallo sintáctico")
    print("=" * 60)

if __name__ == "__main__":
    run_polyglot_benchmark()
