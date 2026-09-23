# Changelog — yunta

Registro de avance del proyecto. Cada modificación al harness se documenta aquí
para que cualquiera —persona, IDE u otro agente/modelo— pueda retomar el contexto
sin historial previo.

Formato: fecha, cambios agregados/modificados/eliminados, y motivo.

## [2.14.21] — 2026-09-22

- **`yunta/provider.py`, nuevo `yunta/llm_call_telemetry.py` — V7-5: telemetría de `finish_reason` crudo por llamada al LLM**: dos corridas reales distintas del pipeline de voz generaron **exactamente 9,402 tokens de salida** con contenido de entrada completamente distinto (72K vs 73K caracteres de transcript, resúmenes con estructura diferente) — coincidencia estadísticamente rara si ambas generaciones terminaron "naturalmente". `_FINISH_REASONS` en `provider.py` no mapea `"length"` (el motivo estándar cuando la respuesta se corta por `max_tokens`) — hoy cae silenciosamente en `StopReason.OTHER`, indistinguible de cualquier otro final.
  - Nuevo módulo `yunta/llm_call_telemetry.py` (mismo patrón JSONL de `voice_telemetry.py`): registra por llamada a `LiteLLMProvider.send()` el modelo, tokens de entrada/salida, tiempo de pared, y **`finish_reason` crudo del proveedor** (no el `StopReason` ya mapeado) — deliberadamente separado de `yunta/api.py::Usage`, superficie pública congelada (`docs/PLAN.md`, ítem E2, reexportada en `yunta/__init__.py`), sin agregarle campos ni tocar `StopReason`.
  - Instrumentado en ambos caminos de `send()`: no-streaming (`litellm.completion` directo) y streaming (`_consume_stream`, que ahora recibe el `model` real usado, relevante con fallback entre modelos).
  - `aggregate_llm_calls`: tokens/segundo promedio y proporción de llamadas truncadas por `"length"` — responde directamente si el truncamiento por `max_tokens` explica una demora, en vez de conjeturarlo.
  - Nunca rompe la respuesta real si falla el registro (mismo patrón de resiliencia que `voice_telemetry`).
  - 6 tests nuevos entre `tests/test_provider.py` y `tests/test_llm_call_telemetry.py` (413 → 419 tests totales): roundtrip y agregación de `llm_call_telemetry.py`, `finish_reason="length"` capturado distinguible en ambos caminos (streaming y no), y que un fallo de telemetría no rompe la llamada real.
  - **Resultado de esta fase**: la próxima corrida real con transcript real va a decir con datos si el truncamiento por `max_tokens` explica la demora sin explicar de la Corrida 2, en vez de solo la coincidencia sospechosa de tokens idénticos.
  - Fase 10 de un plan conjunto con Antigravity (ver `.claude/plans/genera-un-plan-de-concurrent-cook.md`, no versionado en este repo).

## [2.14.20] — 2026-09-22

- **`yunta/voice.py`, `yunta/voice_telemetry.py`, `yunta/cli.py` — V7-2: instrumentación fina por fragmento (network_wait vs processing)**: la Corrida 2 quedó con una anomalía sin explicar (~91s de diferencia en STT no atribuibles a overhead medido) porque la única telemetría existente era un agregado ciego por transcripción completa — no había forma de saber si una demora era de red/endpoint o del lado cliente.
  - `AudioTranscriber.transcribe_with_meta` ahora mide `network_wait_secs` (tiempo dentro de `_post_transcription`, acumulado a través de reintentos — cada reintento es un round-trip real) y `total_secs` (tiempo total del método), agregados a la metadata que ya devolvía (`source`, `cloud_attempted`, `cloud_failed`).
  - `AudioChunker._record_telemetry` colecciona estos valores por fragmento en `_telem_network_wait`/`_telem_processing` (processing = total − network_wait; incluye deliberadamente la espera de backoff entre reintentos, que es una pausa del cliente, no medición perfecta de cada micro-etapa sino la distinción que importa: red/endpoint vs cliente).
  - `yunta/voice_telemetry.py`: nueva `percentile(values, pct)` (interpolación lineal, sin dependencias); `VoiceSnapshot`/`record_voice_snapshot` ganan `network_wait_p50/p95/max`, `processing_p50/p95/max` y `workers_used`, todos con default (compatible con snapshots viejos); `aggregate_voice` promedia estos percentiles entre sesiones, tolerando snapshots sin los campos nuevos (aportan 0.0).
  - `yunta health --voice` muestra los nuevos percentiles.
  - `workers_used` refleja el modo de ejecución REAL (no solo la variable de entorno configurada): con un solo fragmento, `VOICE_PARALLEL_WORKERS>1` igual cae al camino secuencial, y así se reporta.
  - Overhead de instrumentar: unas pocas llamadas a `time.monotonic()` (nanosegundos) por fragmento frente a segundos de I/O de red — despreciable por diseño, no requiere medición aislada adicional.
  - 12 tests nuevos entre `tests/test_voice.py` y `tests/test_voice_telemetry.py` (401 → 413 tests totales): percentiles (vacío, un valor, conocidos), roundtrip y defaults de los campos nuevos, promedio entre sesiones y tolerancia a snapshots viejos, acumulación de `network_wait` a través de reintentos, `_record_telemetry` con y sin campos de timing, integración completa (percentiles reales pasados a `record_voice_snapshot`) y `workers_used` reflejando el modo real de ejecución; se corrigieron 3 tests existentes que comparaban el dict de metadata por igualdad exacta (ahora tiene 2 campos más).
  - **Resultado de esta fase**: la próxima corrida real sobre el archivo de prueba va a producir percentiles interpretables de red vs procesamiento — reemplaza la especulación de la Corrida 2 por datos, no la explica todavía (eso requiere correr la Fase 8/9 con esto ya en pie).
  - Fase 7 de un plan conjunto con Antigravity (ver `.claude/plans/genera-un-plan-de-concurrent-cook.md`, no versionado en este repo) — desbloquea la validación empírica de las Fases 8 (keep-alive) y 9 (paralelismo), a cargo de Antigravity.

## [2.14.19] — 2026-09-22

- **`yunta/voice.py` — V7-1: calibración de bitrate universal (no solo MP3)**: `_calibrate_chunk_minutes` (Fase 4, v2.14.4) solo podía leer bitrate real vía sniffing de frame MP3 — para cualquier otro contenedor (`.m4a`, `.ogg`, `.wav`) siempre daba 0 y la función se rendía directo al `floor` de 0.33 min. **Esto significaba que la calibración de bitrate nunca tuvo efecto en ninguna de las 3 corridas empíricas reales de esta sesión**, porque el archivo de prueba es `.m4a` — hallazgo encontrado en una segunda revisión independiente del trabajo de las corridas 1-3.
  - Nueva `_ffprobe_bitrate_bps(file_path)`: mismo patrón defensivo que `_ffprobe_duration_secs` (try/except, timeout, comparte el flag `_ffprobe_available` — si uno detecta el binario ausente, el otro no reintenta), pero para bitrate vía `ffprobe -show_entries format=bit_rate`, funcionando con cualquier formato que `ffprobe` entienda.
  - `_calibrate_chunk_minutes` ahora intenta `_estimate_bitrate_bps` (rápido, sin subproceso, solo MP3) y si da 0, intenta `_ffprobe_bitrate_bps` antes de rendirse al `floor` — sin regresión si ambos fallan.
  - **Validado con el archivo real de la sesión** (81.78 min, `.m4a`): bitrate detectado 130,564 bps (130.6 kbps), `chunk_minutes` calibrado de 0.33 min (20s) fijo a 0.4444 min (26.7s) — proyección de 248 a 184 fragmentos (**-25.7%**), coincide casi exacto con la proyección de la revisión independiente (~0.44min, -25%).
  - 4 tests nuevos en `tests/test_voice.py` (397 → 401 tests totales): parseo de `_ffprobe_bitrate_bps`, desactivación tras binario ausente, flag compartido entre `_ffprobe_bitrate_bps`/`_ffprobe_duration_secs`, calibración real para `.m4a` con ffprobe mockeado; se actualizó un test existente (`test_calibrate_chunk_minutes_falls_back_to_floor_without_bitrate`) para mockear explícitamente `ffprobe` ausente en vez de depender implícitamente de que el binario real no pudiera parsear un archivo de bytes basura.
  - **Pendiente**: falta la corrida empírica completa (fragmentos totales reales, tasa de errores, ritmo por fragmento) — la calibración standalone ya está verificada, pero el efecto de punta a punta en una transcripción real todavía no.
  - Fase 6 de un plan conjunto con Antigravity (ver `.claude/plans/genera-un-plan-de-concurrent-cook.md` — no versionado en este repo) tras contrastar y resolver dos rondas de revisión cruzada sobre cómo seguir optimizando el pipeline de voz post-v2.14.18.

## [2.14.18] — 2026-09-20

- **`yunta/voice.py` — corrección de regresión: elimina 259 llamadas redundantes a `ffprobe`**: la segunda corrida real de auditoría (mismo audio de 81 min, después de v2.14.12-17) salió **más lenta** que la primera (STT: 2265.7s vs 2127.8s; total: 50m40s vs 43m46s) — el objetivo de estas fases era mejorar, no empeorar, y el resultado neto no lo cumplió.
  - Causa raíz medida (no supuesta): `split_audio_by_silence` (V6-5) ya mide la duración total del audio con `ffprobe` y ya conoce los puntos de corte exactos (por silencio o por múltiplos de `segment_secs`) — pero `transcribe_large_audio` (V6-1) volvía a llamar a `ffprobe` **una vez por cada uno de los 259 fragmentos ya generados**, redescubriendo algo que ya se sabía. Medido con el archivo real: 259 llamadas × ~141ms = **~36.5s de overhead puro**, más ~10.1s de la pasada de `silencedetect` — overhead real total ~47s, pero no explica toda la diferencia observada (~138s en la fase STT); el resto es contención de CPU/red compartida no atribuible al código.
  - `AudioChunker` gana `_last_chunk_durations`: `split_audio_by_silence` calcula las duraciones exactas de cada fragmento a partir de los boundaries que ya conoce (una sola medición de `ffprobe` sobre el archivo original) y las expone; `transcribe_large_audio` las reutiliza directamente en vez de re-medir cada fragmento. Verificado con el archivo real de 81 min: `split_audio_by_silence` completo (silencedetect + corte + cálculo de duraciones) ahora tarda **16.74s en total** (antes: ~47s+ solo en overhead de medición, sin contar el corte en sí), con duraciones exactas (suma = 4906.68s, coincide con la medición real de `ffprobe`).
  - Fallback preservado: si `split_audio_by_silence` fue reemplazado (como en varios tests) o las duraciones no coinciden en cantidad con los chunks generados, se vuelve a medir por fragmento como antes — sin regresión funcional.
  - 3 tests nuevos en `tests/test_voice.py` (394 → 397 tests totales): duraciones exactas expuestas con cortes por silencio, duraciones exactas expuestas con corte fijo, y verificación de que `ffprobe` se llama una sola vez (no una por fragmento) en una transcripción completa.
  - Pendiente: falta una tercera corrida real completa para confirmar que el tiempo total vuelve a ser competitivo con la corrida original — la fase de resumen del LLM (donde también hubo una demora sin explicar en la segunda corrida) no se tocó en este commit.

## [2.14.17] — 2026-09-20

- **Higiene de `.yunta/voice_health.jsonl`**: confirmado que la contaminación por tests ya quedó resuelta como efecto colateral del `monkeypatch.chdir(tmp_path)` agregado en v2.14.13 (V6-3) — corrí toda la suite de voz y el archivo real no creció ni una línea. Limpiadas las 161 entradas sintéticas acumuladas de antes de ese fix (backup en el scratchpad de la sesión), dejando solo la entrada real de la transcripción de 81 min. No es un cambio de código — `.yunta/` está gitignored, es mantenimiento local.
- **`yunta/voice.py` — `offload_transcript`: sugerir lectura única en vez de fragmentada cuando el tamaño lo permite**: motivado por la misma corrida real — el agente fragmentó la lectura del transcript (775 líneas, cabían en una sola llamada a `read_file` bajo su límite de 2000) en 6 llamadas "para procesarlo mejor", porque el mensaje de `offload_transcript` siempre sugería leer "por partes" sin importar el tamaño. Cada llamada extra reenvía todo el historial acumulado — eso, sumado a 7 tool calls perdidas explorando el filesystem tras un dígito mal transcrito en el nombre del archivo, explica buena parte de los 172K tokens de entrada de esa corrida.
  - Bajo un umbral generoso (~50K tokens), ahora sugiere explícitamente una sola lectura sin offset/limit; por encima, mantiene la sugerencia de lectura fragmentada — no se quita la protección para audios de muchas horas.
  - La ruta del archivo ahora se reporta en formato POSIX (`scratch_file.as_posix()`, barras) en vez del formato nativo de Windows (backslashes) — reduce el riesgo de que el modelo la corrompa al reproducirla en un argumento JSON de tool call (`\t`, `\n`, etc. son secuencias de escape válidas que pueden aparecer por casualidad en una ruta de Windows).
  - **Nota honesta**: esto no elimina el riesgo de que el modelo transcriba mal un dígito del timestamp del archivo (lo que causó la mayoría de las 7 llamadas perdidas explorando el filesystem en la corrida real) — es un problema inherente de pedirle a un LLM que reproduzca de memoria una cadena numérica larga, no algo resoluble solo con este cambio.
  - 3 tests nuevos en `tests/test_voice.py` (391 → 394 tests totales): sugiere lectura única para tamaño moderado, mantiene sugerencia fragmentada para tamaño muy grande, y la ruta reportada no contiene backslashes.

## [2.14.16] — 2026-09-20

- **`docs/PLAN.md` — actualización de estado por instrucción humana explícita** (Regla 6): V6-1, V6-3, V6-4 y V6-5 quedan marcados ✅ — resueltos en v2.14.14, v2.14.13, v2.14.12 y v2.14.15 respectivamente. Con esto, todo el "Nivel 1" y "Nivel 2" del backlog v6 queda completo; solo resta V6-8 (diarización pyannote, Nivel 3, dependencia pesada, deliberadamente diferido). Sin cambios de código.

## [2.14.15] — 2026-09-20

- **`yunta/voice.py` — V6-5 (`docs/PLAN.md`): corte de chunks en silencios en vez de tiempo fijo**: hasta ahora `split_audio_by_silence` (pese a su nombre) cortaba a duración fija (`-segment_time`), partiendo palabras a la mitad entre fragmentos consecutivos — técnica estándar en WhisperX/faster-whisper para evitarlo.
  - Nuevas `_detect_silence_intervals(file_path)` (parsea la salida de `ffmpeg -af silencedetect` por stderr) y `_silence_aware_cut_points(total_secs, segment_secs, silences, tolerance)` (ajusta cada corte al punto medio del silencio más cercano dentro de una tolerancia del 30% del tamaño de fragmento; si no hay silencio cerca, mantiene el corte fijo original en vez de descartarlo).
  - En `split_audio_by_silence`: si `ffprobe` da la duración real (V6-1) y se detectan silencios, el comando de `ffmpeg` usa `-segment_times` con los cortes ajustados; si cualquiera de los dos falla, cae íntegro al `-segment_time` de siempre — sin regresión cuando `ffmpeg`/`ffprobe` no cooperan o el audio no tiene pausas detectables.
  - Riesgo controlado: es la función de fragmentación más usada de todo el pipeline, pero el cambio es aditivo (nueva rama opt-in por resultado, no reemplaza el camino existente) y ningún test previo ejercía el comando real de `ffmpeg` con contenido no vacío (todos usan archivos MP3 falsos que `ffprobe` ya rechazaba antes de este cambio), así que no hubo regresiones que corregir.
  - 7 tests nuevos en `tests/test_voice.py` (384 → 391 tests totales): parseo de `silencedetect`, fallback ante fallo de `ffmpeg`, ajuste al punto medio más cercano, mantención del corte fijo sin silencio cercano, lista vacía sin silencios, y dos tests de integración (usa `-segment_times` vs. cae a `-segment_time`).

## [2.14.14] — 2026-09-20

- **`yunta/voice.py` — V6-1 (`docs/PLAN.md`): marcas de tiempo reales por chunk vía `ffprobe`**: hasta ahora el offset de cada fragmento se repartía proporcionalmente por tamaño en bytes, una aproximación que se desincroniza con audio VBR o cuando el último chunk de `ffmpeg -f segment` sale más corto que el resto.
  - Nueva `_ffprobe_duration_secs(file_path)`: mide la duración real de cada chunk con `ffprobe`. Detecta una sola vez si el binario está disponible (`_ffprobe_available`) para no reintentarlo en cada uno de los N fragmentos si falta; un fallo puntual en UN chunk (archivo corrupto) no desactiva `ffprobe` para el resto.
  - En `transcribe_large_audio`: si `ffprobe` da duración real para **todos** los chunks, los offsets se calculan por duración acumulada real; si falla para alguno, cae íntegro a la heurística anterior (bytes proporcionales / `_estimate_duration_secs`) — sin regresión cuando `ffprobe` no está instalado.
  - Funciona para cualquier formato que `ffprobe` sepa leer, no solo `.mp3` — beneficia también a `.m4a` y otros formatos que quedaban fuera de la calibración de Fase 4.
  - 5 tests nuevos en `tests/test_voice.py` (379 → 384 tests totales): parseo de duración, desactivación tras binario ausente, tolerancia a un archivo puntual corrupto, offsets reales en una transcripción simulada (bytes iguales, duraciones distintas), y fallback cuando `ffprobe` no está disponible.

## [2.14.13] — 2026-09-20

