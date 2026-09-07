# Guía de Publicación y Distribución en PyPI — yunta-harness

Este documento detalla los pasos para compilar, validar y publicar **Yunta** en el registro oficial de paquetes de Python ([PyPI](https://pypi.org/project/yunta-harness/)).

---

## 1. Identidad del Paquete en PyPI

- **Nombre en PyPI**: `yunta-harness`  
  *(El nombre `yunta` ya se encontraba registrado por una librería de bioinformática previa; `yunta-harness` coincide exactamente con el repositorio oficial `github.com/j0sp0nc3/yunta-harness`).*
- **Comando en Terminal**: `yunta`  
  *(Cualquier usuario que instale el paquete dispondrá del comando `yunta` en su consola).*
- **Importación en Python**: `from yunta import Agent, LiteLLMProvider, Usage`

---

## 2. Publicación Automatizada vía GitHub Actions (Recomendado)

El repositorio incluye el pipeline [`.github/workflows/publish.yml`](../.github/workflows/publish.yml), que automatiza la compilación y subida a PyPI.

### Opción A: PyPI Trusted Publishing (OIDC — Sin Tokens)
1. En tu cuenta de [PyPI](https://pypi.org/manage/account/):
   - Ve a **Publishing** y agrega un **Trusted Publisher**.
   - Propietario de GitHub: `j0sp0nc3`
   - Repositorio: `yunta-harness`
   - Nombre de Workflow: `publish.yml`
2. En GitHub, crea una nueva **Release**:
   - Tag: `v1.0.2` (o la versión que corresponda).
   - Al publicarse la release, la GitHub Action compilará el paquete y lo publicará en PyPI automáticamente.

### Opción B: Mediante Secret `PYPI_API_TOKEN`
1. Genera un API Token en PyPI (con alcance al proyecto `yunta-harness`).
2. En tu repositorio de GitHub, ve a **Settings > Secrets and variables > Actions**.
3. Crea un secreto llamado `PYPI_API_TOKEN` con el valor del token.
4. Dispara el workflow creando una Release o desde la pestaña **Actions > Publish to PyPI > Run workflow**.

---

## 3. Publicación Manual Local (Alternativa)

Si prefieres compilar y publicar directamente desde tu terminal local:

### Paso 1: Instalar herramientas de compilación
```bash
pip install --upgrade build twine
```

### Paso 2: Generar los artefactos de distribución
```bash
# Limpiar compilaciones anteriores si existen
rm -rf dist/ build/ *.egg-info

# Compilar wheel (.whl) y paquete fuente (.tar.gz)
python -m build
```

### Paso 3: Validar los metadatos del paquete
```bash
twine check dist/*
```
*(Debe indicar `PASSED` sin advertencias críticas).*

### Paso 4: Subir a PyPI
```bash
# Subir al entorno oficial de PyPI
twine upload dist/*

# O para probar primero en TestPyPI:
twine upload --repository testpypi dist/*
```
Te solicitará tu usuario (`__token__`) y tu contraseña (tu API token de PyPI que inicia con `pypi-...`).

---

## 4. Verificación de la Instalación

Una vez publicado, valida la instalación desde una máquina o entorno virtual limpio:

```bash
# Crear entorno de prueba limpio
python -m venv test_env
source test_env/bin/activate  # En Windows: test_env\Scripts\activate

# 1. Instalar desde PyPI
pip install yunta-harness

# 2. Verificar comando CLI en terminal
yunta --help  # O iniciar yunta directamente

# 3. Verificar importación como librería en Python
python -c "from yunta import Agent, LiteLLMProvider, Usage; print('Yunta importado exitosamente!')"
```
