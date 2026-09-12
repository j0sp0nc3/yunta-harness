# Lecciones del dogfooding — análisis empírico

Recompilación de las ~10 rondas de dogfooding (yunta mejorándose a sí mismo
vía GLM-4.7 en ZCode y Gemini 3.6 Flash en Antigravity, con revisión humana).
Propósito: alinear las mejoras futuras con el propósito de yunta — un harness
minimalista, agnóstico al proveedor y capaz de mejorar su propio trabajo.

## 1. Inventario de rondas

| # | Ronda | Modelo/vía | Resultado | Costo aprox. |
|---|-------|-----------|-----------|--------------|
| 1 | Prueba GLM (write/read) | GLM · driver | ✅ | ~3k |
| 2 | Demo calculadora | GLM · driver | 🟡 alucinación total con prompt mínimo; éxito con prompt completo | ~5k |
| 3 | grep/glob (v0.4) | GLM · driver | ✅ + hueco de integración (cli import) cazado por humano | ~25k |
| 4 | memoria (v0.5) | GLM · driver | ✅ + auto-aplicó lección del import; version-bump fuera de alcance | ~20k |
| 5 | subagente (v0.6) | GLM · driver | ✅ primer cambio al core; autocorrigió borrador corrupto | ~30k |
| 6 | streaming (v0.7) | GLM · driver | ❌ murió (archivo corrupto) → Gemini/Antigravity completó | ~250k |
| 7 | MCP/str_replace/robustez/caching (v0.8-0.11) | Gemini · Antigravity | ✅ | n/d |
| 8 | Auditoría del repo | GLM · raíz+subagente | ✅ excelente; auto-verificó hallazgos; lección persistida | ~252k |
| 9 | ide-init / blocklist (O1-a/b) | GLM · CLI -y | ✅ / ✅ con test truncado completado por humano | ~210k+268k |
| 10 | permisos (O1-c) | GLM · CLI | ❌ murió por cuota tras escribir solo tests; humano implementó | ~223k |
| 11 | W3 PowerShell | GLM · CLI -y | ✅ particionó tests por su cuenta; detectó test flaky | ~n/d |
| 12 | W1/W4/W5 | GLM · CLI | ❌ murió analizando; humano completó | ~n/d |
| 13 | P9 E2E (spec 4 archivos) | GLM · CLI --chunks | ✅ 2 lotes limpios con pytest por lote | ~n/d |
| 14 | E1-E14, v2.x | Gemini · Antigravity | ✅ (AST, delegate_batch, visión, extensión VS Code) | n/d |

Total: 105 commits, 16 con "dogfooding" explícito, 9 menciones en CHANGELOG.

## 2. Taxonomía de fallos → qué ya se curó

| Fallo | Frecuencia | Fix aplicado |
|---|---|---|
| Escrituras truncadas a mitad | 3 | P6 write_file atómico |
| Muerte por cuota sin persistir | 2 | P7 estado-de-tarea + P8 presupuesto visible |
| Sesiones multi-archivo desbocadas | 3 | P9 --chunks |
| Alucinación (narrar sin ejecutar) | 1 | Guardas de honestidad + auto-feedback |
| Integración invisible (tool sin registrar) | 1 | Lección aprendida por el modelo (v0.5 la aplicó solo) |

## 3. Qué funciona (proteger estas propiedades)

1. **Spec ejecutable en PLAN antes de la sesión** — las rondas con spec
   detallada (oleada 1) tuvieron ~100% de éxito; las improvisadas murieron.
2. **Revisión humana del diff** — cazó: test truncado, decorador mal
   aplicado, scaffolding de tests roto, hueco de integración. Ninguna
   ronda se fusionó sin ella.
3. **CLI single-shot con -y** — más estable que los drivers Python.
4. **Hook de gobernanza en commit** — bug del sandbox solo surfaced por él.
5. **Verificación en el propio bucle** — "corre pytest antes de declarar"
   funciona; el agente particionó tests ante timeouts sin que se lo pidieran.

## 4. Mejoras propuestas (alineadas al propósito: minimal, agnóstico, auto-mejorable)

### M-A. Cerrar el ciclo de auto-feedback en single-shot 🔴
El feedback solo se ejecuta en `/exit` del REPL; las sesiones CLI single-shot
(y todo el dogfooding) NO generan lecciones. El ciclo de auto-mejora está
abierto justo donde más se usa. Fix: `feedback.summarize()` al completar el
single-shot. Esfuerzo: bajo. *Verificar: tras `yunta "tarea" -y`, learnings.md crece.*

### M-B. Auto-disparo de --chunks 🔴
P9 existe pero requiere flag manual. El harness debería detectar solo la
condición de fallo (spec que menciona >2 archivos, o SessionBudget ≥70%) y
proponer descomposición. Esfuerzo: bajo-medio.

### M-C. Auto-revisión del diff antes de declarar terminado 🟡
El humano cazó todos los defectos de integración. Un paso de self-review
("relee tu diff contra la spec y lista discrepancias") filtraría la mayoría
antes de la revisión humana. Esfuerzo: bajo (es prompt + un turno extra).

### M-D. Ledger de dogfooding automático 🟡
Este documento se compiló a mano. `.yunta/rounds.jsonl` (fecha, tarea,
tokens, archivos, truncaciones, fixes humanos) alimentaría mejoras basadas
en datos, no memoria. Esfuerzo: bajo.

### M-E. Detección de tests flaky por contaminación 🟢
`test_delegate` falla por orden de ejecución (detectado 2 veces, sin fix).
`yunta check --tests` podría correr la suite con orden invertido 1 de cada
N veces para surfacear contaminación. Esfuerzo: medio.

### M-F. Presupuesto por tarea en dogfooding 🟢
Las rondas quemaron 200-270k tokens sin techo. Con SessionBudget ya existe
la pieza: cablear un default por tarea (~80k) que cancele con estado
persistido en vez de agotar la cuota del plan. Esfuerzo: bajo.

## 5. Principio rector extraído

> El harness no debe asumir que la sesión sobrevivirá: cada acción debe ser
> verificable, cada artefacto atómico, cada muerte reversible, y cada lección
> persistida — ANTES de que haga falta.

Es la materialización del principio OpenDev que adoptamos: degradación
progresiva. Aplicarlo también a los ciclos de mejora (M-A a M-F) mantiene a
yunta alineado con su propósito sin engordar el core.