- **`yunta/voice.py` — V6-3 (`docs/PLAN.md`): checkpoint incremental de transcripción**: motivado directamente por la corrida real de 81 min (43m46s de pared) — si el proceso se hubiera caído en el fragmento 200/259, se perdía TODO lo transcrito sin ningún resguardo intermedio.
  - Nuevas funciones de módulo `_checkpoint_path/_load_checkpoint/_save_checkpoint_fragment/_clear_checkpoint`: cada fragmento completado se persiste a `.yunta/scratch/transcript_<audio>.n<total>.part<N>.txt`; relanzar el mismo archivo reanuda desde el último fragmento en vez de empezar de cero, en modo secuencial y paralelo (`VOICE_PARALLEL_WORKERS>1`).
  - El `total` de fragmentos va en el nombre del checkpoint a propósito: si `chunk_minutes` cambia entre corridas (distinto `VOICE_CHUNK_MINUTES` o recalibración de Fase 4), el conteo de fragmentos cambia y los checkpoints viejos simplemente no matchean — fallback seguro a transcripción completa en vez de desalinear fragmentos de una fragmentación distinta.
  - Al completar la transcripción entera (`outcome == "completed"`), los checkpoints se borran — no quedan archivos huérfanos en `.yunta/scratch/`.
  - **Corrección de una regresión propia antes de commitear**: los checkpoints usan una ruta relativa (`.yunta/scratch`) resuelta contra el directorio de trabajo — varios tests existentes de `tests/test_voice.py` y `tests/test_voice_telemetry.py` llamaban a `transcribe_large_audio` sin `monkeypatch.chdir(tmp_path)`, lo que habría escrito archivos de checkpoint reales en el repo cada vez que corriera la suite (el mismo tipo de contaminación ya detectado en `voice_health.jsonl`). Se agregó `monkeypatch.chdir(tmp_path)` a los 11 tests afectados antes de que esto llegara a producirse.
  - 5 tests nuevos en `tests/test_voice.py` (374 → 379 tests totales): roundtrip de guardar/cargar/limpiar, no reanuda si cambia el total de fragmentos, reanudación real tras una interrupción (secuencial y paralelo), y limpieza de checkpoints tras completar.

## [2.14.12] — 2026-09-20

- **`yunta/voice.py` — V6-4 (`docs/PLAN.md`): filtro de alucinaciones conocidas de Whisper**: descarta fragmentos cuyo contenido ENTERO (sin puntuación/mayúsculas) coincide con una frase de relleno típica que Whisper aprendió de subtítulos de YouTube en su entrenamiento ("Gracias por ver el video", "Suscríbete al canal", créditos de Amara.org, etc.) — no recorta contenido real que las mencione de pasada, solo el caso "el chunk es puro relleno".
  - Nuevas funciones de módulo `_filter_whisper_hallucinations(text)` y `_clean_transcription(text)` (combina dedup + filtro de alucinaciones); reemplaza los 3 puntos donde antes se aplicaba `_dedup_whisper_repetition` solo, en `AudioTranscriber.transcribe_with_meta` (éxito de nube, fallback local tras agotar reintentos, y salto directo a local por `skip_cloud`).
  - **Nota honesta**: esto ataca el patrón clásico de alucinación de Whisper (relleno de outro de YouTube), no necesariamente el mismo fenómeno observado en la transcripción real de 81 min de ayer (balbuceo en portugués/italiano/griego/japonés/finlandés durante silencios) — ese problema apunta más a falta de VAD (V6-7/prefiltro) que a frases de relleno conocidas. Son mitigaciones complementarias, no la misma solución.
  - 7 tests nuevos en `tests/test_voice.py` (367 → 374 tests totales): coincidencia exacta con variantes de mayúsculas/puntuación, contenido real intacto, no recorta menciones parciales, string vacío, combinación con dedup, y dos tests de integración (filtra alucinación tanto en éxito de nube como en fallback local).

## [2.14.11] — 2026-09-20

- **`docs/PLAN.md` — actualización de estado por instrucción humana explícita** (Regla 6: el agente no edita el backlog salvo instrucción expresa; el usuario la dio directamente en esta sesión): V6-2 y V6-6 quedan marcados ✅ — ambos ya estaban resueltos por el plan de resiliencia de voz (Fases 0-5) implementado en v2.14.4 y v2.14.9 respectivamente, pero `PLAN.md` no se había actualizado porque el agente no puede tocarlo sin autorización.
  - **V6-2** ✅ (v2.14.4): retry con backoff adaptativo + circuit breaker cloud↔local.
  - **V6-6** ✅ (v2.14.9): paralelismo acotado opt-in vía `VOICE_PARALLEL_WORKERS`, marcado explícitamente como pendiente de validación empírica con audio real bajo concurrencia (no confundir "implementado" con "medido").
  - Sin cambios de código; ningún test afectado.

## [2.14.10] — 2026-09-20

- **`yunta/voice.py` — cache del modelo local de `faster_whisper`**: motivado por un benchmark real hecho tras la transcripción de 81 min de hoy — `transcribe_offline_local` recargaba el modelo (`WhisperModel(...)`) en **cada llamada**, con ~3.9s de overhead medido por carga; en una transcripción de 259 fragmentos que cayera seguido a fallback local, eso son ~17 min extra solo en recargas.
  - Nuevo `_get_local_whisper_model(model_size)` a nivel de módulo: carga el modelo una sola vez por proceso y lo reutiliza en llamadas siguientes, protegido por `threading.Lock` (relevante también bajo `VOICE_PARALLEL_WORKERS>1`, Fase 5). Invalida y recarga si `LOCAL_WHISPER_MODEL` cambia entre llamadas.
  - Cache a nivel de **módulo**, no de instancia: `AudioTranscriber`/`AudioChunker` a veces se instancian varias veces dentro del mismo proceso (p.ej. el retry por `too_large` crea un `AudioChunker` nuevo) y todas deben compartir el mismo modelo cargado.
  - 3 tests nuevos en `tests/test_voice.py` (364 → 367 tests totales, con `faster_whisper` mockeado vía `sys.modules`): carga única tras 5 llamadas, recarga si cambia `LOCAL_WHISPER_MODEL`, y modelo compartido entre instancias distintas de `AudioTranscriber`.
  - Validado además con el modelo real (`faster_whisper` tiny, CPU int8) sobre un fragmento de 20s del audio de la corrida de hoy: la primera llamada paga la carga, las siguientes no repiten ese costo fijo — la medición exacta en esta máquina es ruidosa por carga de CPU compartida con otra sesión concurrente, pero el patrón (sin overhead repetido) es consistente con el fix.

## [2.14.9] — 2026-09-20

- **`yunta/voice.py` — Fase 5 (plan de resiliencia de voz, última fase): paralelismo acotado, opt-in vía `VOICE_PARALLEL_WORKERS`**: fase de mayor riesgo del plan — N workers concurrentes podrían *causar* una ráfaga de 503 si se habilita antes de que el circuit breaker + backoff (Fases 1-2) bajen la tasa de error base, por eso queda opt-in (`default="1"` = secuencial, comportamiento idéntico al actual).
  - Con `VOICE_PARALLEL_WORKERS > 1`: `ThreadPoolExecutor`/`as_completed` (mismo patrón ya usado en `yunta/tools/delegate.py`), reensamblado por índice (`transcripts[idx] = ...`, no por orden de llegada) para no desordenar la transcripción.
  - `AudioChunker` gana `self._state_lock` (`threading.Lock`) para las mutaciones de los contadores del circuit breaker (Fase 1) y de telemetría (Fase 3) — sin costo real en el modo secuencial por defecto, un solo hilo nunca contiende el lock.
  - **Limitación conocida y documentada, no un bug**: sin orden garantizado entre workers concurrentes, no hay continuidad de `tail` (el prompt de continuidad entre fragmentos consecutivos que sí existe en modo secuencial) — cada fragmento en modo paralelo se transcribe con prompt vacío.
  - Ctrl+C en modo paralelo cancela los fragmentos aún no iniciados (`executor.shutdown(cancel_futures=True)`) y espera a que terminen los ya en vuelo (acotado a `VOICE_PARALLEL_WORKERS`, no al total de fragmentos) antes de devolver la transcripción parcial.
  - Refactor interno sin cambio de comportamiento por defecto: los offsets de timestamp ahora se precalculan por índice antes del loop (en vez de acumularse durante la iteración), para que sean válidos tanto en modo secuencial como paralelo.
  - 6 tests nuevos en `tests/test_voice.py` (358 → 364 tests totales): reensamblado fuera de orden, ausencia de continuidad de tail en paralelo, continuidad de tail preservada por defecto, conteo de telemetría independiente del orden de finalización, interrupción por Ctrl+C en paralelo, y tolerancia a un valor inválido de la variable de entorno.
  - Con esto se completan las 6 fases (0-5) del plan de resiliencia del pipeline de voz. Fase 4 y Fase 5 quedan validadas solo con tests unitarios — no hay un audio real de 81 min disponible en esta sesión para la comparación empírica antes/después (RTF, errores por fragmento) que el plan original preveía como criterio de éxito adicional.

## [2.14.8] — 2026-09-20

- **Metodología Yunta y Buzón Canónico de Relevo (`docs/METODOLOGIA_YUNTA.md`, `AGENTS.md`)**:
  - **Especificación de Metodología Yunta (`docs/METODOLOGIA_YUNTA.md`)**: formalización exhaustiva de los 4 principios de continuidad inter-agente y multi-IDE (Persistencia Zero-Tokens, Diagnóstico Forense Asimétrico / Step 0, Git como Ancla de Verdad Inmutable, y Operador Único Secuencial). Resuelve estructuralmente la "Paradoja de la Amnesia" y el aislamiento de contexto en herramientas como Claude Code, ZCode, Cursor y Antigravity.
  - **Buzón Canónico de Relevo (`.yunta/HANDOFF.md`)**: especificado en `AGENTS.md` (Regla 7) para separar notas narrativas del directorio temporal `scratch/`, permitiendo handoffs limpios y persistentes sin ensuciar el working tree de Git.
  - **Principio de Operador Único**: formalización explícita en `AGENTS.md` de la coordinación estricta secuencial (nunca dos agentes concurrentes modificando el working tree).

## [2.14.7] — 2026-09-20

- **`yunta/voice.py` — Fase 4 (plan de resiliencia de voz): recalibración de tamaño de fragmento por bitrate real**: motivado por la misma transcripción real de 81 min (480 errores/259 fragmentos) que originó las Fases 0-3 — los fragmentos contra Cloudflare Workers AI usaban un tamaño fijo de 20s (`chunk_minutes=0.33`) sin importar el bitrate real del audio.
  - Nuevas funciones a nivel de módulo `_estimate_bitrate_bps(file_path)` (extraída de `AudioChunker._estimate_duration_secs`, sniffing del primer frame MP3) y `_calibrate_chunk_minutes(file_path, max_bytes, safety=0.85, floor=0.33, ceiling=0.5)`, que usa el bitrate real para calcular minutos por fragmento en vez de asumir siempre el peor caso. `ceiling=0.5` (30s) es deliberadamente conservador: el límite real de Workers AI es CPU-por-invocación, no solo tamaño de payload.
  - Deliberadamente funciones de módulo y no métodos de `AudioChunker`: se invocan desde `AudioTranscriber.transcribe_with_meta` antes de instanciar `AudioChunker`, y varios tests existentes mockean la clase `AudioChunker` completa — un método de clase habría resuelto el mock en vez de la lógica real. `AudioChunker._estimate_bitrate_bps`/`_calibrate_chunk_minutes` se mantienen como `@staticmethod` de conveniencia que delegan a las funciones de módulo.
  - Solo aplica a `.mp3` contra endpoints Workers AI (`workers.dev`) y solo si no hay override manual (`VOICE_CHUNK_MINUTES` sigue teniendo prioridad absoluta). Otros formatos y el endpoint estándar (25 MB, `chunk_minutes=10`) no cambian de comportamiento.
  - 8 tests nuevos en `tests/test_voice.py` (350 → 358 tests totales): lectura de bitrate, clamping a floor/ceiling, fallback sin bitrate legible, cableado end-to-end contra Workers AI, y respeto del override manual.
  - Validación: solo unitaria — no hay un audio real de 81 min disponible en esta sesión para la comparación empírica antes/después (RTF, errores por fragmento) que el plan original preveía como criterio de éxito adicional para esta fase. Queda pendiente correr esa comparación cuando haya audio real disponible.

## [2.14.6] — 2026-09-20

- **`AGENTS.md` — Regla 7: Protocolo de Relevo y Continuidad (Step 0 obligatorio)**: motivada por un incidente real de esta misma fecha — un relevo entre sesiones concurrentes (ZCode → Claude Code) dejó `tests/test_voice.py` con bytes nulos literales que rompían la compilación, invisibles para un chequeo superficial.
  - **Step 0 obligatorio**: `yunta check --tests` + `git status` antes de proponer cambios. Explícitamente `--tests` y no `yunta check` a secas, porque sin ese flag el comando solo detecta que existe un runner de pytest, no lo ejecuta — no habría atrapado el incidente que motiva la regla.
  - **Handoff estructurado**: el traspaso de estado real de sesión usa `yunta handoff export/import` (Feature 1, v2.8.0), no un markdown ad-hoc; un `scratch/HANDOFF*.md` narrativo sigue siendo válido como complemento, nunca como único registro.
  - Prohibición de "trabajo fantasma" (commits `wip:` ante agotamiento de cuota) y cierre de relevo limpio (working tree commiteado o documentado en CHANGELOG).

## [2.14.5] — 2026-09-20

- **Telemetría persistente del pipeline de voz (`yunta/voice_telemetry.py`, nuevo)**: reemplaza el script ad-hoc (`python -c "..."` grepeando logs) que se usó para medir la transcripción de 81 min/259 fragmentos por un registro estructurado consultable con `yunta health --voice [--json]`.
  - Módulo separado de `yunta/health.py` a propósito: su `health_score` es una heurística específica de agente LLM (tasa de error de tools, doom-loops) que no tiene sentido para un pipeline de audio. Clona el mismo patrón (JSONL append-only en `.yunta/voice_health.jsonl`) sin heredar ese acoplamiento.
  - `AudioChunker` acumula 3 contadores nuevos (`_telem_cloud`, `_telem_local`, `_telem_errors`) en el mismo punto donde ya se actualiza el circuit breaker (v2.14.4), y graba una snapshot (fragmentos totales, nube vs local, errores manejados, disparos de breaker, RTF) al terminar `transcribe_large_audio` — tanto en el camino feliz como en interrupción por Ctrl+C (`outcome="completed"|"partial"`). Envuelto en `try/except: pass`: un fallo al grabar telemetría nunca rompe una transcripción en curso.
  - Comando `yunta health --voice`.
- **Tests: 350** (5 nuevos en `tests/test_voice_telemetry.py`). 100% pasando.

## [2.14.4] — 2026-09-20

- **Resiliencia del pipeline STT: circuit breaker + backoff adaptativo (`yunta/voice.py`)**: motivado por una transcripción real de 81 min (259 fragmentos) contra Cloudflare Workers AI que registró 480 errores 503/1102 manejados — cada fragmento peleaba su propia batalla de reintentos sin memoria de que los anteriores también habían fallado. Trabajo iniciado en paralelo por ZCode (sesión dogfooding, agotó cuota antes de documentar/commitear) y completado aquí con el mismo diseño.
  - **`AudioTranscriber.transcribe_with_meta(file_path, prompt, skip_cloud)`** (nuevo): extrae el cuerpo de `transcribe()` devolviendo además `{"source": "cloud"|"local", "cloud_attempted": bool, "cloud_failed": bool}`. `transcribe()` queda como wrapper de una línea — cero cambio de firma/comportamiento para los llamadores existentes (`cli.py`, `VoiceListener`). `skip_cloud=True` salta directo al fallback local sin tocar la red.
  - **Circuit breaker en `AudioChunker`**: tras `VOICE_BREAKER_THRESHOLD` (default 3) fallos de nube CONSECUTIVOS entre fragmentos, salta la nube por `VOICE_BREAKER_COOLDOWN` (default 5) fragmentos, con sondeo automático (el streak no se resetea al disparar, así que el primer fragmento tras el cooldown reintenta la nube). `VOICE_BREAKER_THRESHOLD=0` desactiva el breaker (comportamiento idéntico al anterior). Anuncia en consola cuando se dispara — sin fallback oculto (regla 2 de AGENTS.md). `_cb_tripped_count` queda listo para telemetría futura.
  - **Backoff adaptativo con `Retry-After`**: `_TranscribeError` gana `retry_after: float | None`, leído del header HTTP si el endpoint lo manda (solo formato numérico en segundos). Sin el header, backoff exponencial con jitter (`VOICE_BACKOFF_BASE * 2**attempt`) en vez del lineal fijo anterior (3s, 6s). Tope configurable vía `VOICE_BACKOFF_CAP` (default 30s).
  - Nuevas env vars: `VOICE_BREAKER_THRESHOLD`, `VOICE_BREAKER_COOLDOWN`, `VOICE_BACKOFF_BASE`, `VOICE_BACKOFF_CAP`.
- **Tests: 345** (7 nuevos: 2 de `transcribe_with_meta`, 3 de backoff/retry_after, 2 de circuit breaker). 100% pasando.

## [2.14.3] — 2026-09-19

- **Blindaje y resiliencia de transcripción de audio (`yunta/voice.py`, `yunta/cli.py`)**:
  - **Soporte nativo y calibración para Cloudflare Workers AI (`workers.dev`)**: Workers AI impone un límite estricto de CPU (~50ms) y memoria (HTTP 413 / error 1102). La calibración automática fragmenta audios >500 KB en bloques de **20 segundos** (`chunk_minutes=0.33`, ~320 KB), permitiendo inferencia fluida en 1.5s sin colapsar el worker.
  - **Fragmentación sin corrupción de contenedor AAC/M4A (`split_audio_by_silence`)**: `ffmpeg` ahora preserva la extensión original del archivo (`chunk_%03d{ext}` con `-c copy`) en lugar de forzar `.mp3`, permitiendo segmentar audios `.m4a`/AAC en milisegundos sin errores de muxing ni pérdida de calidad.
  - **Deduplicación de bucles patológicos de Whisper (`_dedup_whisper_repetition`)**: filtra alucinaciones en loop que Whisper produce ocasionalmente en fragmentos con silencios o ruido ambiente, evitando texto repetitivo.
  - **Compatibilidad con consolas Windows (cp1252)**: reconfiguración segura de `sys.stdout` y `sys.stderr` a `utf-8` con `errors='replace'`, eliminando `UnicodeEncodeError` al imprimir emojis e indicadores de progreso en terminales Windows.
  - **Timeout de red extendido (`VOICE_TIMEOUT`)**: ampliado de 10s fijos a 60s configurables, evitando falsos `TimeoutError` durante inferencias en la nube.
