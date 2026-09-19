# Yunta Governance Check (GitHub Action)

Empaqueta `yunta check` como gate de CI/CD: audita el repositorio contra
`AGENTS.md`/`SPEC.md`/`PLAN.md`, estado de git y la suite de tests —
**determinista y $0 en tokens de LLM** (no requiere `LLM_MODEL` ni ninguna
credencial).

## Uso desde otro repositorio

```yaml
# .github/workflows/yunta-check.yml
name: Yunta Governance Check
on: [pull_request]

jobs:
  governance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: j0sp0nc3/yunta-harness/.github/actions/check@master
        with:
          run-tests: "true"
          fail-on-warning: "false"
```

## Inputs

| Input | Default | Descripción |
|---|---|---|
| `target-dir` | `.` | Directorio del repositorio a auditar |
| `run-tests` | `true` | Ejecuta la suite de tests del repo auditado (pytest/npm/cargo, autodetectado) |
| `fail-on-warning` | `false` | Si `true`, falla el job también ante advertencias (ej. cambios de git sin commitear), no solo ante fallos |
| `source` | `pypi` | `pypi` instala `yunta-harness` publicado; `local` instala el checkout actual en modo editable (solo para dogfooding dentro de este mismo repo) |
| `python-version` | `3.11` | Versión de Python |

## Output

- `healthy`: `"true"` o `"false"` según el resultado de la auditoría.

## Uso dentro de este mismo repositorio (dogfooding)

Ver el job `governance` en [`.github/workflows/ci.yml`](../../workflows/ci.yml),
que usa `uses: ./.github/actions/check` con `source: local` para auditar el
propio `yunta-harness` en cada PR.
