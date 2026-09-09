"""Módulo de inicialización de proyectos guiado por Spec-Driven Development (SDD).

Genera los tres artefactos fundacionales de cualquier proyecto:
1. SPEC.md: Especificación de producto, visión, casos de uso y anti-alcance.
2. PLAN.md: Hoja de ruta por fases verificables (Fase 1: Mínimo Núcleo Viable).
3. AGENTS.md: Guardrails de desarrollo, contexto y comandos de prueba.
"""

from pathlib import Path


def generate_spec(project_name: str, idea_description: str = "") -> str:
    desc = idea_description or f"Solución construida para {project_name}."
    return f"""# Especificación de Producto — {project_name}

## 1. Visión y Propósito
{desc}

El objetivo central de este proyecto es resolver el problema de forma simple,
robusta y verificable, priorizando la arquitectura antes de la codificación masiva.

## 2. Problema a Resolver
- **Contexto:** ¿Qué situación actual motiva la creación de este proyecto?
- **Puntos de dolor:** ¿Qué fricción experimenta el usuario hoy?
- **Resultado deseado:** ¿Qué valor concreto entrega esta herramienta?

## 3. Actores y Usuarios
- **Usuario Principal:** Perfil objetivo que interactúa con el sistema.
- **Sistemas Externos:** APIs, bases de datos o servicios con los que se comunica.

## 4. Casos de Uso Core (MVP)
1. **Flujo Principal:**
   - **Entrada:** Datos o parámetros recibidos.
   - **Procesamiento:** Lógica de negocio esencial.
   - **Salida:** Resultado visible o persistido.
2. **Manejo de Casos Borde y Errores:**
   - Validación de entradas inválidas.
   - Fallos controlados con mensajes claros.

## 5. Arquitectura y Flujo de Datos
```text
[ Entrada / Usuario ] ──> [ Módulo Core ] ──> [ Salida / Almacenamiento ]
```

## 6. Fuera de Alcance (Anti-alcance del MVP)
- Características secundarias que NO deben desarrollarse en la primera versión.
- Optimizaciones prematuras.
- Integraciones complejas no requeridas para validar la idea.

## 7. Criterios de Aceptación Globales
- [ ] La funcionalidad core puede probarse con al menos un comando o test automatizado.
- [ ] No requiere pasos manuales ocultos ni configuración críptica.
- [ ] Cumple con las reglas especificadas en `AGENTS.md`.
"""


def generate_plan(project_name: str) -> str:
    return f"""# Plan de Desarrollo — {project_name}

Plan de desarrollo por fases incrementales guiado por Spec-Driven Development (SDD).
Actualizar este archivo al completar cada fase junto con el registro de cambios.

Estado actual: **Fase 0 — Inicialización Completada**

---

## Fases del Roadmap

### Fase 1: Mínimo Núcleo Viable (Core MVP)
- [ ] Definir modelos de datos o estructuras esenciales.
- [ ] Escribir primera prueba unitaria o de aceptación (Fase Roja).
- [ ] Implementar la lógica mínima para pasar la prueba (Fase Verde).
- [ ] **Criterio de éxito:** Ejecución del test core exitosa.

### Fase 2: Lógica de Negocio y Casos de Uso Principales
- [ ] Implementar los flujos de trabajo definidos en `SPEC.md`.
- [ ] Manejo de validaciones y errores comunes.
- [ ] Pruebas unitarias de cobertura de los casos de uso.
- [ ] **Criterio de éxito:** Todos los casos de uso core cubiertos con tests.

### Fase 3: Interfaz de Usuario / CLI / API
- [ ] Diseñar el punto de entrada para el usuario (CLI, script, endpoints o TUI).
- [ ] Conectar la interfaz con el núcleo de negocio validado en la Fase 2.
- [ ] **Criterio de éxito:** El usuario puede ejecutar el flujo completo desde la interfaz.

### Fase 4: Pulido, Documentación y Empaquetado
- [ ] Documentar instrucciones de uso en `README.md`.
- [ ] Validar compatibilidad y empaquetar dependencias.
- [ ] **Criterio de éxito:** Proyecto listo para compartirse o desplegarse.

---

## Reglas que Gobiernan el Plan
1. **Avanzar una fase a la vez:** No escribir código de la Fase 3 antes de certificar la Fase 1.
2. **Verificación continua:** Ninguna fase se marca como completada sin pruebas que lo demuestren.
3. **El código se adapta a la especificación:** Si la idea cambia, primero se actualiza `SPEC.md` y `PLAN.md`.
"""