- **Tests: 338** (2 nuevos en `tests/test_voice.py`). 100% pasando.

## [2.14.2] — 2026-09-19

- **GitHub Action de `yunta check` (`.github/actions/check/`)**: empaqueta la auditoría de gobernanza determinista y $0-tokens como gate reutilizable de CI/CD, para que cualquier repo externo pueda bloquear PRs que violen `AGENTS.md`/`SPEC.md`/`PLAN.md` sin costo de inferencia. Inputs: `target-dir`, `run-tests`, `fail-on-warning`, `source` (`pypi` para consumo externo, `local` para dogfooding), `python-version`. Dogfooding inmediato: nuevo job `governance` en `.github/workflows/ci.yml` que la usa contra este mismo repo en cada push/PR.
- **Spec pública del Handoff (`docs/schemas/yunta-session-spec-v1.{schema.json,md}`)**: el schema del bundle de `yunta handoff` (Feature 1, v2.8.0) vivía solo como constante interna (`SCHEMA_VERSION = 1`); ahora es un JSON Schema (draft 2020-12) versionado y documentado para que cualquier harness externo pueda implementar lectura/escritura compatible sin depender del código de yunta. `jsonschema` agregado como dependencia de **desarrollo** (no runtime) para validar la conformidad en tests.
- **Fix defensivo — `make_voice_approval` con `session_permissions=None` (`yunta/voice.py`)**: con un `Agent` real esto es inalcanzable (su constructor siempre inicializa `SessionPermissions()`), pero cualquier integración que no pase por él podía provocar `AttributeError` al decir "siempre". Ahora degrada con gracia: concede la aprobación de ese turno igual, solo no la persiste.
- **Tests: 336** (4 nuevos en `tests/test_handoff_schema.py`; `test_voice_chaos.py` actualizado, 0 nuevos ahí). 100% pasando.

## [2.14.1] — 2026-09-19

- **Blindaje del subsistema de Voz/TTS — 6 defectos de runtime encontrados por testing adversarial (`tests/test_voice_chaos.py`, ahora trackeado en git)**: a diferencia de la Parte A (bugs encontrados por exploración arquitectónica), estos 6 solo eran detectables ejecutando código bajo estrés real — condiciones de carrera, inyección de fallos, fuzzing de input malformado. Ninguno fue detectado por la revisión de diseño de la sesión.
  - **Permisos "siempre" ignorados en modo voz (`yunta/agent.py`, `_approve`)**: `voice_approval` se consultaba incondicionalmente ANTES de revisar `session_permissions`, así que decir "siempre" no evitaba que se volviera a preguntar por voz en el siguiente comando de la misma tool. Ahora `session_permissions.allowed()` se consulta primero (salvo en `force_prompt`, que sigue forzando confirmación explícita por diseño — doom-loop).
  - **Condición de carrera en prefetch de TTS (`yunta/tts.py`, `_worker`)**: si una oración se reproducía más rápido de lo que tardaba el prefetch de la siguiente (frases cortas como "Sí."), el bucle principal lanzaba una SEGUNDA síntesis concurrente en vez de esperar la que ya estaba en curso. Ahora se hace `join()` (con timeout de 30s) sobre el hilo de prefetch antes de decidir si sintetizar de nuevo.
  - **Excepción no capturada mataba el hilo de habla (`yunta/tts.py`, `_worker`)**: la llamada síncrona a `provider.synthesize(chunk)` no tenía `try/except` (a diferencia de `_prefetch`, que sí lo tenía) — una falla de red mataba el hilo daemon en silencio y el resto de la respuesta no se leía. Ahora está protegida igual que `_prefetch`.
  - **Emoji duplicaba el argumento del router de voz (`yunta/voice.py`, `route_keyword`)**: la extracción del argumento usaba `text.split(maxsplit=prefix_words)` sobre el texto crudo, pero `prefix_words` se calculaba sobre `cleaned` (sin emojis). Un emoji al inicio desalineaba el conteo y "inicializa" terminaba duplicado dentro del argumento (ej. "🚀 inicializa X" → "/init inicializa X"). Ahora se consumen palabras crudas una a una, limpiándolas individualmente, hasta reconstruir el prefijo exacto.
  - **Bloques de código Markdown sin cerrar se filtraban a voz (`yunta/tts.py`, `clean_markdown_for_speech`)**: la regex de resumen de código exigía el cierre ` ``` `; si la respuesta del modelo se cortaba a mitad de un bloque, el código crudo pasaba intacto al lector de voz. Se agregó una segunda pasada que trata cualquier ` ``` ` remanente (sin cierre) como código hasta el final del texto.
  - **Mensaje de error engañoso en audio de 0 bytes (`yunta/voice.py`, `AudioChunker.split_audio_by_silence`)**: un archivo vacío hacía fallar tanto el intento con ffmpeg como el fallback por bytes, cayendo en el `RuntimeError` genérico de "ffmpeg no está disponible" incluso con ffmpeg instalado. Ahora se detecta el archivo vacío explícitamente al inicio con un mensaje que señala la causa real.
- `tests/test_voice_chaos.py`: incorporado formalmente al repo (estaba sin trackear); sus 14 pruebas pasan de documentar los defectos a ser regresión permanente sobre el comportamiento corregido.
- **Tests: 332** (mismos 14 de `test_voice_chaos.py`, ahora trackeados; 0 nuevos, assertions invertidas de "defecto confirmado" a "comportamiento correcto"). 100% pasando, sin `PytestUnhandledThreadExceptionWarning`.

## [2.14.0] — 2026-09-19

- **Feature 7 — Undo como Árbol / Best-of-N (`yunta/bestof.py`)**: el agente prueba N enfoques alternativos para la misma tarea en sandboxes de worktree aislados y el humano elige el mejor por diff, en vez de aceptar el único intento del agente o deshacer linealmente con `/undo`.
  - **Decisión de alcance explícita: ejecución SECUENCIAL, no paralela real** — `os.chdir()` es global al proceso; N hilos pisándose entre sandboxes distintos sería una condición de carrera real, no hipotética. Paralelismo real (subprocesos con cwd propio) queda fuera de este roadmap.
  - `run_best_of_n()`: crea N sandboxes (reutiliza `sandbox.create_sandbox`/`cleanup_sandbox` sin tocar su contrato), ejecuta un sub-agente de contexto limpio por rama (mismo patrón que `decompose.run_chunks`), compromete los cambios de cada rama (`git commit --allow-empty`, necesario para que el merge posterior no pierda archivos sin commitear al hacer `git worktree remove --force`) y calcula el diff de cada candidato contra el commit del que partió.
  - `choose_and_finalize()` / `discard_all()`: integran la rama elegida (`merge=True`) y descartan el resto, reutilizando `cleanup_sandbox` sin lógica de merge nueva.
  - Comando REPL `/bestof <n> <tarea>` (2-5 enfoques), separado de `/sandbox` para no arriesgar código ya estable.
  - Fix relacionado ya aplicado en la Parte A (B3): la colisión de timestamp de `create_sandbox` con N≥2 llamadas rápidas, prerequisito real de esta feature.
- **Tests: 332** (5 nuevos en `tests/test_bestof.py`). 100% pasando.

**Con esta entrada se completan las 7 features propuestas en `docs/propuestas/2026-09-19-plan-7-features.md` (Parte B), sobre la Parte A de blindaje previo.**

## [2.13.0] — 2026-09-19

- **Feature 6 — Enrutamiento Económico Dinámico**: usa automáticamente un modelo barato (`LLM_CHEAP_MODEL`) para pasos triviales de solo lectura, reservando el modelo principal para decisiones y ediciones.
  - `LiteLLMProvider.set_model_override()` (`yunta/provider.py`): fuerza el modelo del próximo `send()` sin tocar la posición de la cascada de fallback (`_model_idx`). Si el modelo económico falla, se descarta el override y se reintenta con la cascada normal **sin avanzar** `_model_idx` (no es un fallo del modelo principal).
  - `IntentClassifier.evaluate_triviality()` (`yunta/intent.py`): reutiliza `Agent._recent_tool_calls` (el mismo estado que ya trackea doom-loops, cero instrumentación duplicada). **Regla dura, no heurística blanda**: si `write_file`/`str_replace`/`bash` aparece en la ventana reciente, nunca es trivial — se prefiere gastar de más en el modelo caro a arriesgar una edición mal razonada con el barato. Sin historial de tools (primer turno), tampoco es trivial por defecto.
  - `yunta/agent.py`: se evalúa en cada turno del bucle (no solo al inicio de `send()`), para que el override se desactive de inmediato en cuanto el agente decide escribir algo.
  - Nueva env var `LLM_CHEAP_MODEL`.
- **Tests: 327** (8 nuevos: 2 en `tests/test_provider.py`, 5 en `tests/test_intent.py`, 1 de integración en `tests/test_agent.py`). 100% pasando.

## [2.12.0] — 2026-09-19

- **Feature 5 — Agent Health Score (`yunta/health.py`)**: persiste métricas agregadas por repo entre sesiones (`.yunta/health.jsonl`, misma convención JSONL append-only de la Feature 4), en vez de perderlas al morir el proceso (`Usage`/`Budget` eran 100% en memoria).
  - `record_snapshot()`: una snapshot por sesión (turnos, tool_errors, total_tool_calls, disparos de doom-loop, cache_rate, modelo). Cero instrumentación nueva salvo `Agent._doom_loop_triggers` (`yunta/agent.py`), incrementado en el mismo punto donde ya se calculaba `force_prompt`.
  - `aggregate()`: agrega snapshots en un `health_score` heurístico v1 (documentado explícitamente como punto de partida, no como métrica científica) — penaliza tasa de error de tools y frecuencia de doom-loops.
  - Grabado automáticamente al `/exit` del REPL y al finalizar single-shot (mismo lifecycle hook que ya dispara `feedback.summarize`). Comando: `yunta health [--json]`.
- **Tests: 319** (6 nuevos: 5 en `tests/test_health.py`, 1 de integración en `tests/test_agent.py` verificando el contador de doom-loops). 100% pasando.

## [2.11.0] — 2026-09-19

- **Feature 4 — Memoria de Equipo (`yunta/tools/memory.py`, `yunta/team_memory.py`)**: hace que la memoria explícita (`remember`/`recall`) sea sincronizable entre miembros de equipo, en dos partes.
  - **Formato (`yunta/tools/memory.py`)**: migrado de "array JSON reescrito completo en cada `remember`" a **JSONL append-only** (una entrada por línea) — mucho más amigable con merges de git. Migración automática y transparente del formato viejo la primera vez que se lee o escribe (`_load` detecta un array `[...]` y lo reescribe como JSONL antes de continuar). Retrocompatible: `recall`/`remember` se comportan igual desde fuera.
  - **Transporte (`yunta/team_memory.py`, nuevo)**: `dedup_learnings()`/`dedup_memory()` (deduplican tras un merge mal resuelto, conservando la primera aparición) y `sync_report()` (solo lectura, cuenta entradas). Comando `yunta memory sync [--fix]`.
  - **`.gitignore`**: hoy `.yunta/` está 100% ignorado, por lo que "memoria compartible por git" no tenía transporte. Comando `yunta memory init-sync` agrega las excepciones necesarias (`!.yunta/learnings.md`, `!.yunta/memory.json`) **solo con confirmación explícita del usuario** en terminal — nunca se toca `.gitignore` automáticamente.
- **Tests: 313** (11 nuevos: 4 en `tests/test_memory.py` incluyendo migración legacy→JSONL, 7 en `tests/test_team_memory.py`). 100% pasando.

## [2.10.0] — 2026-09-19

- **Feature 3 — Tests de Caracterización / Golden-Master (`yunta/tools/characterize.py`)**: nueva tool `characterize_function` (`requires_approval=True`) que captura el comportamiento ACTUAL de una función Python top-level antes de refactorizarla, para detectar regresiones en código legacy sin tests.
  - Filtro heurístico best-effort de efectos secundarios (por AST: llamadas a `open`/`subprocess`/`requests`/`socket`/`input`/`urlopen`; por nombre: prefijos `write_/save_/delete_/send_/remove_/post_/put_`) — rechaza en vez de arriesgar caracterizar código con I/O real.
  - **Ejecución en subproceso aislado con timeout** (nunca in-process): un crash o cuelgue en la función objetivo no tumba el proceso de yunta.
  - Genera `tests/test_characterize_<módulo>_<función>.py` con cabecera de advertencia explícita ("captura comportamiento ACTUAL, no necesariamente correcto"), cargando el módulo objetivo por ruta de archivo (`importlib.util`) para evitar problemas de resolución de paquetes/imports en repos arbitrarios.
  - Verificado end-to-end: los tests generados se ejecutan de verdad como subproceso pytest (test "meta") y pasan, tanto para el caso de resultado exitoso como para el caso de excepción capturada.
  - Alcance MVP documentado: solo funciones Python top-level (no anidadas, no métodos de clase).
- **Tests: 302** (8 nuevos en `tests/test_characterize.py`). 100% pasando.

## [2.9.0] — 2026-09-19

- **Feature 2 — Reverse-SDD (`yunta/reverse_sdd.py`)**: genera `SPEC.md`/`AGENTS.md` candidatos a partir de código existente sin especificaciones, abriendo adopción brownfield a la metodología SDD de yunta.
  - `scan_repository()`: reutiliza al 100% `adapter_registry.get_adapter().get_outline()/.find_symbols()` (los mismos adaptadores AST que ya usa `tools/symbols.py`) para construir un inventario condensado del repo sin volcar contenido completo de archivos (control de tokens).
  - `generate_spec_candidate()`/`generate_agents_candidate()`: condensan el inventario en un prompt y generan el Markdown vía un `Agent` sin tools (generación de texto puro, sin llamadas a herramientas).
  - `run_reverse_sdd()`: por defecto escribe `SPEC.md.candidate`/`AGENTS.md.candidate`; con `--apply` escribe el archivo real **solo si no existe ya** — nunca sobreescribe specs existentes (regla 6 de AGENTS.md).
  - `yunta/governance.py`: las regex de validación de estructura (`SPEC_HEADER_RE`, `PLAN_PHASE_RE`, `AGENTS_YUNTA_MARKER`) se extrajeron a constantes de módulo, compartidas con `reverse_sdd.py`, para que lo generado pase `yunta check` de inmediato (verificado con test de integración cruzada).
  - Comando: `yunta reverse-sdd [ruta] [--apply]`.
- **Tests: 294** (9 nuevos en `tests/test_reverse_sdd.py`, incluye integración con `governance.audit_repository`). 100% pasando (1 warning preexistente no relacionado en `test_voice_chaos.py`, de un hilo de chaos-testing simulando fallo de endpoint TTS).

## [2.8.0] — 2026-09-19

- **Feature 1 — Protocolo de Portabilidad de Sesión / Handoff (`yunta/handoff.py`)**:
  - `export_handoff()`/`import_handoff()`: empaquetan el estado de una sesión (mensajes, usage, permisos persistentes, sandbox activo, `cwd`, rama/commit de git) en un bundle JSON versionado (`schema_version`) que puede reanudarse en otro proceso, máquina o harness/IDE compatible (ej. entre ZCode y Antigravity). Reutiliza al 100% `serialize_messages`/`serialize_usage` de `yunta/session.py` — no reinventa el formato de mensajes.
  - Detección de "drift": si el commit de git guardado en el bundle difiere del commit actual al importar, se reporta como aviso no bloqueante (`drift_warning`), no como error.
  - `SessionPermissions.to_list()`/`.from_list()` (`yunta/agent.py`): serialización explícita y opt-in de los permisos persistentes de sesión — el objeto en sí sigue sin persistirse solo (invariante sin cambios).
  - Comandos: `yunta handoff export [ruta]` / `yunta handoff import <ruta>` (CLI single-shot, opera sobre la última sesión guardada en disco) y `/handoff export|import` en el REPL (con fidelidad completa: permisos y sandbox activo incluidos).
  - Límite de alcance documentado: yunta solo puede publicar y leer el schema — no puede forzar que otro harness lo adopte.
- **Tests: 271** (7 nuevos en `tests/test_handoff.py`). 100% pasando.

## [2.7.6] — 2026-09-19

- **Blindaje (Parte A de `docs/propuestas/2026-09-19-plan-7-features.md`)**: antes de construir features nuevas, se cerraron grietas confirmadas en el código existente.
  - **B1 — Fix de `LLM_FAST_MODEL` (bug de producción)**: `LiteLLMProvider.__init__` (`yunta/provider.py`) no aceptaba el parámetro `model=` que `yunta/tools/delegate.py::delegate_research` le pasaba para usar un modelo económico en subagentes de investigación. La llamada siempre lanzaba `TypeError`, capturado por un `except` silencioso que hacía caer la ejecución al provider compartido — `LLM_FAST_MODEL` nunca funcionó desde que se documentó como feature en v2.0. Se agregó el parámetro `model: str | None = None` (si viene, ignora `LLM_MODELS`/`LLM_MODEL` de entorno; retrocompatible al 100%) y se reemplazó el `except` mudo por un aviso explícito en consola ante fallo de construcción del provider rápido.
  - **B2 — Eliminado código huérfano (`yunta/budget.py`, `tests/test_session_budget.py`)**: `SessionBudget`/`check_budget` no tenían ningún import fuera de su propio test; la funcionalidad real de aviso por umbrales (P8) se implementó y quedó en producción vía `compact.py::TokenBudgetCompactor` (4 umbrales: 70/80/85/99%), dejando este módulo como prototipo abandonado sin borrar. Mantenerlo hubiera duplicado lógica de umbrales ya cubierta, violando la regla de minimalismo de `AGENTS.md`.
  - **B3 — Fix de colisión de nombres en `create_sandbox` (`yunta/sandbox.py`)**: el sufijo `int(time.time())` (resolución de 1 segundo) podía colisionar si `create_sandbox()` se llamaba más de una vez dentro del mismo segundo (ej. `/sandbox` tras un `discard` rápido), generando el mismo nombre de carpeta/rama. Se agregó un sufijo `uuid.uuid4().hex[:6]`.
  - **B4 — Tests de "wiring" (`tests/test_wiring_smoke.py`, nuevo)**: cubre las firmas reales con las que producción construye `LiteLLMProvider` (`model=` de `delegate.py`, `system=` de `cli.py`/scripts, sin argumentos de `json_server.py`) para que un desalineamiento de firma como el de B1 se detecte de inmediato en vez de quedar 6 versiones inadvertido tras un `except` mudo.
