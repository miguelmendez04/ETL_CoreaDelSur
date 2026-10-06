# Orquestación con Apache Airflow

Airflow ejecuta el pipeline (bronze -> silver -> gold) de forma automática y programada, y deja a la vista cada
ejecución: qué tarea corrió, cuánto tardó, su log y si falló. Es opcional: `python main.py` sigue funcionando igual.

## Puesta en marcha

Requisitos: Docker Desktop con ~4 GB de memoria disponible y el `.env` del proyecto completo (el mismo de siempre).

```bash
docker compose --profile airflow up -d --build    # la primera vez descarga ~1,5 GB y construye la imagen
```

Abrir http://localhost:8080 (sin usuario: es una instalación local). El DAG `etl_corea` aparece pausado.
Para que corra:
1. activarlo con el interruptor junto a su nombre. Corre una vez de inmediato (la semana más reciente) y
   luego cada domingo a medianoche;
2. o lanzarlo a mano con el botón **Trigger** (▶).

Para apagar Airflow sin tocar la base del proyecto: `docker compose --profile airflow stop`.

Por consola, desde la raíz del proyecto:

```bash
docker compose exec airflow-scheduler airflow dags trigger etl_corea     # lanzar una ejecución
docker compose exec airflow-scheduler airflow dags list-runs etl_corea   # ver el historial
```

## Conceptos, con este proyecto

| Concepto | Qué es | En este proyecto |
|---|---|---|
| **DAG** | Grafo dirigido sin ciclos: las tareas y el orden en que dependen unas de otras. Es un archivo Python | `dags/etl_corea.py` |
| **Tarea** (task) | Una unidad de trabajo que puede fallar, reintentarse y tener su log por separado | `bronze_worldbank`, `bronze_oecd`, `bronze_unwpp`, `bronze_kosis`, `silver`, `gold`, `verificar_kpis` |
| **Dependencias** | `a >> b`: b corre solo si a terminó bien | Las 4 fuentes en paralelo `>> silver >> gold >> verificar_kpis` |
| **Programación** (schedule) | Cada cuánto se crea una ejecución | `@weekly`. Las fuentes son anuales o mensuales: más seguido no aporta |
| **Ejecución** (DAG run) | Una corrida completa del DAG. Puede ser programada o manual | Se ven en la pestaña *Runs* |
| **Reintentos** (retries) | Si una tarea falla, Airflow la repite sola | 2 reintentos con 5 minutos de espera (p. ej. una API caída un momento) |
| **Scheduler** | El proceso que decide qué tarea corre y cuándo | Servicio `airflow-scheduler` |
| **Ejecutor** (executor) | Cómo se ejecutan las tareas | `LocalExecutor`: como procesos dentro del scheduler (suficiente para un solo PC) |
| **DAG processor** | Lee la carpeta `dags/` y registra los cambios | Servicio `airflow-dag-processor`. Al editar el DAG, el cambio aparece en segundos |
| **API server** | La interfaz web y la API | Servicio `airflow-apiserver`, http://localhost:8080 |
| **XCom** | Valores pequeños que una tarea devuelve y otras pueden leer | Cada tarea devuelve un resumen: conteos por estado, filas por tabla, KPIs cumplidos |

## Cómo está montado

```
docker-compose.yml (perfil "airflow")
├── airflow-db              PostgreSQL interno de Airflow: historial de ejecuciones (no es la base del proyecto)
├── airflow-init            crea o actualiza las tablas internas de Airflow y termina
├── airflow-apiserver       interfaz web (puerto 8080)
├── airflow-scheduler       programa y ejecuta las tareas
└── airflow-dag-processor   lee dags/
```

- **Imagen:** `airflow/Dockerfile` parte de la imagen oficial de Airflow 3.3.2 (Python 3.12) y le instala las
  dependencias del pipeline (`airflow/requirements.txt`).
- **Código:** no se copia a la imagen: el proyecto completo se monta en `/opt/airflow/proyecto`. Un cambio en
  `src/`, en `config.yaml` o en el DAG se usa en la siguiente ejecución, sin reconstruir nada.
- **Conexión a la base del proyecto:** dentro de Docker, la base del proyecto no es `localhost` sino el servicio
  `postgres`. Por eso el compose fija `PG_HOST=postgres` y `PG_PORT=5432`; el resto de credenciales sale del `.env`.
- **Hora:** los contenedores usan `TZ=America/Bogota`, igual que el PC. Sin eso las fechas de las carpetas y de
  extracción quedarían en UTC y cambiarían los `_metadata.json` versionados de KOSIS.

## El DAG no tiene lógica de datos

Cada tarea llama a la misma función que usa `main.py` (`ejecutar_bronze`, `ejecutar_silver`, `ejecutar_gold`).
Así, correr el pipeline con Airflow o con `python main.py` da exactamente el mismo resultado y deja la misma
bitácora en `ctl.log_cargas`.

Repetir una tarea es seguro:
- en bronze, si el crudo no cambió, la carga queda `omitido` y no se duplica;
- silver y gold se reconstruyen completos en una transacción.

`verificar_kpis` lee `gold.v_kpis_calidad` y termina en rojo si algún KPI no cumple su meta. Es la alerta de
calidad del pipeline.

## Dónde mirar cuando algo falla

1. En la interfaz: la tarea en rojo > **Logs**. Ahí está todo lo que registra el pipeline (resúmenes de cada capa,
   rechazos, KPIs) y el error.
2. En la base: `SELECT * FROM ctl.log_cargas ORDER BY id_carga DESC;` (estado y mensaje de cada carga).
3. Si el DAG no aparece: `docker compose exec airflow-scheduler airflow dags list-import-errors`.
