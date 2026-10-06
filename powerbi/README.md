# Tablero de Power BI

`Tablero_ETL_Corea_Grupo6.pbip` es el tablero del proyecto: portada y 7 páginas con menú lateral, con el diseño del
equipo (Angie Rodríguez). Responde las 10 preguntas de negocio y tiene una versión web con el mismo diseño
(`dashboard/Tablero_ETL_Corea_Grupo6.html`, ver más abajo).

| Página | Contenido | Preguntas |
|---|---|---|
| Portada | Pregunta central, equipo y acceso a las secciones | — |
| Resumen | 6 tarjetas y los 14 KPIs del problema con semáforo | 8, 10 |
| Natalidad | Nacimientos, fecundidad frente al reemplazo, fecundidad por si-do, nacimientos vs defunciones | 1 |
| Envejecimiento | Pirámide por año (selector), grandes grupos de edad, dependencia de vejez, esperanza de vida | 3 |
| Fuerza laboral | Población 15-64 en los 8 escenarios de KOSTAT, fuerza laboral potencial A/B/C/D (selector de escenario), reemplazo laboral, participación por edad y sexo | 2, 4, 6, 8 |
| Regiones | Índice de riesgo por si-do, sus componentes y mapa | 5 |
| Corea vs OCDE | Fecundidad, 65+ y dependencia frente a 7 países y el promedio OCDE; PIB por hora | 7, 9 |
| Calidad y OKR | Resultados clave O1-O4, registros válidos, rechazo, conciliación y calidad por dataset | — |

Convención: línea continua = observado o estimado; discontinua = proyección oficial o escenario propio.

## Cómo se arma

```
data/gold/powerbi/pbi_*.parquet          capa de servicio: 16 tablas con la forma que necesita cada visual
        │                                (src/transform/gold/servicio_bi.py, se regenera al final de la capa gold)
        ▼
Tablero_ETL_Corea_Grupo6.SemanticModel   modelo TMDL: tablas, relaciones por año y territorio y medidas DAX
        │                                (src/load/powerbi.py)
        ▼
Tablero_ETL_Corea_Grupo6.Report          páginas, visuales, imágenes y tema (PBIR, versionado tal cual)
```

Las transformaciones están en Python y quedan auditadas en el repositorio; Power Query solo lee los archivos Parquet.

## Abrir y actualizar

1. Correr el pipeline (o al menos la capa gold): `python main.py --capa gold`.
2. Abrir `powerbi/Tablero_ETL_Corea_Grupo6.pbip` con Power BI Desktop.
3. Si el repositorio está en otra carpeta: **Transformar datos → Editar parámetros → RutaGold** con la ruta de
   `data\gold\` (terminada en `\`).
4. **Actualizar**.

Para entregar un solo archivo: **Archivo → Guardar como** `.pbix` (queda con los datos incluidos).

Si cambian las columnas de la capa de servicio, regenerar el modelo con `python -m src.load.powerbi` y volver a abrir
el proyecto. Si solo cambian los datos, basta con **Actualizar**.

## Versión web

```bash
python dashboard/generar_tablero.py      # dashboard/Tablero_ETL_Corea_Grupo6.html
```

Un solo archivo HTML con Plotly que lee la misma capa de servicio y replica las 8 páginas. Funciona sin conexión y sin
Power BI: se abre con doble clic en cualquier navegador.