- **Tests: 267** (264 previos − 2 de `test_session_budget.py` eliminado + 6 nuevos: 1 en `test_provider.py`, 1 en `test_delegate.py`, 1 en `test_sandbox.py`, 3 en `test_wiring_smoke.py`). 100% pasando.

## [2.7.5] — 2026-09-19

- **Integración de Voz (STT/TTS) con Modo SDD y Experiencia Hands-Free (`yunta/voice.py`, `yunta/cli.py`, `yunta/decompose.py`)**:
  - **Aprobación por voz unificada (`make_voice_approval`)**: Compartida entre el REPL interactivo, despachos single-shot nacidos de voz (`yunta voice archivo.mp3 "tarea"`) y sub-agentes en lotes `--chunks`. Mantiene el flujo 100% manos libres en el ciclo SDD sin volver al teclado para aprobar herramientas.
  - **Soporte de voz en sub-agentes `--chunks` (`run_chunks`)**: `run_chunks` propaga el listener de voz a cada sub-agente por lote, preservando compatibilidad retroactiva completa con mocks/callers existentes.
  - **Lectura hablada en Single-shot y Chunks (`--speak`)**: Al concluir ejecuciones directas o descomposiciones por lotes con `--speak` activo, el agente lee el resultado final o el resumen de lotes en voz alta.
  - **Router con intenciones paramétricas locales (0 tokens LLM)**: `DEFAULT_PREFIX_VOICE_KEYWORDS` mapea frases como `"inicializa <idea>"`, `"inicia proyecto <idea>"` o `"crear proyecto <idea>"` directamente a `/init <idea>`, preservando tildes y mayúsculas de la especificación sin consultar al modelo.
- **Tests: 264** (3 nuevos tests: ruteo de prefijos hablados, máquina de estados de aprobación por voz y propagación de voz en `run_chunks`). 100% pasando.

## [2.7.4] — 2026-09-19

- **Pipeline de Prefetch en TTS (`yunta/tts.py`)**:
  - `speak()` sintetiza la oración N+1 en un hilo corto mientras la N se reproduce: la latencia de síntesis de Edge (~4.7s/oración) queda oculta tras el tiempo de habla (~6s), encadenando oraciones sin pausas. La única espera perceptible es la primera síntesis. Medido end-to-end: 5 oraciones en 29.9s (tiempo de habla puro) vs ~53s secuencial (**~44% menos**; en configuraciones con síntesis más lenta que el habla, el ahorro tiende a ~100% de la síntesis).
  - Test de regresión con FakeProvider temporizado: el total debe acercarse a `primera_síntesis + n×reproducción`, no a `n×(síntesis+reproducción)`.

## [2.7.3] — 2026-09-19

- **Banco de Pruebas y Métricas del Pipeline de Voz (`scripts/bench_voice.py` + `tests/test_voice_quality.py`)**:
  - `scripts/bench_voice.py`: benchmark por componente con reporte JSON (`.yunta/voice_bench_*.json`): fuzzy (precisión sobre mutaciones fonéticas sintéticas + falsos positivos), router (cobertura/latencia), STT (tiempo worker vs faster-whisper local + WER de desacuerdo entre motores), TTS (latencia de síntesis) y VAD en vivo (umbral calibrado y frase capturada). Flags modulares: `--fuzzy --router --stt --audio <ruta> --tts --vad --all`.
  - `tests/test_voice_quality.py`: gate de regresión en CI — precisión del fuzzy ≥90% sobre 370+ mutaciones, 0 falsos positivos con vocabulario técnico, cobertura 100% del router sin falsos positivos en frases largas.
  - **Línea base medida (2026-09-19, SDD.mp3 ~30s)**: fuzzy 93.6% precisión / 0 FP; router 100% cobertura / 0.008 ms; STT worker 9.4s vs local 63.3s (incluye carga de modelo), WER de desacuerdo 10.2%; TTS Edge 4.7s por oración (mejorable: streaming/paralelismo).
- **Fix de falsos positivos del fuzzy (encontrado por el propio benchmark)**:
  - `_FUZZY_EXEMPT`: sinónimos cuya forma colisiona con palabras comunes quedan fuera del matching difuso (exacto sigue OK): "reescribir"≈"escribir" y "apruebo"≈"prueba" mapeaban incorrectamente a acción editar/aprobar.

## [2.7.2] — 2026-09-18

- **Limpieza Fonética de Markdown para Síntesis de Voz TTS (`yunta/tts.py`)**:
  - Nueva función `clean_markdown_for_speech(text: str) -> str`: Normaliza y remueve sintaxis de Markdown antes de la síntesis de voz (`speak()`). Elimina asteriscos de negrita/cursiva, comillas invertidas de código inline, encabezados `#`, URLs largas y viñetas; formatea tablas a lenguaje pausado natural; y sustituye bloques de código extensos por `"código en pantalla"`. La salida visual en el terminal permanece 100% enriquecida con Markdown intacto.
- **Interrupción Inmediata y Salida Forzada Segura (`yunta/cli.py`, `yunta/tts.py`, `yunta/feedback.py`, `yunta/voice.py`)**:
  - **Doble Ctrl+C para Cierre Forzado**: Si el usuario presiona Ctrl+C dos veces en < 1.5s, la aplicación se cierra de forma inmediata e incondicional (`sys.exit(0)`), deteniendo cualquier hilo de audio o proceso en segundo plano.
  - **Cancelación Limpia de Turno**: Un solo Ctrl+C durante la generación o la locución corta el habla en curso (`stop_speaking()`), detiene el turno activo y devuelve el control al REPL.
  - **`wait_until_done()` Interrumpible (`yunta/tts.py`)**: Espera con bucles no bloqueantes de 0.1s para permitir que las señales del sistema operativo en Windows (`SIGINT`/Ctrl+C) se procesen al instante en lugar de quedar retenidas durante timeouts largos.
  - **Prevención de Bloqueos en Salida (`yunta/feedback.py`, `yunta/cli.py`)**: Reemplazado `except BaseException` por `except Exception` en `feedback.summarize` para evitar que `KeyboardInterrupt` sea tragado silenciosamente si el LLM demora o falla en el cierre de sesión.
  - **Nuevas Palabras Clave de Detención por Voz (`yunta/voice.py`)**: Soporte directo en `DEFAULT_VOICE_KEYWORDS` para "para", "parar", "stop", "detener", "cancela", "cancelar", "basta" (rutean a `/stop`), y "cállate", "callate" (rutean a `/speak off`).
- **Tests: 254** (3 nuevos tests: limpieza de Markdown básico, limpieza de tablas, ruteo de keywords de parada). 100% de la suite pasando.

## [2.7.1] — 2026-09-18

- **Corrección de Métrica ROI y Telemetría Per-Request (`yunta/provider.py`, `yunta/api.py`, `yunta/cli.py`)**:
  - **Extracción robusta de uso de tokens (`_extract_usage`)**: Soporte completo para respuestas de proveedores donde `usage` retorna como `dict`, objeto o `Usage`, con estimación fallback (`litellm.token_counter` / estimador de caracteres) cuando los endpoints custom o streaming omiten la clave `usage`. Resuelve el problema donde los tokens marcaban 0 y el ROI no se calculaba.
  - **Telemetría ROI automática tras cada solicitud (`print_roi_footer`)**: Imprime un resumen de telemetría y retorno económico (`Turno: +in / +out | Sesión: total tokens | ⚡ % caché | 💰 Ahorro API`) inmediatamente después de procesar cada prompt del usuario, tanto en ejecuciones CLI single-shot como en el REPL interactivo.
  - **Método `Usage.delta` (`yunta/api.py`)**: Cálculo de diferencia de consumo por turno para reporte exacto por solicitud.
- **Robustez y Calibración en Modo Voz Continua (`yunta/voice.py`, `yunta/cli.py`)**:
  - **Calibración VAD más sensible**: Umbral dinámico con piso ajustado a 90 (antes forzado a 350, lo que volvía sordo al micrófono en computadores portátiles) y soporte de anulación manual mediante la variable de entorno `YUNTA_VAD_THRESHOLD`.
  - **Ampliación de sinónimos de salida local**: Añadidos "terminar", "cerrar", "adios", "chao", "exit", "quit" a `DEFAULT_VOICE_KEYWORDS` para cerrar la sesión con 0 tokens de LLM.
  - **Limpieza de recursos**: Parada garantizada de `InputStream` en bloques `finally` tanto en `VoiceListener._loop` como al salir del REPL en `cli.py`.
  - **Manejo de Ctrl+C**: Captura limpia de `KeyboardInterrupt` en `voice_listener.get()` sin volcar trazas de error de Python.
- **Tests: 251** (100% de la suite pasando).

## [2.7.0] — 2026-09-18

- **Escucha Continua Manos Libres V5-1 (`yunta/voice.py` + `yunta/cli.py`)**:
  - Nueva clase `VoiceListener`: hilo daemon con captura `sounddevice` (16kHz, bloques de 0.5s) y **VAD por umbral RMS calibrado con 1s de ruido ambiental** (umbral ajustable vía `YUNTA_VAD_THRESHOLD`). Detecta inicio de voz, acumula hasta 1.5s de silencio y deposita cada frase transcrita en una cola. `yunta --voice` sin archivo ya no graba una sola toma: entra al REPL con micrófono siempre activo.
  - **Gate de eco**: el micrófono se pausa mientras el agente genera y mientras el TTS habla (nueva `wait_until_done()` en `tts.py`), evitando que yunta se escuche a sí misma; se reanuda incluso si `send()` falla (try/finally).
  - **Aprobación de tools 100% por voz**: nuevo hook `Agent.voice_approval` — al pedir permiso (`Aprobar bash?`), el callback reactiva el micrófono, espera "sí"/"siempre"/"no" (con fuzzy fonético) y vuelve a pausarlo. Sin respuesta en 180s rechaza por seguridad.
- **Fuzzy Matching Fonético V5-3 (`yunta/voice.py`)**:
  - `normalize_voice_response` ahora tolera errores de transcripción de Whisper en palabras sueltas vía Levenshtein (≤1 para palabras ≤5 chars, ≤2 para largas): "aprobau"→s, "avansar"→s, "cancelal"→c, "editat"→e. Frases largas quedan intactas (van al LLM).
- **Router de Palabras Clave Local — 0 consultas LLM (`yunta/voice.py`)**:
  - `route_keyword()` + `load_voice_keywords()`: frases habladas como "métricas", "salir", "limpiar", "rentabilidad" se resuelven a comandos REPL localmente sin gastar tokens. **Registro persistente ampliable por el usuario** en `.yunta/voice_keywords.json` (`{"frase": "/comando"}`) que sobrevive entre sesiones.
  - El REPL de voz anuncia cuándo una frase se resolvió localmente: `⚡ /metrics (palabra clave local, 0 consultas LLM)`.
- **Tests: 248** (5 nuevos: fuzzy, router, overrides de keywords JSON, segmentación VAD por silencio con audio sintético, API de pausa/reanudación). Smoke test de hardware: calibración y captura OK.

## [2.6.0] — 2026-09-15

- **Replanteo del TTS al estándar de yunta (`yunta/tts.py`, 2026-09-18)**:
  - Reproducción Windows reescrita con **MCI vía ctypes/winmm.dll** (reproduce MP3 nativo, 0 dependencias — mismo patrón que la grabación de micrófono en voice.py). La implementación anterior usaba `System.Media.SoundPlayer`, que solo reproduce WAV y fallaba silenciosamente ante el MP3 que produce el TTS.
  - `speak()` ahora es **no-bloqueante** (hilo daemon): el REPL sigue usable mientras habla; una respuesta nueva o un nuevo input corta la locución anterior vía `stop_speaking()` (verificado con test de corte). Antes bloqueaba el REPL con `PlaySync()` pese a documentar lo contrario.
  - Fallback de síntesis (edge-tts) ahora **anunciado en terminal** ("💡 voz: Edge TTS"), cumpliendo la regla de transparencia de yunta (sin fallbacks ocultos): `synthesize()` retorna `(audio, proveedor)` explícito.
  - Corregido User-Agent inconsistente ("Yunta/2.6.0" → "Yunta/2.5.1 Client") y fallback de reproducción no-Windows a ffplay/mpv.
  - Tests: 8 (3 nuevos: transparencia del fallback, no-bloqueo + corte, texto vacío). Total suite: 243.
- **Módulo Neutral de Síntesis de Voz Hablada TTS (`yunta/tts.py`)**:
  - `TTSProvider`: Motor agnóstico de salida de voz con fallback automático en 2 niveles: proveedor primario HTTP OpenAI-compatible (`/v1/audio/speech`, Cloudflare Worker) y respaldo secundario con Microsoft Edge TTS (`edge-tts` con voces neuronales en español de alta fidelidad `es-CL-CatalinaNeural`).
  - `chunk_text_by_sentences`: Troceo inteligente por oraciones y pausas de puntuación para iniciar la reproducción de audio en menos de 0.5s sin esperar a la finalización completa de la respuesta del LLM.
- **Respaldo Local Offline de Transcripción `faster-whisper` (`yunta/voice.py`)**:
  - Carga bajo demanda (*lazy import*) de `faster-whisper` en `transcribe_offline_local` para permitir transcripción local en CPU con 0 MB de costo de inicio.
- **Soporte CLI y REPL para Lectura Hablada (`yunta/cli.py`)**:
  - Bandera CLI `--speak` / `-s` y comando interactivo REPL `/speak [on|off]` para activar y desactivar la lectura en voz alta de las respuestas del agente. Un nuevo input del usuario corta la locución en curso.
- **Pruebas Unitarias Ampliadas (`tests/test_tts.py`)**:
  - Suite de pruebas unitarias verificando inicialización, troceo por oraciones y mecanismos de resiliencia del motor TTS.

## [2.5.1] — 2026-09-14

- **Diagnóstico y resilencia STT ante fallos del endpoint (`yunta/voice.py`)**:
  - Causa raíz encontrada transcribiendo `SDD.mp3` (8.9 MB): el worker de Cloudflare pasa el audio a Workers AI como array JSON de números (`[...Uint8Array]`), lo que infla el payload ~4-5x y Workers AI lo rechaza con `3006: Request is too large` de forma intermitente. El worker devolvía 500 genérico.
  - `AudioTranscriber.transcribe()` ahora reintenta 3x con backoff ante errores transitorios (429/5xx/timeout), y ante error "too large"/3006/413 **fragmenta el audio automáticamente** y reintenta por partes (guard anti-recursión bajo 256 KB).
  - `AudioChunker` soporta corte por bytes (~1 MB) para MP3 sin ffmpeg (frames autocontenidos; verificado empíricamente); para otros formatos sin ffmpeg falla con mensaje claro.
  - Marcas de tiempo de fragmentos ahora proporcionales a bytes con duración MP3 estimada por bitrate (antes `índice × 10 min`, incorrecto con cortes binarios).
  - Fix worker (`scratch/yunta-stt-worker`, pusheado a GitHub): error 3006 mapeado a HTTP 413 con mensaje accionable.
  - Verificado con audio real: `SDD.mp3` completo → 9.310 caracteres transcritos (algunos fragmentos requirieron retry).
- **Backlog v6 registrado (`docs/PLAN.md`, por instrucción humana)**:
  - Robustez del pipeline STT para audios largos, derivada del análisis comparativo contra WhisperX/faster-whisper/OpenAI Cookbook: V6-1 timestamps reales (ffprobe), V6-2 retry por chunk, V6-3 checkpoint incremental, V6-4 filtro de alucinaciones, V6-5 corte en silencios, V6-6 chunks en paralelo, V6-7 faster-whisper local con VAD, V6-8 diarización. Priorizados por nivel de impacto y costo.
- **Fix: crash de `/resume` en REPL (`yunta/agent.py`)**:
  - `AttributeError: property 'total_usage' of 'Agent' object has no setter` — el handler de `/resume` en el REPL asignaba `agent.total_usage` (propiedad de solo lectura). Se agregó un setter que restaura el usage acumulado de la sesión previa en `agent.usage`.
- **Offload de transcripts largos a scratch (`yunta/voice.py` + `yunta/cli.py`)**:
  - Nueva función `offload_transcript()`: transcripciones >8.000 caracteres se guardan en `.yunta/scratch/transcript_*.txt` y al agente solo le entra un preview de 500 chars con la ruta y estimación de tokens. Antes el transcript completo entraba de golpe al contexto y el SlidingWindow terminaba expulsándolo por ser el mensaje más viejo. Aplica tanto en `yunta voice` (arranque) como en `/voice` (REPL).
- **Continuidad entre fragmentos de Whisper (`yunta/voice.py`)**:
  - `AudioChunker` pasa ahora los últimos ~200 caracteres del fragmento anterior como `prompt` de Whisper al siguiente, manteniendo coherencia de nombres propios y terminología técnica en cátedras largas. Además muestra progreso por fragmento (`fragmento 3/12`).
- **Cancelación de transcripciones largas con Ctrl+C (`yunta/voice.py` + `yunta/cli.py`)**:
  - Ctrl+C durante la transcripción de un audio grande interrumpe el proceso, conserva los fragmentos ya transcritos (marcados como "[NOTA: transcripción parcial...]"), limpia los temporales y devuelve el control al REPL. En modo single-shot cancela limpiamente.
- **Fix: 'siempre' ahora aprueba la tool completa (`yunta/agent.py`)**:
  - Antes, responder "siempre" a "Aprobar bash?" memorizaba solo el primer token del comando (`("bash","git")`), por lo que cada comando nuevo volvía a preguntar. Ahora registra un comodín `("bash","*")` que aprueba toda la tool por el resto de la sesión. Tests actualizados a la nueva semántica.
