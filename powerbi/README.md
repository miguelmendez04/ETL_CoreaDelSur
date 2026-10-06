# Dashboards en Power BI

`ETL_Corea.pbip` es un proyecto de Power BI guardado como texto (se puede versionar en git):

- `ETL_Corea.SemanticModel/`: el modelo. Contiene la conexión a PostgreSQL, 14 tablas leídas de las vistas y tablas
  `gold`, las relaciones con `Territorio` y las medidas DAX.
- `ETL_Corea.Report/`: el reporte en formato PBIR (una carpeta por página y un `visual.json` por visual), con
  6 páginas (una por bloque de preguntas de negocio) y una página "Presentación" con los gráficos de las
  diapositivas. El tema UAO ya viene aplicado (`StaticResources/`).
- `tema_uao.json`: el mismo tema por separado (rojo UAO, Segoe UI), para reutilizarlo en otro reporte.

Los datos importados se guardan en `.pbi/cache.abf`, que no se versiona. Para entregar el dashboard a alguien que no
tiene la base, se usa **Archivo > Exportar > Power BI (.pbix)**: el `.pbix` lleva los datos dentro.

## Abrir y cargar los datos

1. Correr el pipeline (`python main.py`) con PostgreSQL arriba (`docker compose up -d`).
2. Abrir `powerbi/ETL_Corea.pbip` con Power BI Desktop.
3. **Inicio > Actualizar**. La primera vez pide credenciales:
   - tipo **Base de datos**;
   - usuario y contraseña: `PG_USER` y `PG_PASSWORD` del `.env`;
   - si avisa que la conexión no está cifrada, aceptar: es la base local de Docker.
4. Si la base está en otro servidor o puerto: **Transformar datos > Editar parámetros**, cambiar `Servidor` y
   `BaseDatos`.

Cada vez que se vuelva a correr el pipeline basta con **Actualizar**.

El tema UAO viene aplicado. Para usarlo en otro reporte: **Ver > Temas > Buscar temas** y elegir `powerbi/tema_uao.json`.

## Modelo

| Tabla | Origen | Uso |
|---|---|---|
| Territorio | `gold.v_territorios` | Filtro común: nacional, 17 si-do, Chungnam+Sejong, países, promedio OCDE |
| Panel | `gold.v_panel_indicadores` | Un registro por año × territorio con todos los indicadores (histórico + proyección media) |
| Natalidad | `gold.v_natalidad_vs_15_64` | Nacimientos vs quienes llegan a 15-19 |
| Riesgo, RiesgoSensibilidad | `gold.indicadores_riesgo`, `gold.riesgo_sensibilidad` | Índice por si-do y ranking con otros pesos |
| Escenarios, EscenariosDetalle, EscenariosSensibilidad, Supuestos | `gold.v_escenarios_resumen` y tablas de escenarios | Fuerza laboral potencial A/B/C |
| Hitos, Senales | `gold.hitos_escasez`, `gold.v_senales_escasez` | Señales tempranas de escasez |
| Asociaciones | `gold.asociaciones` | Correlaciones (asociación, no causalidad) |
| KPIs, Conciliacion | `gold.v_kpis_calidad`, `gold.v_conciliacion` | Calidad del dato |
| Embudo | `gold.v_embudo_silver` | Filas después de cada paso de bronze -> silver (`ctl.pasos_silver`) |
| Anio | `gold.v_anios` | Eje común de años: une en un mismo gráfico el histórico (Panel) y el futuro (Escenarios) |

Relaciones: `Territorio[cod_territorio]` filtra `Panel`, `Riesgo`, `RiesgoSensibilidad` y `Senales`;
`Anio[anio]` filtra `Panel` y `Escenarios`.

Medidas: las de las tarjetas son siempre de Corea (nacional) y no cambian con el filtro de territorio.
- **Natalidad y población:** `TFR 2025`, `Nacimientos 2000`, `Nacimientos 2025`, `Variación nacimientos 2000-2025`,
  `Proporción 65+ 2025`, `Dependencia de vejez 2025`.
- **Mercado laboral y escenarios:** `Población activa 2025`, `Fuerza laboral potencial`, `Población 15-64 KOSTAT`,
  `Cambio vs población activa 2025`.
- **Riesgo:** `Índice de riesgo`.
- **Calidad:** `KPIs cumplidos (texto)` y `Pares dentro de ±3 %`.

## Páginas: qué va en cada una

Convenciones:
- un solo eje por gráfico;
- títulos que digan la conclusión;
- los escenarios A/B/C se rotulan como **escenarios, no pronósticos**.

### 1. Natalidad (preguntas 1 y 2)
Filtro de página: `Territorio[tipo]` = nacional.

