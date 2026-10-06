# Validación y calidad de los datos

Un pipeline maduro no promete "0 % de inconsistencias": detecta, rechaza y deja trazado cada registro que no cumple
una regla. Aquí se mide la tasa de registros válidos y la tasa de rechazo de cada carga, y cada rechazo queda en
`ctl.rechazos` con su regla, su motivo y el registro original.

Cifras de la última ejecución completa (6-oct-2026).

## 1. Reglas de validación (bronze → silver)

Implementadas en `src/quality/validate.py` y `src/transform/silver/homologacion.py`. Los rangos se leen de
`silver.dim_indicador` y las tolerancias de `config.yaml` (sección `calidad`).

| Regla (`ctl.rechazos.regla`) | Qué verifica | Ejemplo |
|---|---|---|
| `nulo` | Valor vacío (`''`, `'-'`, `nan`) donde el territorio ya existía | EAPS de Sejong en 2012 |
| `tipo_invalido` | Valor no numérico | texto en una celda de valor |
| `etiqueta_no_mapeada` | Territorio, sexo o edad sin código en `etiquetas.csv` (incluidas las etiquetas coreanas) | una región nueva sin homologar |
| `territorio_excluido` | Territorio que se descarta a propósito, con motivo | "Jeonnam-Gwangju": región combinada (Gwangju + Jeollanam-do) que KOSIS publica solo en 2025; duplicaría valores |
| `indicador_invalido` | Indicador fuera de `dim_indicador` | |
| `rango` | Valor fuera del rango del indicador | TFR fuera de 0–10; tasas fuera de 0–100; esperanza de vida fuera de 0–120 |
| `clave_duplicada` | Dos filas con la misma clave natural | |
| `coherencia_totales` | Suma de grupos de edad ≈ total y H + M ≈ T (población y EAPS), tolerancia 0,5 % más el margen de redondeo de la fuente (la EAPS publica en miles) | |

Lo que **no** es rechazo: un valor vacío de un territorio que aún no existía (Sejong antes de 2012) se cuenta como
"no aplica"; los agregados de edad que se solapan en KOSIS (15-24, 15-29…) se descartan porque se recalculan en el
pipeline; las variantes de proyección de KOSTAT que no se usan, también. Todo eso queda en el embudo, no en
`ctl.rechazos`.

Además, la base garantiza por sí misma la clave primaria, las claves foráneas a las dimensiones y los `CHECK` de
dominio (`estado`, `escenario`, `nivel`, `capa`).

## 2. Resultado de la última carga

| Carga | Filas | Válidas | Rechazadas | Tasa de rechazo |
|---|---|---|---|---|
| `silver.fact_historico` | 46.112 | 45.868 | 244 | 0,53 % |
| `silver.fact_proyeccion` | 57.600 | 57.600 | 0 | 0 % |
| `silver.conciliacion` | 1.054 | 1.054 | 0 | 0 % |

| Regla | Tabla de origen | Rechazos | Motivo |
|---|---|---|---|
| `territorio_excluido` | `bronze.kosis` | 208 | "Jeonnam-Gwangju" (solo 2025, se solapa con Jeollanam-do y Gwangju) |
| `nulo` | `bronze.kosis` | 28 | celdas `-`: EAPS de Sejong 2012-2016 (25; la EAPS lo publica desde 2017) y esperanza de vida 2025 (3, aún sin publicar) |
| `nulo` | `bronze.worldbank_wdi` | 8 | TFR 2025 aún sin publicar en el WB (7 países de comparación y el promedio OCDE) |

El 100 % de los rechazos tiene regla y motivo. Por dataset (`gold.v_calidad_dataset`), los rechazos se concentran en
`eaps_sido` (155: Sejong 2012-2016 y Jeonnam-Gwangju), `vitales_sido` (78, Jeonnam-Gwangju), `SP.DYN.TFRT.IN` (8) y
`vitales_nacional` (3); los otros 13 datasets tienen 100 % de registros válidos.

### Embudo bronze → silver

Filas después de cada paso (`ctl.pasos_silver`, vista `gold.v_embudo_silver`). Los filtros solo pueden quitar
filas; si alguno agregara, el pipeline se detiene.

| # | Paso | Tipo | Filas | Variación |
|---|---|---|---|---|
| 1 | Formato largo | filtro | 164.080 | — |
| 2 | En alcance (indicadores, años y territorios del proyecto) | filtro | 89.032 | −75.048 |
| 3 | Homologados | filtro | 88.824 | −208 |
| 4 | Con dato (sin imputar) | filtro | 87.888 | −936 |
| 5 | Válidos (85+ agrupado y reglas) | filtro | 77.115 | −10.773 |
| 6 | + agregados de edad | cálculo | 87.888 | +10.773 |
| 7 | Coherencia de totales | filtro | 87.888 | 0 |
| 8 | + Chungnam + Sejong | cálculo | 91.594 | +3.706 |
| 9 | + indicadores derivados | cálculo | 103.468 | +11.874 |