- **Fix: `-y`/`--yes` ahora aplica también en el REPL (`yunta/cli.py`)**:
  - El agente del modo interactivo se creaba sin el callback `confirm`, así que `--yes` solo silenciaba aprobaciones en single-shot y --chunks, pero seguía preguntando en el chat interactivo.
- **Proveedor Secundario con Endpoint Propio (`yunta/provider.py`)**:
  - Nuevas variables `LLM_FALLBACK_MODEL` / `LLM_FALLBACK_API_BASE` / `LLM_FALLBACK_API_KEY`: si el proveedor primario falla (429/503/cuota), el router conmuta a un endpoint y credencial completamente distintos. Ejemplo verificado contra la doc oficial de Z.AI (`docs.z.ai/guides/llm/glm-5.3`): GLM-5.3 vía GLM Coding Plan usa protocolo OpenAI Chat en `https://api.z.ai/api/coding/paas/v4` con model ID `glm-5.3` (los suscriptores del Coding Plan no pueden usar el endpoint Anthropic). Antes la cascada `LLM_MODELS` solo cambiaba el nombre del modelo; ahora base URL y API key se conmutan junto con el modelo.
  - Documentado en `.env.example` y en la ayuda de variables del CLI.
- **Grabación en vivo ilimitada en REPL (`yunta/cli.py`)**:
  - `/voice` y `/listen` sin archivo ahora graban indefinidamente hasta presionar ENTER (igual que `yunta voice`), en lugar del límite fijo de 5 segundos que cortaba la conversación hablada dentro del chat.