| Visual | Campos |
|---|---|
| 3 tarjetas | `TFR 2025`, `Nacimientos 2025`, `Variación nacimientos 2000-2025` |
| Líneas: TFR 2000-2025 | Eje X `Panel[anio]`; Y `Panel[tfr]`; filtro `Panel[nivel]` = historico |
| Columnas: nacimientos por año | Eje X `Panel[anio]`; Y `Panel[nacimientos]`; filtro `Panel[nivel]` = historico |
| Líneas: cohortes | Eje X `Natalidad[anio]`; Y `Natalidad[nacidos_hace_15]` y `Natalidad[pob_15_19]` |

### 2. Envejecimiento y regiones (preguntas 3 y 5)

| Visual | Campos |
|---|---|
| Segmentador | `Territorio[territorio]`, filtrado a `tipo` nacional y sido (selección única, por defecto Corea) |
| Líneas: envejecimiento 2000-2072 | Eje X `Panel[anio]`; Y `Panel[prop_65mas]`; leyenda `Panel[nivel]` |
| Líneas: dependencia de vejez | Igual, con `Panel[dependencia_vejez]` |
| Barras: riesgo por si-do | Eje Y `Territorio[territorio]`; X `Índice de riesgo`; ordenar de mayor a menor. Este visual no lo filtra el segmentador: Formato > Editar interacciones |
| Matriz: robustez del ranking | Filas `Territorio[territorio]`; columnas `RiesgoSensibilidad[esquema]`; valores `RiesgoSensibilidad[ranking]` (mínimo) |

### 3. Mercado laboral (preguntas 4 y 7)
Filtro de página: `Territorio[tipo]` = nacional y `Panel[nivel]` = historico.

| Visual | Campos |
|---|---|
| Tarjeta | `Población activa 2025` |
| Líneas: población activa y ocupados | Eje X `Panel[anio]`; Y `Panel[pob_activa]`, `Panel[ocupados]` |
| Líneas: participación | Eje X `Panel[anio]`; Y `Panel[tasa_participacion]` (y en otro visual `Panel[tasa_desempleo]`: no mezclar en un eje) |
| Tabla: asociaciones | `Asociaciones[variable_x]`, `[variable_y]`, `[corr_niveles]`, `[corr_variaciones]`. Nota en el título: "asociación, no causalidad" |

### 4. Futuro de la fuerza laboral (preguntas 6a, 6b y 8)

| Visual | Campos |
|---|---|
| Segmentador | `Escenarios[escenario_kostat]` (selección única, por defecto medio) |
| Líneas: fuerza laboral potencial | Eje X `Escenarios[anio]`; Y `Fuerza laboral potencial`; leyenda `Escenarios[supuesto]` |
| Líneas: población 15-64 KOSTAT | Eje X `Escenarios[anio]`; Y `Población 15-64 KOSTAT` (pregunta 6a) |
| Tarjeta: cambio a 2072 | `Cambio vs población activa 2025`, con filtro `Escenarios[anio]` = 2072 y `id_supuesto` = A |
| Tabla: hitos | `Hitos[descripcion]`, `[id_supuesto]`, `[anio]`, `[valor]`; filtro `Hitos[escenario_kostat]` = medio |
| Líneas: relevo generacional | Eje X `Senales[anio]`; Y `Senales[relevo_generacional]`; filtro `Territorio[tipo]` = nacional |

### 5. Comparación OCDE (pregunta 9)
Filtro de página: `Territorio[tipo]` = nacional, pais, agregado_int y `Panel[anio]` = 2024 (último año con TFR de
todos los países).

| Visual | Campos |
|---|---|
| Barras | Eje Y `Territorio[territorio]`; X `Panel[tfr]` |
| Barras | Igual con `Panel[prop_65mas]` |
| Barras | Igual con `Panel[tasa_participacion]` |
| Barras | Igual con `Panel[pib_hora]` |

Resaltar a Corea con un color distinto: Formato > Barras > Colores > por elemento.

### 6. Calidad del dato (KPIs)

| Visual | Campos |
|---|---|
| Tarjetas | `KPIs cumplidos (texto)`, `Pares dentro de ±3 %` |
| Tabla: KPIs | `KPIs[kpi]`, `[valor]`, `[meta]`, `[cumple]`, `[detalle]`. Formato condicional en `cumple` (icono) |
| Tabla: conciliación | `Conciliacion[indicador]`, `[fuente_contraste]`, `[anio]`, `[dif_pct]`; filtro `nivel` = historico |

### 7. Presentación
Los gráficos de las diapositivas, en millones de personas, para exportar (**Archivo > Exportar > Exportar a PDF**):
- **Embudo de silver** (diapositiva 11);
- **Fuerza laboral observada + A/B/C** (13): las medidas de la carpeta "Presentación" arrancan los escenarios en el
  último año observado (2025) para que la línea sea continua;
- **Población de 15-64 estimada + KOSTAT medio/alto/bajo** (14);
- **Índice de riesgo por si-do** (15).