El paso 2 descarta lo que está fuera del alcance: los agregados de edad que se solapan en KOSIS (se recalculan en
el paso 6) y las variantes de proyección de KOSTAT que no se usan. Todo sigue en bronze por si se necesita después.

## 3. KPIs de calidad

Calculados en cada ejecución (`src/quality/kpis.py` → `ctl.kpis`, vista `gold.v_kpis_calidad`). Los 13 se cumplen.

| KPI | Meta | Resultado |
|---|---|---|
| Fuentes institucionales integradas | ≥ 3 | 4 (KOSIS, OECD, WB, UN WPP) |
| Indicadores con definición en el diccionario | 100 % | 100 % (16 de 16) |
| Contrastes del diccionario presentes en la conciliación | 100 % | 100 % |
| Ejecuciones sin fallo técnico | ≥ 95 % | 100 % (201 de 201 cargas) |
| Registros válidos por carga | ≥ 98 % | 99,47 % en la peor carga |
| Tasa de rechazo por carga | ≤ 2 % | 0,53 % en la peor carga |
| Rechazos trazados con regla y motivo | 100 % | 100 % |
| Completitud año × indicador, nacional | ≥ 95 % | 100 % (11 indicadores × 26 años) |
| Completitud año × indicador, regional | ≥ 90 % | 99,53 % (17 si-do, desde que cada uno existe) |
| Suma de los 17 si-do vs nacional (±0,5 %) | 100 % | 100 % (130 de 130 año × indicador) |
| Duplicados en bronze | se monitorean | 0 dentro de una misma carga |
| Proyecciones con edición y escenario | 100 % | 100 % (57.600 registros) |
| Pares maestra-contraste dentro de ±3 % (histórico) | ≥ 90 % | 99,8 % (489 de 490) |

## 4. Conciliación maestra vs contraste

| Indicador | Contraste | Pares | Diferencia media | Diferencia máxima | Dentro de ±3 % |
|---|---|---|---|---|---|
| Nacimientos | OECD | 25 | 0,00 % | 0,00 % | 25 |
| Nacimientos | WB (tasa bruta × población) | 25 | 0,92 % | 2,06 % | 25 |
| TFR | OECD y WB | 25 + 25 | 0,00 % | 0,00 % | 50 |
| Población (total y grandes grupos) | WB | 104 | 0,46 % | 2,77 % | 104 |
| Población (total y grandes grupos) | UN WPP | 104 | 0,64 % | 2,34 % | 104 |
| Población activa y ocupados | OECD | 26 + 26 | 0,00 % | 0,00 % | 52 |
| Tasa de desempleo | OECD | 26 | 0,67 % | 1,82 % | 26 |
| Tasa de participación | WB (modelada OIT) | 26 | 0,71 % | 1,44 % | 26 |
| Proporción 65+ | WB | 26 | 0,98 % | 2,77 % | 26 |
| Índice de envejecimiento | WB | 26 | 0,98 % | 1,80 % | 26 |
| Dependencia de vejez | WB | 26 | 1,20 % | 3,53 % | 25 |

El único par fuera de tolerancia (dependencia de vejez, 3,53 %) se explica porque el WB usa la población de UN WPP
como denominador. En proyección, la diferencia con UN WPP (media 8,2 %; hasta 44 % en el grupo 0-14 de los escenarios de fecundidad)
no es un error: son supuestos distintos de fecundidad y migración. Se guarda como contraste y no entra en el KPI.

## 5. Pruebas automatizadas

`python -m pytest tests` ejecuta 35 pruebas sin red ni base de datos:

- **Extracción:** hash independiente del orden de claves, crudo que nunca se sobrescribe, metadata determinista,
  lectura de KOSIS con encabezado doble, elección de la descarga más reciente, rechazo de una tabla equivocada.
- **Homologación y validación:** normalización de edades, etiquetas en coreano, nulo vs "no aplica", rango,
  indicador y duplicados, coherencia de totales con tolerancia al redondeo de la EAPS.
- **Cálculos:** derivados y agregados de edad, Chungnam + Sejong (suma niveles y recalcula tasas), factor de
  cobertura, escenarios A/B/C/D, asociaciones, índice de riesgo y su sensibilidad (percentiles y z-score), embudo y
  calidad por dataset.

## 6. Limitaciones conocidas

- La EAPS regional es una encuesta por muestreo: las diferencias pequeñas entre si-do no son significativas.
- La población 2023–2025 de KOSIS se marca `preliminar`: KOSTAT la publica a partir de su proyección base.
- La esperanza de vida de 2025 aún no está publicada (la serie llega a 2024).
- El índice de riesgo y los escenarios dependen de decisiones metodológicas; por eso se publican con su
  sensibilidad (`gold.riesgo_sensibilidad`, `gold.escenarios_sensibilidad`).