- **Eliminado fallback oculto a Google (`yunta/voice.py`)**:
  - Se removió `recognize_google` como último recurso de transcripción: el audio del micrófono ya no se envía a un servicio cloud sin consentimiento explícito (regla #2 de AGENTS.md: sin fallbacks ocultos).
- **Errores de transcripción visibles (`yunta/voice.py`)**:
  - Un fallo HTTP contra el endpoint STT ahora imprime la causa real (URL y error) en lugar de solo "No se obtuvo transcripción".
- **Chunking sin ffmpeg falla con mensaje claro (`yunta/voice.py`)**:
  - Para audios >25 MB sin ffmpeg instalado se lanza `RuntimeError` indicando cómo instalarlo; el fallback anterior dividía el archivo en partes binarias crudas que producían fragmentos de audio corruptos.
- **Desacoplamiento de `LLM_API_BASE` para Modelos Gemini Nativos (`yunta/provider.py`)**:
  - Se corrigió el enrutamiento para asegurar que los modelos oficiales de Google Gemini (`gemini/gemini-3.6-flash`) omitan `api_base` cuando este apunta a proxies como Z.AI, conectando directamente con el endpoint oficial `https://generativelanguage.googleapis.com`.
- **Carga Nativa de Archivos de Entorno `.env` (`yunta/cli.py`)**:
  - Se agregó `_load_dotenv()` al inicio de `main()` para cargar automáticamente variables desde `.env` en la raíz del proyecto o `~/.yunta/.env` sin necesidad de librerías externas.
  - Creados los archivos [`.env`](file:///c:/Users/HP/.zcode/workspace/default/yunta/.env) y [`.env.example`](file:///c:/Users/HP/.zcode/workspace/default/yunta/.env.example), y actualizado `.gitignore` para proteger credenciales.
- **Soporte REPL Interactivo para `/resume` y `--resume` (`yunta/cli.py`)**:
  - Se añadió la captura de `/resume`, `--resume` y `-r` directamente dentro del bucle del REPL interactivo para cargar la sesión anterior desde `.yunta/session_state.json` sin enviar el texto de la bandera como prompt al modelo de IA.
- **Script de Modo Investigación para Transcripción de Audio en Lote (`scripts/investigar_audios.py`)**:
  - Evaluación masiva de transcripciones de audio (.mp3, .wav, .m4a, .ogg) con métricas e informe de rendimiento.

## [2.5.0] — 2026-09-13

### Corregido & Mejorado
- **Generalización y Polivalencia de `SYSTEM_PROMPT` (`yunta/cli.py`)**:
  - Se rediseñó `SYSTEM_PROMPT` para declarar formalmente a Yunta como un asistente autónomo e inteligente y compañero de trabajo versátil. Expande explícitamente sus capacidades más allá del desarrollo de software para abarcar tareas de **investigación, síntesis de información, análisis de datos, extracción de textos (multimedia/documentos/OCR) y redacción de informes**, preservando al 100% el soporte para metodología SDD, ejecución ágil de pruebas y verificación empírica.
- **Persistencia de Métricas de Uso de Tokens en Sesión (`yunta/agent.py`)**:
  - `_save_session_state()` invocaba `save_session()` enviando únicamente `self.usage` (métricas locales de ejecuciones de tools sin contadores de tokens de la API) en lugar de `self.total_usage`. Esto ocasionaba que `.yunta/session_state.json` se guardase con 0 tokens de entrada, salida y caché, mostrando `0.0% Hit Rate` y `$0.0000 USD` al ejecutar `python main.py --roi`.
  - `Agent.total_usage`: Corregido el cálculo para sumar las métricas de tokens de sesiones previas (`self.usage`) con los tokens de la llamada actual (`provider.total_usage`), preservando la continuidad histórica al reanudar sesiones con `--resume`.

### Agregado & Implementado
- **Pipeline Universal de Extracción Local de Texto Multiformato (Etapa 1 ➔ Etapa 2)**:
  - `yunta/extractors/`: Paquete de extractores locales deterministas sin llamadas a LLMs.
  - `extract_text_from_file`: Fábrica universal que convierte cualquier formato de entrada a Texto Plano (Prompt Base).
  - `yunta/extractors/audio.py`: Extracción de audio (.wav, .mp3, .m4a, .ogg) vía `System.Speech` / Whisper local.
  - `yunta/extractors/video.py`: Extracción de pistas de audio de videos (.mp4, .mkv, .avi) vía `ffmpeg` ➔ Texto Plano.
  - `yunta/extractors/document.py`: Extracción de documentos PDF (.pdf), Word (.docx) y texto (.txt, .md, .json) localmente.
  - `yunta/extractors/ocr.py`: OCR de imágenes (.png, .jpg, .webp) vía `Windows.Media.Ocr` nativo de Windows.
- **Filtro de Ruido Inicial y Puerta de Silencio en STT (`trim_initial_noise_and_silence`)**:
  - `yunta/voice.py`: Pre-procesamiento de señales de audio `.wav` antes de pasar por el reconocedor de voz. Elimina automáticamente los chasquidos de teclado (`noise_gate_ms=150ms`) y silencios pre-voz preservando 100ms de margen (*lead-in*) previo a la primera palabra hablada.
- **Previsualización, Edición Interactiva y Cancelación de Transcripción de Voz (`yunta/cli.py`)**:
  - Muestra la transcripción capturada antes de despacharla al agente (`Agent.send`), permitiendo al usuario:
    - `[ENTER / s]`: Enviar inmediatamente la transcripción.
    - `[e]`: Editar interactivamente el texto transcrito antes de enviarlo.
    - `[c]`: Cancelar la operación sin ejecutar ni consumir tokens.
- **Inyección Explícita de Idioma `language="es"` en STT (`yunta/voice.py`)**:
  - Pasa el parámetro `language="es"` en el payload `multipart/form-data` de Whisper para forzar el reconocimiento en español y evitar alucinaciones en inglés ante silencios o ruidos de fondo.
- **Comparador y Normalizador de Respuestas Rápidas por Voz/Texto (`normalize_voice_response`)**:
  - `yunta/voice.py`: Normalizador determinista que compara transcripciones habladas o textos con sinónimos fonéticos de aprobación (`"sí"`, `"aprobado"`, `"avanzar"`, `"abanzau"`, `"ok"`, `"dale"`, `"listo"` ➔ `s`), rechazo/cancelación (`"no"`, `"rechazado"`, `"cancelar"`, `"alto"`, `"stop"` ➔ `c`), edición (`"editar"`, `"modificar"`, `"cambiar"` ➔ `e`) y aprobación permanente (`"siempre"`, `"para siempre"`, `"sí a todo"`, `"aprobado a todo"` ➔ `siempre`).
  - `yunta/cli.py` & `yunta/agent.py`: Integrado en el menú de revisión de voz y en las confirmaciones interactivas de herramientas (`_approve`), permitiendo respuestas habladas o tipeadas rápidas sin requerir letras exactas.
- **Herramienta Nativa de Búsqueda Web (`web_search`) sin Dependencias (`yunta/tools/search.py`)**:
  - Implementación de `@registry.register("web_search")` basada en `urllib` nativo de Python y la API pública de Wikipedia/búsqueda web.
  - Elimina las secuencias de ensayo y error de 27 comandos `bash` en consolas de Windows CMD, reduciendo la latencia de investigación a 1 llamada HTTP (~0.2s).
- **Directiva Dinámica de Idioma en `SYSTEM_PROMPT` (`yunta/cli.py`)**:
  - `SYSTEM_PROMPT` actualizado para adaptarse dinámicamente al idioma del usuario (*"Responde e interactúa siempre en el idioma que esté utilizando el usuario (español, inglés, etc.). Tanto tus pensamientos como tus respuestas y archivos redactados deben escribirse en ese mismo idioma."*).
- **Auto-Detección Inteligente y Forzado de Razonamiento Profundo por Usuario (`yunta/intent.py`, `yunta/agent.py`, `yunta/cli.py`)**:
  - `IntentClassifier.evaluate_reasoning(prompt, user_override)`: Evalúa si un prompt requiere razonamiento profundo (`HIGH`, `MEDIUM`, `OFF`) mediante clasificación automática de complejidad y palabras clave en tiempo de ejecución.
  - Comando interactivo `/think [high|medium|low|off|auto]` en el REPL y flag CLI `--think` / `--think=high|off` / `-t` para forzar o desactivar explícitamente el modo de pensamiento.
  - Indicador visual dinámico en la consola (`🧠 Razonamiento Profundo (Thinking)...`) cuando la tarea activa el modo de razonamiento.
- **Captura Directa de Bytes y Decodificación UTF-8 en Subprocesos Windows (`yunta/tools/bash.py`)**:
  - Elimina el uso de `text=True` en `subprocess.run` para capturar la salida estándar y de error como bytes crudos, decodificándolos explícitamente en Python con `.decode("utf-8", errors="replace")`. Evita la creación de hilos de lectura de texto (`_readerthread`) con la codificación `cp1252` predeterminada de Windows y resuelve 100% las excepciones `UnicodeDecodeError`.
- **Prevención de Bucle Recursivo de Scratch Files (`yunta/agent.py`)**:
  - `_maybe_offload_result`: Exime a `read_file` de re-offloadear salidas al leer archivos en `.yunta/scratch/` o con parámetros de paginación (`offset`/`limit`), evitando la generación infinita de archivos temporales anidados al inspeccionar resultados extensos.
- **Despacho Directo de Subcomandos CLI de Telemetría (`yunta/cli.py`)**:
  - Implementación del despacho directo en CLI para `yunta roi` / `yunta --roi` (Dashboard ROI y retorno económico), `yunta tokens` / `yunta --tokens` / `yunta metrics` (desglose de tokens) y `yunta context` / `yunta --context` (presupuesto de contexto) desde la terminal sin requerir llamar a la API ni abrir el REPL.
- **`tests/test_search.py`, `tests/test_provider.py`, `tests/test_intent.py`, `tests/test_agent.py` & `tests/test_cli.py`**: Suite ampliada a 232 pruebas unitarias pasadas al 100%.

---

## [2.4.0] — 2026-09-13

### Agregado & Implementado
- **Prompts por Voz y Dictado Manos Libres (Zero-Typing)**:
  - `yunta/voice.py`: Módulo nativo `AudioTranscriber` para transcripción de audio vía HTTP `multipart/form-data` a endpoints compatibles con Whisper (OpenAI, Groq `whisper-large-v3`, Ollama Whisper).
  - Captura desde micrófono local `record_microphone` y soporte para archivos `.wav`, `.mp3`, `.m4a`, `.ogg`, `.webm`.
  - CLI `yunta -v` / `yunta --voice [archivo.mp3]` y comando interactivo `/voice` en el REPL.
- **Soporte para Grabaciones Extensas (Cátedras de Medicina de 2 a 4+ Horas)**:
  - `AudioChunker`: Fragmentación basada en Voice Activity Detection (VAD) / silencios (`silencedetect`) para no trocear palabras compuestas por la mitad.
  - `yunta/tools/voice.py`: Herramientas `@registry.register("transcribe_audio")` y `generate_study_notes` que generan resúmenes ejecutivos por temas, glosarios médicos/farmacológicos, tarjetas Anki Q&A y diagramas Mermaid.
- **Enrutamiento por Intención (`yunta/intent.py`)**:
  - `IntentClassifier`: Clasificación automática de tareas entre `SOFTWARE_IMPLEMENTATION` (aplica compuertas SDD, git hooks, validación atómica `.tmp` y compilación) y `RESEARCH_AND_CONSULTING` (bypass completo de compuertas SDD y git hooks para resúmenes, cátedras y consultoría).
- **Adaptadores Modales Carga Bajo Demanda (`InputAdapterRegistry`)**:
  - `yunta/adapters.py`: Expansión con `InputAdapterRegistry` para carga perezosa (0 MB al inicio) de adaptadores multimedia (`AudioInputAdapter`, `VisionInputAdapter`).
- **Pruebas Unitarias**:
  - `tests/test_intent.py`, `tests/test_voice.py` y `tests/test_voice_lazy.py` (100% test pass rate).

---

## [2.3.0] — 2026-09-12

### Agregado & Port C# Nativo (.NET 10)
- **Port 100% generado mediante Yunta CLI (`python main.py -y ...`)** en `scratch/yunta-csharp/`:
  - `Yunta.Core/`: Módulos nativos `Api.cs` (tipos neutrales `Message`, `Block`, `ToolDef`, `Usage`), `Adapters.cs` (adaptadores de lenguaje bajo demanda), `Tools.cs` (escritura atómica, reemplazo, listado, búsqueda de símbolos y AST), `Provider.cs` (`LiteLlmProvider` con `HttpClient` y semántica Litellm) y `Agent.cs` (`YuntaAgent` con bucle autónomo).
  - `Yunta.Cli/`: Aplicación de consola REPL e interfaz one-shot (`-y` / `--yolo`) alineada con `main.py`.
  - `Yunta.Tests/`: Suite de 19 pruebas unitarias xUnit verificando serialización, tools, bucle del agente y tolerancia a respuestas JSON.
  - **Métricas**: 0 dependencias externas (solo SDK .NET 10), 100% test pass rate (19/19 en 335 ms), 0 errores y 0 warnings de compilación.

---

## [2.2.0] — 2026-09-12

### Agregado & Implementado
- **Soporte Polyglot Ampliado para 20+ Lenguajes con Carga bajo Demanda (Lazy-Loading)**:
  - `yunta/adapters.py`: Expansión de `LanguageAdapterRegistry` con adaptadores dinámicos para **Python, JavaScript/TypeScript, Go, Rust, Java, Kotlin, Scala, Groovy, C#, F#, C/C++, PHP, Ruby, Swift, Shell/Bash/Powershell, SQL y JSON/YAML/TOML**.
  - Cada adaptador se importa e instancia en memoria de forma perezosa (*lazy-loading*) únicamente cuando el agente interactúa con un archivo de su extensión, manteniendo el consumo inicial de memoria en cero.
  - `yunta/tools/files.py`: Refactorización de `_validate_content` para delegar la validación sintáctica atómica previa a la escritura en el registro de adaptadores según la extensión del archivo.
  - **Comando CLI `yunta update` / `yunta --update`**: Permite actualizar Yunta a la versión más reciente directamente desde la terminal (soporta actualización vía PyPI `pip` o desde el repositorio `git`).
  - `tests/test_lazy_adapters.py`: Suite de 11 pruebas unitarias verificando la instanciación bajo demanda y la funcionalidad de extracción/validación por lenguaje.


---

## [2.1.0] — 2026-09-11


### Agregado & Implementado
- **V4-1 — Indexación Semántica de Código con AST (`find_symbol` y `get_ast_outline`)**:
  - `yunta/tools/symbols.py`: Módulo estático nativo sin dependencias externas usando `ast` para buscar firmas de clases/funciones y generar esquemas estructurados del código base.
  - `tests/test_symbols.py`: 4 pruebas unitarias verificando búsquedas exactas, parciales, esquemas e incompatibilidades sintácticas.
- **V4-2 — Paralelización Concurrente de Subagentes (`delegate_batch`)**:
  - `yunta/tools/delegate.py`: Herramienta para despachar múltiples subtareas de investigación en paralelo mediante `ThreadPoolExecutor` con consolidación estructurada de respuestas.
  - `tests/test_delegate_batch.py`: 3 pruebas unitarias verificando paralelismo y manejo defensivo de errores.
- **V4-3 — Inspección Multimodal (`read_image` y `BlockType.IMAGE`)**:
  - `yunta/api.py` y `yunta/provider.py`: Soporte para el bloque de contenido `BlockType.IMAGE` traduciendo imágenes a Data URLs Base64 para modelos con visión (GPT-4o, Gemini 2.5, Claude 3.7).
  - `yunta/tools/vision.py`: Herramienta de lectura e inspección de imágenes (PNG, JPEG, WebP, GIF) de hasta 5MB.
  - `tests/test_vision.py`: 4 pruebas unitarias validando encoding Base64, caps de peso y payload en LiteLLM.
- **V4-4 — Extensión Gráfica Nativa de IDE (`yunta-vscode-extension`)**:
  - Repositorio `c:\Users\HP\.zcode\workspace\default\yunta-vscode-extension`: Cliente TypeScript para `yunta serve-mcp` / `yunta serve-json` y modo subproceso CLI.
  - Comandos VS Code: `yunta.runTask`, `yunta.audit`, `yunta.showMetrics`, `yunta.initProject`.
  - Panel WebView ROI: `src/roiPanel.ts` para visualización gráfica de dólares ahorrados por Prompt Caching, tokens evitados y uso.
  - Test suite TypeScript: `src/test/suite/extension.test.ts` (3 tests 100% OK).

---

## [2.0.0] — 2026-09-09

### Agregado & Mejorado
- **v2.0 — Git Pre-Commit Hooks SDD (`yunta hooks` / `yunta install-hooks`)**:
  - `yunta/hooks.py`: módulo gestor e instalador de hooks pre-commit para ejecutar la auditoría determinista local `yunta check --tests` automáticamente antes de cada `git commit`, impidiendo commits con código roto o especificaciones desobedecidas.
  - `yunta/cli.py`: comandos `yunta hooks`, `yunta install-hooks` y `yunta uninstall-hooks`.
  - `tests/test_hooks.py`: suite de pruebas unitarias.
- **v2.0 — Multi-Model Routing por Especialización de Subagente (`LLM_FAST_MODEL`)**:
  - `yunta/tools/delegate.py`: soporte para variable de entorno `LLM_FAST_MODEL` asignando modelos ultra-rápidos y económicos (ej. `gpt-4o-mini`, `gemini-2.5-flash`) a subagentes de investigación de solo lectura.
- **v2.0 — Protocolo Completo MCP Resources & Prompts (`server_mcp.py`)**:
  - Exposición nativa de los artefactos de especificación `SPEC.md`, `PLAN.md`, `AGENTS.md` como recursos MCP (`resource://yunta/spec`, `resource://yunta/plan`, `resource://yunta/agents`) y plantillas de prompt SDD (`yunta/sdd_init`, `yunta/review_code`).
  - `tests/test_server_mcp.py`: pruebas unitarias de recursos y prompts vía JSON-RPC.

---

## [1.3.0] — 2026-09-09

### Agregado & Mejorado
- **P9 — Descomposición de Specs Complejas en Subtareas (`delegate_subtask`)**:
  - `yunta/tools/subtask.py`: herramienta nativa `delegate_subtask(task, target_files)` que delega modificaciones enfocadas en máximo 1-2 archivos a un `Agent` interno con contexto limpio y acotado, previniendo la contaminación e inflación del historial en tareas complejas multi-archivo.
  - `tests/test_subtask.py`: suite de 4 pruebas unitarias verificando límites de archivos, validación de parámetros y ejecución delegada.
- **V3-10 — Aprobaciones de Herramientas canalizadas vía MCP (`yunta/permissions` y `yunta/approve`)**:
  - `yunta/server_mcp.py`: adición de métodos JSON-RPC `yunta/permissions` y `yunta/approve` para que clientes MCP o extensiones de IDE puedan consultar y otorgar permisos de ejecución programáticamente sin requerir interacción manual en el REPL.
  - `tests/test_server_mcp.py`: pruebas unitarias de consulta y concesión de permisos vía RPC.
- **V3-11 — Modo Servidor `serve-json` para Integraciones CLI Ligeras (`JSONL`)**:
  - `yunta/json_server.py`: servidor de eventos en tiempo real en formato JSON-Lines (`JSONL`) a través de `stdout` (`serve_json_stream` y `serve_json_stdin`). Emite eventos estructurados (`system`, `text_delta`, `tool_call`, `tool_result`, `usage`, `done`, `error`) permitiendo a extensiones de IDE y scripts CLI consumir ejecuciones sin montar el protocolo MCP completo.
  - `yunta/cli.py`: despacho de comando `yunta serve-json` y alias `yunta json`.
  - `tests/test_json_server.py`: suite de pruebas unitarias verificando la emisión de eventos y el procesamiento desde `stdin`.

---

## [1.2.1] — 2026-09-09

### Agregado & Mejorado
- **P7 — Degradación Progresiva ante Agotamiento de Cuota (`RateLimitError` / `QuotaExhausted`)**:
  - `yunta/resilience.py`: ampliación de marcadores de cuota e identificación de excepciones de autenticación y límites de API (`401`, `403`, `429`, `insufficient_quota`, `resource_exhausted`).
  - `yunta/agent.py` & `yunta/cli.py`: auto-guardado defensivo de `.yunta/estado-de-tarea.md` (resumen de tarea hecha y pasos pendientes) y sincronización con `.yunta/session_state.json` para permitir la reanudación transparente mediante `yunta --resume` sin perder el contexto ni el trabajo realizado.
  - `tests/test_quota_graceful.py`: suite de 5 pruebas unitarias verificando captura de cuota, aviso en terminal y guardado de sesión.
- **P8 — Presupuesto de Sesión y Control de Tokens (`SessionBudgetManager`)**:
  - `yunta/budget.py`: nuevo gestor de presupuesto de tokens para prevenir consumos accidentales desmedidos. Emite advertencias en consola al alcanzar el 70% del presupuesto de la sesión y ejecuta un guardado de estado con salida limpia al 90%.
  - `yunta/agent.py`: verificación automática de presupuesto en cada turno del bucle del agente.
  - `tests/test_session_budget.py`: suite de 6 pruebas unitarias verificando umbrales, advertencias y guardado automático.
- **Seguridad de Archivos — Verificación de Frontera del Workspace (*Workspace Boundary Check*)**:
  - `yunta/tools/files.py`: función `_check_boundary()` aplicada a `read_file`, `write_file` y `str_replace` para prevenir accesos no autorizados mediante Path Traversal (`../`) fuera del directorio de trabajo actual (`Path.cwd()`), preservando rutas absolutas temporales en entornos de prueba.
  - `tests/test_tools.py`: 4 pruebas unitarias adicionales validando el rechazo de accesos fuera de la frontera.

---

## [1.2.0] — 2026-09-09

### Agregado
- **V3-1 — Detección de Doom-Loops**:
  - `yunta/agent.py`: fingerprinting de `(tool_name, raw_input)` en ventana deslizante de 20 llamadas. A partir de 3 repeticiones se inyecta un aviso de advertencia en `tool_result`; al alcanzar 5 repeticiones se fuerza la pausa y confirmación explícita `[PAUSA DOOM-LOOP]` del usuario, previniendo bucles infinitos en modo autónomo.
  - `tests/test_agent.py`: pruebas unitarias `test_doom_loop_detection_warning` y `test_doom_loop_detection_pause`.
- **V3-5 — Recordatorios como `role: user` en Puntos de Decisión**:
  - `yunta/agent.py`: re-inyección automática de un bloque de recordatorio de sistema (`role: user`) cada 15 ejecuciones de herramientas para evitar la deriva de contexto en sesiones largas.
  - `tests/test_agent.py`: prueba unitaria `test_decision_point_reminder_injected_after_15_calls`.
- **V3-6 — Recuperación de Errores Clasificada**:
  - `yunta/errors.py`: nuevo módulo con clasificador `classify_tool_error` en 6 categorías accionables (`FILE_NOT_FOUND`, `PERMISSION_DENIED`, `TIMEOUT`, `PARSE_OR_SYNTAX`, `GIT_CONFLICT`, `UNKNOWN`) con plantillas de sugerencia para orientar al LLM tras un fallo de herramienta.
  - `yunta/agent.py`: integración del clasificador en el manejo de errores de ejecución de herramientas.
  - `tests/test_errors.py`: suite de 6 pruebas unitarias.
- **V3-4 — Compactación por Etapas basada en Presupuesto de Tokens**:
  - `yunta/compact.py`: nueva clase `TokenBudgetCompactor` con 4 umbrales progresivos (70% aviso en contexto, 80% enmascaramiento de tool_results largos, 85% pruning seguro de mensajes antiguos, 99% resumen sintético defensivo).
  - `yunta/cli.py`: comando `/context` en el REPL que reporta la cantidad de mensajes, tokens estimados en contexto y porcentaje consumido del presupuesto (`YUNTA_MAX_TOKENS`).
  - `tests/test_token_compact.py`: suite de 5 pruebas unitarias.
- **V3-9 — Aislamiento en Git Worktree (`/sandbox`)**:
  - `yunta/sandbox.py`: módulo con funciones `create_sandbox()` y `cleanup_sandbox()` para crear git worktrees temporales aislados en `.yunta/sandboxes/` con merge opcional al concluir.
  - `yunta/cli.py`: comandos `/sandbox`, `/sandbox merge`, `/sandbox discard` en el REPL CLI.
  - `tests/test_sandbox.py`: prueba unitaria completa de ciclo de vida e integración git.

---

## [1.1.1] — 2026-09-09

### Agregado
- **V3-8 / O1-d — Presupuesto de arranque medible (`startup_tax`)**:
  - `yunta/provider.py`: cálculo e inspección de tokens de arranque aproximados (`provider.startup_tax` y `estimate_startup_tax()`) contando payload inicial de system prompt y schemas de herramientas con `litellm.token_counter` (y fallback `len//4`).
  - `yunta/api.py` & `yunta/cli.py`: reporte de `Startup tax (payload inicial)` en `/metrics` y `/tokens` con objetivo `<5,000` tokens.
  - `tests/test_provider.py`: prueba unitaria `test_startup_tax_calculation` (123 tests 100% verde).
- **V3-3 — Offloading de salidas largas a scratch files**:
  - `yunta/agent.py`: método `_maybe_offload_result` que intercepta salidas de herramientas o comandos que superen los 8.000 caracteres, volcando el contenido completo en `.yunta/scratch/output_{timestamp}_{tool_name}.txt` e inyectando al contexto del LLM únicamente un preview de 500 caracteres con la referencia al archivo scratch.
  - `tests/test_agent.py`: prueba unitaria `test_long_output_offloaded_to_scratch_file` (124 tests 100% verde).
- **Documentación de Comandos y CLI**:
  - `README.md`, `README_en.md`, `docs/quickstart.md`, `docs/quickstart_en.md`, `yunta/cli.py`: actualización y sincronización completa de la descripción de invocación desde el CLI (`yunta`, `yunta init`, `yunta check`, `yunta ide-init`, `yunta serve-mcp`, `yunta --resume`, `yunta "instrucción"`, `yunta --version`, `yunta --help`), comandos interactivos del REPL (`/permissions`, `/roi`, `/metrics`, `/tokens`, `/undo`, `/init`, `/clear`, `/exit`, `Ctrl+C`) y variables de entorno (`YUNTA_BLOCKLIST_EXTRA`, `YUNTA_ALLOW_FORCE`).

---

## [0.1.0] — 2026-09-06

### Agregado
- **Núcleo del harness** (v1, núcleo mínimo):
  - `yunta/api.py` — tipos neutrales de conversación: `Message`, `Block`,
    `ToolDef`, `Response`, `Usage`, `StopReason`. Ningún tipo de SDK externo
    cruza esta frontera; es el idioma común de todo el harness.
  - `yunta/provider.py` — `LiteLLMProvider`: única capa que habla con modelos.
    Traduce los tipos neutrales al formato unificado de LiteLLM y viceversa
    (incluye el split de tool_results a mensajes `role:"tool"`).
  - `yunta/agent.py` — bucle del agente: agrega mensaje user → consulta
    provider → ejecuta tool calls (con aprobación) → agrega resultados → repite
    hasta `stop_reason ≠ tool_use` o `max_turns`. Los errores de tools vuelven
    al contexto como `tool_result` con `is_error=True` para que el modelo
    reintente.
  - `yunta/compact.py` — estrategias `NoCompaction` y `SlidingWindow`
    (recorte en límites seguros: antes de un mensaje user sin tool_results).
  - `yunta/tools/` — registro de tools con decorador `@registry.register`;
    auto-registro al importar el paquete.
  - `yunta/tools/bash.py` — tool `bash` con timeout de 30s y aprobación.
  - `yunta/tools/files.py` — tools `read_file` y `write_file` (write con
    aprobación).
  - `main.py` — REPL con comandos `/clear`, `/tokens`, `/exit`.
  - `requirements.txt`, `README.md`.

### Decisiones de diseño
- **Agnóstico al proveedor por construcción**: `LLM_MODEL` es obligatorio y no
  existe fallback ni proveedor por defecto; sin esa variable el proceso termina
  con un error que muestra ejemplos de configuración para varios proveedores.
  Variables soportadas: `LLM_MODEL`, `LLM_API_KEY`, `LLM_API_BASE`.
- **Sin dependencias de SDKs de proveedores**: LiteLLM es la única capa de
  acceso, por lo que OpenAI, Anthropic, Gemini, Ollama, OpenRouter, vLLM, Groq,
  DeepSeek, etc. funcionan sin cambios de código.
- **Sin frameworks de agentes**: el bucle, los permisos y el contexto son
  propios; nada de LangChain/Agents SDK.

### Verificación
- Compilación sin errores de los 9 archivos Python.
- Smoke test del bucle completo con provider falso: tool call `write_file`
  aprobada, archivo escrito, conversación con estructura correcta
  (user → assistant/tool_use → user/tool_result → assistant/text).
- Total: ~500 líneas.

### Documentación de gobernanza (mismo día, post-lanzamiento)
- `AGENTS.md` — reglas para cualquier agente/IDE que modifique el proyecto:
  aislamiento del SDK, sin proveedor default, sin frameworks, registro
  obligatorio en changelog, minimalismo. Es la convención multi-IDE que la
  mayoría de los agentes leen automáticamente.
- `docs/PLAN.md` — plan de la iniciativa compartible: decisiones fundacionales,
  tabla de fases con estado (1-6 completadas; 7 validación multi-proveedor y
  8 difusión pendientes) y backlog no comprometido.
- Motivo: el plan solo existía en conversación y se perdería al compartir la
  carpeta; ahora plan + avance + reglas viajan con el código.

---

## [0.1.1] — 2026-09-06

### Agregado
- `tests/test_provider.py` — suite pytest (4 tests) que valida el
  agnosticismo del provider interceptando `litellm.completion`:
  1. Traducción OpenAI: system prompt, assistant con tool_calls,
     tool_results como mensajes `role:"tool"`, schemas con envelope,
     acumulación de usage.
  2. Mismo core para Anthropic: solo cambia `LLM_MODEL`.
  3. Endpoint custom vía `LLM_API_BASE` (Ollama/vLLM/OpenRouter).
  4. Ausencia de `LLM_MODEL` → error de arranque con mensaje claro.

### Modificado
- `docs/PLAN.md` — Fase 7 marcada ✅ con nota; backlog de tests marcado parcial.

### Limitación registrada
- Sin credenciales ni Ollama local en el entorno de desarrollo: la
  validación llega hasta la capa de traducción (kwargs que recibe LiteLLM).
  El enrutado real contra APIs vivas queda como smoke manual del usuario
  final con su propio modelo.

### Verificación
- `python -m pytest tests/ -q` → 4 passed.

---

## [0.1.1 — difusión] — 2026-09-06

### Agregado
- `pyproject.toml` — paquete instalable (`pip install -e .`) con entry point
  `yunta` y extra `dev` (pytest).
- `yunta/cli.py` — REPL movido a módulo instalable; `main.py` queda como
  wrapper fino.
- `.gitignore`.
- Repo git inicializado; commit base `584a8ae`.

### Modificado
- `docs/PLAN.md` — Fase 8 en progreso con estado de empaquetado.

### Integración multi-IDE (verificada contra documentación oficial)
- **ZCode**: lee `AGENTS.md` de la raíz — ya presente.
- **Antigravity**: soporta `AGENTS.md`/`GEMINI.md` en la raíz del workspace
  (además de `.agents/rules/`) — ya compatible sin cambios.

### Verificación
- `pip install -e .` OK; `from yunta.cli import main` OK; entry point
  responde con error claro sin `LLM_MODEL`; `pytest` → 4 passed.

---

## [0.2.0] — 2026-09-06

### Agregado
- **Diff unificado en la aprobación de `write_file`**: `agent.py` calcula el
  diff (difflib) contra el contenido actual del archivo y lo muestra antes
  del y/n. `confirm` ahora recibe `(name, detail)`.
- **Carga de `AGENTS.md` del proyecto** en el system prompt (`cli.py`):
  si existe `AGENTS.md` en el directorio de trabajo, se adjunta como
  contexto del proyecto.
- `tests/test_agent.py` (6), `tests/test_tools.py` (5), `tests/test_compact.py` (3).

### Corregido
- **Bug en `SlidingWindow.compact`**: cortaba *después* del mensaje user
  seguro, dejando un mensaje assistant (o tool_result huérfano) al inicio
  del historial restante. Ahora corta *en* el primer user seguro desde el
  exceso. Detectado por `test_sliding_window_cuts_at_safe_boundary`.

### Modificado
- `pyproject.toml` → versión 0.2.0.

### Verificación
- `pytest` → 18 passed (provider 4, agent 6, tools 5, compact 3).
- Compilación sin errores.

---

## [0.2.1 — publicación] — 2026-09-06

### Publicado
- Repo público: **https://github.com/j0sp0nc3/yunta-harness**
- Rama `master`, historial completo (v0.1.1 → v0.2.0) con autoría real.
- Autenticación GitHub CLI configurada para futuras operaciones.

### Verificación
- `gh repo view` confirma: PUBLIC, rama master, commits `945a049` y `1ae1d8f`.

---

## [0.2.2] — 2026-09-06

### Agregado
- `docs/logo.svg` — identidad gráfica: dos cabezas de buey en silueta
  (estilo grabado, inspirado en la estética de mascotas de proyectos
  libres) unidas por una yunta de madera curva con anillo central.
  Paleta: pizarra oscura `#1f2937`, crema `#f5eeda`, madera `#b45309`.
- Logo integrado en la cabecera de `README.md`.

---

## [0.2.3] — 2026-09-06

### Modificado
- **Logo oficial reemplazado**: `docs/logo.png` (1024×559, generado con
  modelo de imagen y curado por el autor) pasa a ser el logo del proyecto
  en el README. El boceto vectorial previo queda como `docs/logo.svg`
  (referencia de paleta y composición).

---

## [0.2.4] — 2026-09-06

### Agregado
- `scripts/prueba_glm.py` — prueba de integración de bucle completo
  (write_file con diff + read_file + respuesta) contra un modelo real.
- `Provider.system` — propiedad pública (antes `._system`).

### Validación real (Fase 8)
- **ZCode + GLM-4.7 (Z.ai, vía Coding Plan)**: prueba completa OK.
  Config: `LLM_MODEL=openai/glm-4.7`,
  `LLM_API_BASE=https://api.z.ai/api/coding/paas/v4`, `LLM_API_KEY`.
  Resultado: archivo creado y leído por el modelo, 3192/137 tokens.
- Nota: el prefijo nativo `zai/` requiere saldo API por consumo; el
  Coding Plan funciona por el endpoint OpenAI-compatible de arriba.

---

## [0.3.0] — 2026-09-06

### Agregado
- **Capa de auto-feedback** (`yunta/feedback.py`): el harness se mejora a
  sí mismo entre sesiones.
  - Al salir (`/exit`), el modelo auto-evalúa la sesión (TAREA /
    RESULTADO / LECCION) y se persiste en `.yunta/learnings.md`.
  - Al arrancar, las últimas 5 lecciones se inyectan en el system
    prompt ("Lecciones de sesiones anteriores — aprendidas por ti mismo").
  - Best-effort: fallos de red o formato se ignoran sin romper el cierre.
- **Guardas de honestidad** en `SYSTEM_PROMPT` (derivadas del incidente
  de alucinación detectado en la demo): prohibido narrar acciones no
  ejecutadas con tools reales; verificación obligatoria tras editar.
- `tests/test_feedback.py` (6 tests).

### Motivo
Durante la demo real, un prompt mínimo indujo al modelo a fabricar una
transcripción entera de acciones nunca ejecutadas. Dos conclusiones que
esta versión materializa: (1) el prompt debe exigir verificación y
honestidad sobre tools; (2) las lecciones de cada sesión deben volver al
agente en la siguiente — auto-mejora sin infraestructura pesada.

### Validación
- Circuito real con GLM-4.7 (Z.ai Coding Plan): historial de sesión →
  auto-evaluación → lección persistida → inyección verificada en el
  system prompt del arranque siguiente.
- `pytest` → 24 passed.

---

## [0.4.0] — 2026-09-06

### Agregado
- **Tools de búsqueda** (`yunta/tools/search.py`):
  - `grep`: regex recursivo sobre directorio, salida `ruta:linea: texto`,
    `max_results` (default 50), regex inválido → `ValueError`.
  - `glob`: patrones tipo `**/*.py` vía `Path.glob`, rutas POSIX ordenadas.
- `tests/test_search.py` (5 tests).

### Proceso — primer dogfooding del harness
- Implementado por **yunta mismo** (GLM-4.7 vía Coding Plan): leyó las
  convenciones del repo (AGENTS.md + files.py), escribió tool + tests,
  verificó con pytest y respetó el alcance (solo 2 archivos nuevos).
- Revisión humana posterior encontró 1 hueco de integración: `cli.py`
  no importaba `search`, por lo que el REPL real no registraba las tools
  (los tests del agente las importaban directamente y lo enmascaraban).
  Corregido agregando el import.

### Modificado
- `yunta/cli.py`: importa `search` junto a `bash`/`files`.

### Verificación
- `pytest` → 29 passed. Registro de tools del REPL verificado.

---

## [0.5.0] — 2026-09-06

### Agregado
- **Memoria persistente entre sesiones** (`yunta/tools/memory.py`):
  - `remember(content, kind?, tags?)`: guarda en `.yunta/memory.json`
    (configurable vía `MEMORY_PATH`); kind: fact/preference/decision.
  - `recall(query)`: búsqueda case-insensitive por palabras en content y
    tags, máximo 10 más recientes, formato `[fecha] (kind) content [tags]`.
- `tests/test_memory.py` (5 tests).

### Proceso — segunda ronda de dogfooding
- Implementado por **yunta mismo** (GLM-4.7): leyó convenciones, escribió
  tool + tests, detectó por sí solo que faltaba el import en `cli.py`
  (la lección de v0.4.0 se aplicó sin que se lo pidiera explícitamente),
  lo corrigió por la vía autorizada y verificó las 7 tools registradas.
- Desviación de alcance detectada en revisión humana: el agente también
  subió `version` en `pyproject.toml` a 0.5.0 (no autorizado; la intención
  era correcta según convención y se conserva). Sin otros cambios fuera
  de alcance; sin archivos temporales residuales.
- El agente además auto-limpió una línea confusa en su propio test antes
  de cerrar.

### Modificado
- `yunta/cli.py`: importa `memory`.
- `pyproject.toml`: versión 0.5.0.

### Verificación
- `pytest` → 34 passed. Registro de 7 tools en el REPL verificado.
- Prueba funcional real: remember→persistencia en JSON→recall con match,
  case-insensitive y sin resultados. CHANGELOG y docs actualizados a mano.

---

## [0.6.0] — 2026-09-06

### Agregado
- **Subagente de investigación read-only** (`yunta/tools/delegate.py`):
  - Tool `delegate_research(task)`: crea un `Agent` interno restringido a
    `read_file`/`grep`/`glob`, max_turns 15, y devuelve sus hallazgos.
  - Provider inyectado vía `set_provider()` desde el CLI (sin providers
    por defecto: sin configurar, error claro).
- `Agent(tools=...)`: parámetro opcional de subconjunto de tools — primer
  cambio al core vía dogfooding. Sin el parámetro, comportamiento idéntico.
- `tests/test_delegate.py` (9 tests: subset, global, ejecución del
  subagente, entradas inválidas, sin configurar).

### Proceso — tercera ronda de dogfooding
- Implementado por **yunta mismo** (GLM-4.7), esta vez tocando el core
  (`agent.py`). Mitigaciones: especificación exacta + restricción dura de
  no romper los 34 tests existentes (cumplida: pasaron sin modificarse).
- El agente pasó por un borrador defectuoso de `agent.py` que se
  autocorrigió en el turno siguiente; el diff final es quirúrgico.
- Registró solo read-only tools en el subagente; wiring del CLI correcto.
- Validación end-to-end real con GLM-4.7: la raíz delegó y el subagente
  investigó usando exclusivamente glob/grep/read_file (sin bash ni
  writes), devolviendo hallazgos exactos sobre el propio repo.

### Modificado
- `yunta/agent.py`: `__init__` acepta `tools` opcional; `_definitions()`.
- `yunta/cli.py`: importa `delegate` y llama `set_provider(provider)`.

### Verificación
- `pytest` → 43 passed. 8 tools registradas en el REPL.

---

## [0.7.0] — 2026-09-06

### Agregado
- **Streaming de respuestas y reensamblado de tool calls** (`yunta/provider.py`, `yunta/agent.py`):
  - `Provider.send(..., on_text=None)`: soporte opcional de streaming en la interfaz neutral.
  - `LiteLLMProvider._consume_stream()`: procesa stream de tokens en tiempo real invocando `on_text`.
  - Reensamblado robusto de tool calls fragmentados: agrupa chunks por `index`, reconstruyendo `tool_name` y concatenando fragmentos de `tool_input` (`function.arguments`) hasta finalizar la llamada.
  - Soporte de `stream_options={"include_usage": True}` para acumulación exacta de métricas de tokens en streams.
  - Salvaguarda de `StopReason.TOOL_USE` si el proveedor emite finish_reason no específico cuando hay tool calls presentes.
- `tests/test_provider.py`: tests unitarios de streaming de texto puro y streaming de tool calls fragmentados (45 tests totales en la suite).

### Modificado
- `yunta/agent.py`:
  - Detección dinámica de soporte de streaming (`on_text` en firma del provider) manteniendo estricta compatibilidad con providers síncronos/mocks (`FakeProvider`).
  - Reseteo adecuado de `_streamed` antes de la llamada para evitar salida duplicada en consola.

### Verificación
- `pytest` → 45 passed (100% verde).
- Compilación sin errores (`py_compile` en los 14 archivos Python).
- Smoke test end-to-end con `gemini/gemini-3.6-flash` en Antigravity completando llamada a `write_file` y `read_file` con streaming en tiempo real.

---

## [0.8.0] — 2026-09-06

### Agregado
- **Soporte MCP (Model Context Protocol) sobre stdio** (`yunta/mcp.py`):
  - Cliente `MCPClient` minimalista (~100 líneas) implementado exclusivamente con la librería estándar de Python (`subprocess`, `json`), sin dependencias externas ni SDKs pesados.
  - Handshake de inicialización JSON-RPC 2.0 (`initialize` y `notifications/initialized`).
  - Auto-descubrimiento de herramientas vía `tools/list` desde configuración `.yunta/mcp.json`.
  - Integración transparente en el `registry` de Yunta con prefijo de espacio de nombres `mcp__<servidor>__<tool>`.
  - Ejecución de llamadas a herramientas (`tools/call`) canalizadas a través del bucle con los permisos de Yunta.
  - Ciclo de vida y cierre limpio de subprocesos (`close()`) al finalizar la sesión del CLI.
  - Formato estándar de configuración compatible con el ecosistema MCP (Claude Desktop / Cursor / VS Code).
- `tests/test_mcp.py`: 3 tests unitarios cubriendo handshake, auto-descubrimiento, ejecución de tools, manejo de errores JSON-RPC y degradación silenciosa sin configuración (48 tests totales en la suite).

### Modificado
- `yunta/cli.py`: integra `load_mcp_servers()` al inicio y limpieza en bloque `finally`.
- `README.md`: documentación de configuración de servidores MCP.
- `docs/PLAN.md`: ítem de Soporte MCP completado en el backlog.
- `.gitignore`: exclusión de `.yunta/`.

### Verificación
- `pytest` → 48 passed (100% verde).
- Compilación de los 15 archivos Python (`py_compile`).
- Smoke test end-to-end con servidor MCP real ejecutando `consultar_clima` y respuesta del modelo Gemini 3.6 Flash vía Yunta en Antigravity.

---

## [0.9.0] — 2026-09-06

### Agregado
- **Edición quirúrgica de archivos `str_replace`** (`yunta/tools/files.py`):
  - Tool `str_replace(path, old_str, new_str)` inspirada en el estándar de Anthropic (SWE-bench / Claude Code).
  - Validación determinista de unicidad:
    - Falla con error descriptivo si `old_str` no existe en el archivo.
    - Falla con advertencia de ambigüedad si `old_str` aparece múltiples veces, solicitando más líneas de contexto circundante.
    - Reemplazo exacto preservando indentación y codificación UTF-8 cuando hay una coincidencia única.
  - Soporte de previsualización de diffs unificados en `Agent._tool_detail` (`yunta/agent.py`) antes de la aprobación del usuario.
- `tests/test_tools.py` y `tests/test_agent.py`: 5 nuevos tests unitarios (éxito, no encontrado, ambigüedad, archivo inexistente y visualización de diff en el agente). 53 tests totales en la suite.

### Proceso — cuarta ronda de dogfooding
- Implementado por **yunta mismo** (Gemini 3.6 Flash vía Antigravity):
  - El agente inspeccionó `yunta/tools/files.py` y `yunta/agent.py`.
  - Creó la implementación completa de `str_replace` y su integración de diffs.
  - Escribió la suite de pruebas unitarias y ejecutó la verificación.

### Verificación
- `pytest` → 53 passed (100% verde).
- Compilación de los 15 archivos Python (`py_compile`).

---

## [0.10.0] – 2026-09-06

### Agregado
- **Licencia MIT formal** (`LICENSE`): Incorporación formal del archivo de licencia MIT al repositorio.
- **Interrupción limpia de turnos con KeyboardInterrupt (`Ctrl+C`)** (`yunta/agent.py`):
  - Captura controlada de `KeyboardInterrupt` en el bucle principal de ejecución de turnos `_loop()`.
  - Preservación estricta de la invariante de roles alternados de la conversación: si el turno se interrumpe después de un mensaje de usuario o tool results, se añade un mensaje con rol `ASSISTANT` y contenido `"[interrumpido por el usuario]"`.
  - Retorno limpio de la respuesta acumulada hasta el momento de la interrupción.
- **REPL interactivo resiliente** (`yunta/cli.py`):
  - Manejo de `KeyboardInterrupt` alrededor de `agent.send(prompt)` en el bucle de interacción para regresar inmediatamente al prompt `> ` sin abortar el proceso ni perder el historial previo.
  - Reconfiguración automática de `stdout` y `stderr` a UTF-8 en consolas Windows (`sys.stdout.reconfigure(encoding="utf-8", errors="replace")`) para evitar fallos por caracteres especiales en diffs o tool calls.
- **Resiliencia de conectividad y reintentos automáticos** (`yunta/provider.py`):
  - Manejo de backoff con reintentos para errores transitorios de rate limit (`429`) y congestión del servidor (`503`, `MidStreamFallbackError`).
- **Tests unitarios** (`tests/test_agent.py`):
  - Test `test_keyboard_interrupt_in_loop_preserves_assistant_message` validando la captura no destructiva, mensaje final de asistente y conservación de roles.

### Modificado
- `yunta/agent.py`: soporte de interrupción limpia y preservación de mensajes en `_loop()`.
- `yunta/cli.py`: soporte de `Ctrl+C` en el REPL y codificación UTF-8 en Windows.
- `yunta/provider.py`: reintentos automáticos ante 429 y 503.
- `docs/PLAN.md`: actualización de estado a v0.10.0.
- `docs/architecture.md` y `docs/architecture_en.md`: especificación técnica de arquitectura bilingüe (ES/EN) con diagrama Mermaid y desglose de capas.
- `README.md` y `README_en.md`: guía de usuario bilingüe completa con detalles de configuración de modelos, comandos, aprobaciones con diff unificado, memoria y MCP.

### Verificación
- 54 tests pasando al 100% en `pytest` (`tests/test_agent.py`, `tests/test_tools.py`, `tests/test_mcp.py`, `tests/test_provider.py`, etc.).
- Compilación sintáctica verificada con `py_compile`.
- Implementación realizada mediante dogfooding utilizando la herramienta `str_replace` recientemente creada.


## [0.11.0] – 2026-09-06

### Agregado
- **Prompt Caching nativo y agnóstico al LLM** (`yunta/provider.py` y `yunta/api.py`):
  - Inyección de punto de corte de caché estructurado (`cache_control: {"type": "ephemeral"}`) en el system prompt dentro de `_to_litellm()`.
  - Activación automática de Prompt Caching en Anthropic Claude (reducción de hasta 90% en costo de tokens cacheados y aceleración de latencia TTFT del 50-80%).
  - Compatibilidad transparente sin errores en OpenAI, DeepSeek, Google Gemini y proveedores locales (Ollama/vLLM), aprovechando su caching automático a nivel de prefijo.
  - Normalización de métricas de telemetría de caché en `yunta/api.py` (`Usage.cached_tokens`).
  - Extracción unificada de tokens cacheados desde LiteLLM soportando `prompt_tokens_details.cached_tokens`, `cache_read_input_tokens` y `prompt_cache_hit_tokens` tanto en respuestas síncronas como en streaming.
- **Visibilidad de ahorro en el REPL** (`yunta/cli.py`):
  - El comando `/tokens` ahora desglosa el ahorro de caché: `in=<tokens> (cached=<cached_tokens>) out=<output_tokens>`.
- **Tests unitarios** (`tests/test_provider.py`):
  - `test_system_prompt_includes_cache_control`: valida la presencia de `cache_control` en el system prompt.
  - `test_usage_accumulates_cached_tokens`: valida la acumulación en el método `Usage.add()`.
  - `test_provider_tracks_cached_tokens`: valida la extracción y suma en `provider.total_usage`.

### Modificado
- `pyproject.toml`: versión actualizada a `0.11.0`.
- `docs/PLAN.md`: actualizado estado a v0.11.0.

### Verificación
- 57 tests pasando al 100% en `pytest` (54 existentes + 3 nuevos tests unitarios).
- Compilación y verificación sintáctica con `py_compile` y `compileall`.
- Implementado de forma autónoma mediante dogfooding con Yunta.

---

## [1.0.0] — 2026-09-07

### Agregado
- **Documentación y Presentación SDD (Spec-Driven Development)**: Creación de `docs/sdd.md` y `docs/sdd_en.md`, cruzando la arquitectura del harness con el desarrollo guiado por especificaciones (los 6 pilares: contratos en `AGENTS.md`, esquemas JSON-Schema/MCP, edición quirúrgica con `str_replace`, oráculo ejecutable con `pytest`, Prompt Caching económico y anti-regresión con `learnings.md`).
- **CI (GitHub Actions)**: `.github/workflows/ci.yml` — tests en Python
  3.10-3.13 en cada push/PR. La suite no requiere credenciales (LiteLLM
  se intercepta en tests).
- **Documentación v1.0.0 unificada**: `docs/architecture.md` y `docs/architecture_en.md` actualizados con la especificación de API pública congelada, pipeline de CI y sección de Spec-Driven Development. `README.md` y `README_en.md` actualizados con guía de uso como librería Python embebible y enlace a matriz de proveedores.
- **Matriz de proveedores**: `docs/PROVEEDORES.md` +
  `scripts/prueba_proveedor.py` (prueba universal: tool call real +
  lectura + verificación). GLM-4.7 (Z.ai Coding Plan) re-verificado con
  el script universal: RESULTADO OK.
- Congelación de API: exports estables en `yunta/__init__.py` (núcleo,
  compactación, provider, FeedbackStore; `Response`/`Usage` añadidos).

### Declaración de estabilidad (1.0)
Superficie pública estable: `Agent(provider, system, compactor,
max_turns, confirm, tools)`, `Provider.send(messages, tools, on_text)`,
`LiteLLMProvider`, tipos de `api.py`, `FeedbackStore`,
`@registry.register`, estrategias de compactación. Cambios que rompan
esta interfaz requieren versión mayor (2.0).

### Roadmap de evolución
E1 CI ✅ · E2 API congelada ✅ · E3 matriz ✅ (GLM+Gemini verificados,
resto comunitario) · E4 PyPI pendiente (último, por decidir cuenta de
publicación).

### Verificación
- `pytest` → 57 passed. Prueba universal GLM-4.7 → OK.
- El push de esta versión dispara el primer run del CI.

---

---

---

## [1.1.0] — 2026-09-08

### Agregado
- **V2-5 — Modo Servidor MCP de Yunta (`yunta serve-mcp`, `yunta mcp`) (`server_mcp.py`, `cli.py`)**:
  - Implementación completa del protocolo estándar Model Context Protocol (versión `2024-11-05`) sobre `stdio` mediante JSON-RPC 2.0.
  - Exposición de todo el catálogo blindado de herramientas de Yunta (`read_file`, `write_file`, `str_replace`, `list_dir`, `bash`) con sus correspondientes esquemas JSON Schema (`inputSchema`).
  - Permite a IDEs y clientes MCP modernos (Claude Desktop, Cursor, Windsurf, Claude Code, Antigravity) conectarse a Yunta directamente vía `stdio` para ejecutar herramientas deterministas con control de presupuesto y paginación.
  - Redirección estricta de telemetría y logs a `sys.stderr` para garantizar pureza en el canal de mensajes `sys.stdout`.
  - Despacho CLI ultrarrápido desde `yunta serve-mcp` o el alias `yunta mcp` sin requerir clave de API.
  - 8 nuevas pruebas unitarias y de integración end-to-end (`MCPClient` conectándose a `yunta serve-mcp`) en `tests/test_server_mcp.py`.
  - **Cierre formal del Backlog v2 al 100%**: Suite ampliada a **99 pruebas pasando (100% PASS)**.

## [1.0.9] — 2026-09-08

### Agregado
- **V2-1 — Modo Gobernanza `yunta check` (`governance.py`, `cli.py`)**:
  - Comando CLI ligero y 100% local para auditar la salud SDD de cualquier proyecto sin costo de tokens ($0 API calls, ejecución instantánea).
  - Inspección exhaustiva de la tríada SDD (`SPEC.md`, `PLAN.md`, `AGENTS.md`), configuración `.yunta/config.json`, estado de Git y suite de tests.
  - Detección automática del protocolo de interoperabilidad en `AGENTS.md` (delegación canónica a Yunta).
  - Ejecución opcional de tests unitarios del proyecto con flag `--tests` (timeout de seguridad de 60s).
  - Salida dual: tabla visual con formato de consola o salida estructurada con flag `--json` para que IDEs externos (Claude Code, Cursor, Antigravity) o scripts de CI/CD verifiquen la gobernanza programáticamente.
  - Retorna código de salida estándar: `0` si el proyecto es saludable o `1` si faltan especificaciones críticas o fallan los tests.
- **V2-2 — Sesiones Resumibles `yunta --resume` (`session.py`, `agent.py`, `cli.py`)**:
  - Persistencia atómica de mensajes, bloques y telemetría de tokens (`Usage`) en `.yunta/session_state.json`.
  - Auto-guardado continuo tras cada turno completado y al interrumpir con `Ctrl+C`.
  - Reanudación instantánea del contexto y métricas mediante flag `yunta --resume` o `yunta -r`.
  - Limpieza automática del archivo de sesión al ejecutar `/clear` en el REPL.
- **Especificación Canónica del Harness (`docs/SPEC.md`)**:
  - Creación formal de la especificación técnica SDD para el desarrollo del propio harness Yunta (visión, frontera ontológica, requerimientos, arquitectura y criterios de calidad).
- **Tests Unitarios**:
  - `tests/test_governance.py`: 5 tests unitarios verificando directorio vacío, repositorio SDD completo, fallback a `docs/`, salida JSON y salida de consola.
  - `tests/test_session.py`: 4 tests unitarios verificando serialización de bloques/mensajes, telemetría de uso, guardado/carga/limpieza atómica y manejo de archivos corruptos.
  - Suite total de Yunta ampliada a **91 tests pasando (100% PASS)**.

## [1.0.8] — 2026-09-08

### Agregado
- **V2-4 — Herramienta Nativa `list_dir` con Presupuesto de Tokens (`files.py`)**:
  - Inspección estructurada de directorios en árbol compacto con tamaños legibles (`B`, `KB`, `MB`).
  - Filtrado automático de directorios pesados (`.git`, `node_modules`, `__pycache__`, `.venv`, `.pytest_cache`, `.gemini`, `.zcode`).
  - Control de recursión (`max_depth`, default: 2) y truncamiento inteligente de presupuesto (`max_files`, default: 80).
  - Formato de conectores ASCII universal (`|-- `, `\-- `) a prueba de terminales Windows cp1252.
- **V2-7 — Protocolo Canónico de Interoperabilidad en `AGENTS.md` (`init.py`)**:
  - Incorporación formal de la regla de interoperabilidad para IDEs externos (Claude, Cursor, Copilot) en la plantilla `generate_agents()`.
  - Establece a `yunta` CLI como el único ejecutor y oráculo oficial del repositorio, priorizándolo sobre el LLM interno del IDE y habilitando consultas de solo lectura (Q&A) sin forzar modificaciones.

---

## [1.0.7] — 2026-09-08

### Corregido & Mejorado (Auditoría Dogfooding P1-P5)
- **P1 — Prevención de `tool_use` huérfano ante `Ctrl+C` (`agent.py`)**:
  - Al interrumpir con `KeyboardInterrupt` durante la ejecución de herramientas, ahora se cierran todas las llamadas a herramientas pendientes agregando bloques `TOOL_RESULT` con estado cancelado, evitando que el proveedor lance `400 Bad Request` en el siguiente turno.
- **P2 — Resiliencia ante rechazo de `stream_options` (`provider.py`)**:
  - Detección automática de errores en endpoints OpenAI-compatibles estrictos (vLLM, LocalAI) que no soportan `stream_options`, reintentando de inmediato sin el kwarg.
- **P3 — Inicialización segura de `mcp_clients` (`cli.py`)**:
  - `mcp_clients` inicializado como lista vacía al inicio de `main()` previniendo `UnboundLocalError` en bloques `finally`.
- **P4 — Compactador `SlidingWindow` activo en CLI (`cli.py`)**:
  - Integración nativa del compactador por ventana deslizante en el REPL y modo single-shot (configurable vía `YUNTA_MAX_MESSAGES`, default: 40).
- **P5 & V2-3 — Cap de tamaño y seguridad UTF-8 en `read_file` (`files.py`)**:
  - Límite por defecto a 2000 líneas con mensaje de truncamiento y soporte opcional para `offset` y `limit`. Lectura y escritura con `errors="replace"` protegiendo contra errores de codificación en Windows (cp1252).
- **Documentación**:
  - `README.md` y `README_en.md` actualizados con todos los comandos interactivos (`/init`, `/undo`, `/roi`, `/metrics`, `/tokens`, `/help`).

---

## [1.0.6] — 2026-09-07

### Agregado
- **E9 — Cascada de Respaldo de Modelos (`ModelFallbackRouter`)**:
  - Soporte para variable de entorno `LLM_MODELS` con lista separada por comas de proveedores/modelos prioritarios.
  - Conmutación en caliente automática ante errores transitorios de API, saturación o cuotas agotadas (`429`, `503`, `RESOURCE_EXHAUSTED`, `ratelimit`, `quota`) sin abortar la sesión ni perder el contexto del turno.
- **E11 — Streaming de Pensamiento y Pre-Notificación de Herramientas**:
  - Soporte de streaming para tokens de razonamiento (`reasoning_content` / `thought`) en modelos de razonamiento (ej. DeepSeek-R1, Claude 3.7 Thinking).
  - Pre-notificación en terminal (`[tool] {name} en ejecución...`) previo a la invocación de herramientas para retroalimentación visual inmediata.
- **E13 — Micro-Checkpoints y Time-Travel en Memoria (`/undo`)**:
  - Captura instantánea de snapshots en memoria de archivos afectados antes de cualquier ejecución destructiva o de reemplazo (`write_file`, `str_replace`).
  - Comando interactivo `/undo` en el REPL de `yunta` para revertir al estado inmediatamente anterior y eliminar archivos creados accidentalmente.
- **E14 — Dashboard de Retorno de Inversión y Eficiencia Económica (`/roi`)**:
  - Comando `/roi` que despliega métricas visuales consolidadas: porcentaje de acierto de caché, tokens cacheados, tokens evitados frente a chats crudos y estimación de ahorro monetario en USD.
- **Suite de Pruebas Automatizadas**:
  - Pruebas unitarias para conmutación por fallback ante 429, streaming de razonamiento, checkpoints y restauración vía `/undo`, y cálculo de métricas ROI (total: 75 tests 100% pasando).

---

## [1.0.5] — 2026-09-07

### Agregado
- **Compactación semántica de salidas de terminal (E12)** (`yunta/tools/bash.py`):
  - Función `_compact_output` que previene la inflación innecesaria de contexto en turnos largos:
    - En ejecuciones exitosas de `pytest`, retiene únicamente los encabezados y la línea de resumen final (ej. `=== 70 passed in ... ===`), eliminando decenas de líneas redundantes y ahorrando hasta un 95% de tokens de contexto.
    - En comandos largos exitosos (> 30 líneas), preserva el inicio y final del log intercalando un resumen explícito de líneas omitidas.
    - En comandos con fallo, preserva las partes iniciales y el bloque de traceback/error final para diagnóstico preciso.
  - Aumento de timeout de comandos bash de 30s a 60s en `yunta/tools/bash.py` para prevenir falsos timeouts en entornos con alta carga de CPU en Windows.
- **Directiva de eficiencia de pruebas en el System Prompt** (`yunta/cli.py`):
  - Regla explícita para que el agente ejecute pruebas focalizadas (`pytest tests/test_modulo.py`) durante la iteración activa, reservando la suite completa para la certificación final.
- **Tests unitarios** (`tests/test_tools.py`):
  - Nuevo test `test_bash_compact_output` verificando la compresión de pytest y comandos extensos. Suite total: 70 tests al 100% verde.

---

## [1.0.4] — 2026-09-07

### Agregado
- **Comando de Ideación y Scaffolding SDD (`yunta init` / `/init`)** (`yunta/init.py`, `yunta/cli.py`):
  - Nuevo módulo `yunta/init.py` para inicializar cualquier idea desde cero guiada por Spec-Driven Development (SDD).
  - Generación automática de los 3 artefactos maestros fundacionales en el directorio destino:
    - `SPEC.md`: Especificación formal de la idea (visión, problema, actores, casos de uso del MVP, arquitectura, flujos de datos y anti-alcance).
    - `PLAN.md`: Hoja de ruta iterativa estructurada por fases verificables (Fase 1: Mínimo Núcleo Viable con criterio de aceptación TDD).
    - `AGENTS.md`: Manual de convivencia y guardrails para cualquier agente de IA (stack, comandos de ejecución/tests y reglas inviolables).
  - Integración en CLI: `yunta init [nombre_o_idea]` para ejecutar la inicialización de forma directa y offline sin requerir credenciales ni modelos configurados.
  - Integración en REPL: comando interactivo `/init [idea]` para inicializar proyectos desde la sesión de terminal activa.
  - Ejecución de comando único (single-shot): `yunta "instrucción"` para despachar tareas directas sin entrar al REPL interactivo.
- **Tests unitarios** (`tests/test_init.py`):
  - Cobertura completa de generación de artefactos, respeto a archivos existentes, asignación de nombre por defecto y despacho CLI (`main()`). 4 nuevos tests (69 tests en total al 100% verde).

---

## [1.0.3] — 2026-09-07

### Agregado
- **Indicador de actividad y estado en tiempo real (Spinner / Activity Status)** (`yunta/agent.py`):
  - Clase auxiliar `Spinner` ultra-liviana implementada únicamente con la biblioteca estándar (`threading`, `time`, `sys`).
  - Animación con caracteres Unicode (`⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏`) y contador de tiempo transcurrido en segundos.
  - Salvaguarda `sys.stdout.isatty()` para ejecutarse exclusivamente en terminales interactivas sin alterar entornos no interactivos ni ejecuciones de pruebas.
  - Integración en `_loop()` y `_stream_text()`: inicio antes de `self.provider.send()` con el mensaje `'Pensando...'` y detención limpia al recibir el primer delta de texto o al finalizar la llamada.
  - Telemetría de duración de herramientas en `_execute_tool()`: medición con `time.time()` e impresión del tiempo transcurrido (`[tool] {name} completado en {elapsed:.2f}s` o `falló en ...` si ocurre una excepción).
- **Tests unitarios** (`tests/test_agent.py`):
  - `test_spinner_start_and_stop`: valida que `Spinner` arranca y se detiene de forma limpia, liberando el hilo sin dejar colgadas ejecuciones ni lanzar excepciones.

### Verificación
- `pytest` → 65 passed (100% verde).
- Compilación de todos los archivos Python verificada.

---

## [1.0.2] — 2026-09-07

### Agregado
- **Lanzamiento Oficial en PyPI**: Publicación del paquete en el registro global de Python como [`yunta-harness`](https://pypi.org/project/yunta-harness/) (instalable con `pip install yunta-harness`).
- **Empaquetado y Publicación en PyPI (E4)**: Metadatos completos en `pyproject.toml` bajo el nombre `yunta-harness` (con comando CLI `yunta`), pipeline de publicación automatizada en `.github/workflows/publish.yml` y guías bilingües de release en `docs/pypi_release.md` y `docs/pypi_release_en.md`.
- **Gobernanza del Backlog (Regla Inviolable 6 en AGENTS.md)**: Formalizada la regla de soberanía de especificaciones: los archivos de planificación y backlog (`docs/PLAN.md`) son estrictamente de solo lectura durante tareas de desarrollo; el agente nunca debe auto-modificar el backlog ni alterar requerimientos sin instrucción humana explícita.
- **Modularización y jerarquía de System Prompt (E7)** (`yunta/cli.py`):
  - Jerarquía de resolución para el system prompt base:
    1. Variable de entorno `YUNTA_SYSTEM_PROMPT` si está definida.
    2. Archivo de usuario `~/.yunta/system_prompt.md` si existe.
    3. `SYSTEM_PROMPT` por defecto (fallback inmutable con frontera ontológica y reglas de honestidad).
  - Concatena `AGENTS.md` si existe en el workspace del proyecto y el preámbulo de lecciones de `FeedbackStore`.
- **Tests unitarios** (`tests/test_agent.py`):
  - `test_load_system_prompt_custom_override`: valida la sobreescritura vía variable de entorno `YUNTA_SYSTEM_PROMPT` y fallback a `~/.yunta/system_prompt.md`.

### Verificación
- `pytest` → 64 passed (100% verde).
- Compilación `compileall` sin errores.

---

## [1.0.1] — 2026-09-07

### Agregado
- **Métricas livianas de eficiencia de recursos**: Telemetría 100% en memoria en `yunta/api.py` (`Usage`), cálculo de Cache Hit Rate, cálculo de tokens brutos transferidos frente a chat crudo sin harness, desglose por tipo de herramienta y errores en `yunta/agent.py`, comandos `/tokens` y `/metrics` enriquecidos en `yunta/cli.py`, y 5 tests unitarios en `tests/test_metrics.py`. Cero llamadas adicionales a APIs, cero latencia y cero dependencias.
- **Guardrail ontológico y flujo de 5 fases**:
  - `yunta/cli.py`: refuerzo de `SYSTEM_PROMPT` con frontera explícita entre el harness de desarrollo y el runtime de producción (evita que el modelo cree daemons o servicios locales para Yunta).
  - `tests/test_agent.py`: test unitario de regresión `test_system_prompt_ontological_boundary()`.
  - `docs/quickstart.md` y `docs/quickstart_en.md`: adición del **Paso 0** con la tabla *Lo que ES vs Lo que NO ES Yunta*, la *Regla de Oro*, metodología de 5 fases y plantilla `AGENTS.md` para proyectos de clientes.
- **Harness para SDD en portadas**: Actualización del título principal y adición de sección destacada en `README.md` y `README_en.md` posicionando formalmente a Yunta como el Harness de Agente de Código para Spec-Driven Development (SDD), vinculándolo con la arquitectura y guías de `docs/sdd.md`.
- **Guía paso a paso bilingüe**: Creación de `docs/quickstart.md` y `docs/quickstart_en.md`, tutorial detallado desde la instalación y configuración de modelos (Gemini, Claude, GPT-4o, Ollama, DeepSeek) hasta la verificación con `scripts/prueba_proveedor.py`, flujo de turnos interactivo, aprobaciones con diff unificado, comandos del REPL (`/tokens`, `Ctrl+C`, `/clear`, `/exit`) y uso avanzado con `AGENTS.md` y MCP.

### Corregido
- **CI fallaba en Python 3.10**: bug upstream en litellm 1.100.0 —
  `llms/anthropic/experimental_pass_through/context_management/editors/compact.py`
  importa `typing.NotRequired`, inexistente en 3.10, pese a que litellm
  declara `requires-python >=3.10`.

### Modificado
- Piso de Python subido a **3.11**: `pyproject.toml` (`requires-python`),
  matriz del CI (3.11/3.12/3.13) y README/AGENTS.
- Nota: si litellm corrige el bug upstream, se puede restaurar 3.10.

### Verificación
- El push de esta versión dispara el CI; verde en 3.11-3.13 confirma.

---

## [2.2.0] — 2026-09-12

### Agregado
- **P9 — descomposición de specs grandes** (`yunta/decompose.py`):
  - `decompose_task(provider, spec)`: pide al modelo subtareas JSON
    [{goal, files(≤2), verify}], validación dura (sin solape de archivos,
    máximo 2 por lote), una regeneración ante plan inválido.
  - `run_chunks()`: ejecución SECUENCIAL por lotes con subagente de
    contexto limpio (solo su subtarea + sus archivos), max_turns 15;
    ante cuota/fallo persiste el lote exacto pendiente en
    `.yunta/estado-de-tarea.md` (integración con P7) y acepta
    `start_from` para reanudar.
  - Flag CLI `--chunks` (y env `YUNTA_CHUNKS`) en single-shot.
  - `tests/test_decompose.py`: 10 tests (parser, validación, regeneración,
    secuencia con contexto limpio, muerte de lote con persistencia,
    reanudación desde lote N).

### Cerrado
- Último bug estructural del dogfooding: las sesiones multi-archivo ya no
  mueren por acumulación de contexto (evidencia: v0.7 streaming, O1-c,
  ronda W). E2E real: spec de 4 archivos → 2 lotes → completada con
  verificación pytest en cada lote.
