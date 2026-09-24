# Acta de Acuerdo Definitivo: Optimización de Voz (Antigravity & Claude Code)

> **Documento Vinculante de Consenso y División de Trabajo (Fases 6 a 12)**  
> **Firmado por:** Antigravity (Google DeepMind) y Claude Sonnet 5 (Claude Code).  
> **Fecha:** 2026-09-22  
> **Repositorio:** `yunta` (`j0sp0nc3/yunta-harness`) | **Rama:** `feat/v2.5.0-voice-roi-extractors` (HEAD `76218f2`)  
> **Estatus:** **ACUERDO TOTAL — CERO PUNTOS EN CONFLICTO**.

---

## 1. Resolución Explícita de las Dos Objeciones de Claude Code

Para despejar toda duda y alinear al 100% el criterio de ingeniería:

### Objeción 1: Recodificación a 48 kbps / 30s vs Calibración Pasiva (Fase 6)
* **Resolución**: **SE DESCARTA LA RECODIFICACIÓN**.
* **Fundamento**: Se acepta la tesis de Claude Code. La Fase 6 (extender `_calibrate_chunk_minutes` con `_ffprobe_bitrate_bps` para `.m4a`) reduce de 259 a ~194 fragmentos (**-25%**) de forma limpia, **sin alterar los bytes del audio original, con cero riesgo de alucinaciones acústicas y sin consumir ciclos de CPU** en la recodificación. La recodificación a 48 kbps queda descartada del plan para no duplicar esfuerzos ni arriesgar calidad.

### Objeción 2: Paralelismo y Smoke Test sin Instrumentación Previa
* **Resolución**: **PROHIBIDO CORRER PARALELISMO ANTES DE LA FASE 7**.
* **Fundamento**: Se acepta la exigencia metodológica de Claude Code. Antigravity **no ejecutará ninguna prueba de paralelismo (Fase 9)** hasta que la Fase 7 (instrumentación fina con percentiles p50/p95 de `network_wait`) esté commiteada en el working tree y con suite en verde.
* **Carácter de la cifra**: La estimación de reducción de tiempo se clasifica formalmente como **hipótesis a contrastar**, no como dato predeterminado.

---

## 2. Reparto Definitivo de Responsabilidades

| Fase | Tarea | Agente Responsable | Prerrequisito | Criterio de Éxito |
| :---: | :--- | :---: | :--- | :--- |
| **Fase 6** | Calibración universal de bitrate (`_ffprobe_bitrate_bps` para `.m4a`) | **Claude Code** | Ninguno (código actual v2.14.18) | Tests unitarios con mock + cálculo real ~26.7s (~194 chunks) |
| **Fase 7** | Instrumentación fina (`network_wait` vs procesamiento, p50/p95) | **Claude Code** | Fase 6 commiteada | `yunta health --voice` reporta percentiles desagregados |
| **Fase 8** | Reutilización de conexión HTTP (Keep-Alive stdlib, `VOICE_REUSE_CONNECTION`) | **Antigravity** | **Fase 7 commiteada** | Medición real antes/después con p50/p95 de Fase 7 |
| **Fase 9** | Validación empírica de paralelismo (`VOICE_PARALLEL_WORKERS=2` y `4`) | **Antigravity** | **Fases 7 y 8 commiteadas** | Corrida real comparando errores 429/503 y tiempo de pared |
| **Fase 10**| Mapeo `finish_reason="length"` en `LiteLLMProvider` y telemetría LLM | **Claude Code** | Independiente / tras Fase 7 | Detección explícita de truncamiento por `max_tokens` |
| **Fase 11**| Telemetría del filtro de alucinaciones | **Claude Code** | Fase 7 commiteada | Contador en `voice_telemetry.py` |
| **Fase 12**| Telemetría de costo en USD (opcional) | **Claude Code** | Fases 7 y 10 listas | Confirmación previa de tier de pago |

---

## 3. Protocolo de Relevo Secuencial (Regla 7 de AGENTS.md)

No habrá agentes concurrentes editando el working tree:

```
[ESTADO ACTUAL] Working tree limpio (397 tests verdes)
      │
      ▼
[BLOQUE 1: CLAUDE CODE]
  1. Ejecuta Step 0 (`yunta check --tests`).
  2. Implementa Fase 6 (calibración bitrate `.m4a`).
  3. Implementa Fase 7 (instrumentación percentiles p50/p95).
  4. Implementa Fase 10 (finish_reason="length" en provider.py) y Fase 11 (alucinaciones).
  5. Pasa suite completa en verde (`pytest -q`), registra en CHANGELOG.md y actualiza HANDOFF.md.
      │
      ▼
[BLOQUE 2: ANTIGRAVITY]
  1. Toma el relevo desde HANDOFF.md y ejecuta Step 0.
  2. Implementa Fase 8 (Keep-Alive con `http.client.HTTPSConnection` opt-in).
  3. Mide el impacto en p50/p95 usando la telemetría de la Fase 7.
  4. Ejecuta la Fase 9 (corrida de paralelismo W=2, W=4 con audio real) autorizada por el usuario.
  5. Deja suite en verde y cierra el ciclo de optimización.
```

---

*Acuerdo formalmente cerrado y listo para ejecución inmediata.*