def generate_agents(project_name: str) -> str:
    return f"""# Contexto del Proyecto y Reglas para Agentes — {project_name}

Este archivo define las reglas de convivencia y contexto ontológico para cualquier
agente de código (Yunta, Claude, Cursor, Copilot) que trabaje en este proyecto.

## 1. Contexto del Proyecto
- **Proyecto:** {project_name}
- **Filosofía:** Spec-Driven Development (SDD). El código sigue a la especificación.
- **Entorno recomendado:** Python 3.11+ / Node / el stack elegido por el usuario.

## 2. Comandos Esenciales
- **Ejecutar tests:** `pytest` (o el comando de test del stack elegido)
- **Ejecutar linters/verificación:** `python -m py_compile ...` o equivalente.

## 3. Reglas Inviolables para Agentes
1. **Soberanía de las Especificaciones:** Consulta `SPEC.md` y `PLAN.md` antes de proponer cambios. Nunca cambies el alcance ni la arquitectura sin instrucción humana.
2. **TDD / Verificación Obligatoria:** Todo cambio debe acompañarse de su prueba o comando de verificación. Nunca declares una tarea terminada sin haberla verificado con una tool real.
3. **Mínimo Código Necesario:** No agregues frameworks pesados ni dependencias innecesarias si la biblioteca estándar o una herramienta simple resuelve el problema.
4. **Frontera de Ejecución:** Respeta las fases del `PLAN.md`. Resuelve únicamente la tarea solicitada en la fase activa.

## 4. Protocolo Obligatorio para IDEs y Agentes Externos (Claude, Cursor, Copilot)
1. **Yunta CLI como Único Ejecutor y Oráculo:** Cualquier agente o IDE externo debe interactuar con el proyecto invocando a Yunta vía terminal: `yunta "tu instrucción"`.
2. **Prioridad sobre el LLM Interno:** Antes de asumir reglas o generar código por tu cuenta, delega la tarea en `yunta` para que sea procesada bajo SPEC, PLAN y AGENTS.
3. **Consultas de Solo Lectura (Q&A):** Para preguntas arquitectónicas o de inspección ("¿dónde está X?", "¿cómo funciona Y?"), invoca `yunta "pregunta"`. Yunta responderá fundamentándose en el código fuente sin realizar modificaciones sobre el proyecto.
4. **Modificaciones Quirúrgicas:** Todo cambio de código debe realizarse mediante ediciones precisas y validarse con la suite de tests antes de finalizar.
"""


def run_init(
    idea: str = "",
    target_dir: Path | None = None,
    overwrite: bool = False,
) -> dict[str, Path]:
    dest = Path(target_dir) if target_dir else Path.cwd()
    dest.mkdir(parents=True, exist_ok=True)

    raw_name = idea.strip()
    if not raw_name or raw_name == ".":
        project_name = dest.resolve().name
        idea_description = ""
    else:
        project_name = raw_name
        idea_description = raw_name

    created: dict[str, Path] = {}

    files_to_create = [
        ("SPEC.md", generate_spec(project_name, idea_description)),
        ("PLAN.md", generate_plan(project_name)),
        ("AGENTS.md", generate_agents(project_name)),
    ]

    for filename, text in files_to_create:
        filepath = dest / filename
        if not filepath.exists() or overwrite:
            filepath.write_text(text.strip() + "\n", encoding="utf-8")
            created[filename] = filepath

    print(f"\n✨ Proyecto '{project_name}' inicializado con éxito bajo Spec-Driven Development (SDD):")
    for name, _ in files_to_create:
        status = "creado" if name in created else "ya existía (respetado)"
        print(f"  - {name:<10} [{status}] -> {dest / name}")

    print("\n🚀 Próximos pasos sugeridos:")
    print("  1. Abre SPEC.md y afina los detalles o anti-alcance de tu idea.")
    print("  2. Inicia Yunta en esta carpeta:")
    print(f'     yunta "Comencemos con la Fase 1 del PLAN.md"')
    print()

    return created
