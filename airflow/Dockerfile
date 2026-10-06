# Imagen de Airflow con las dependencias del pipeline. El código del proyecto no se copia: se monta como volumen
# (docker-compose.yml), así un cambio en src/ o en el DAG se ve sin reconstruir la imagen.
ARG AIRFLOW_VERSION=3.3.2
FROM apache/airflow:${AIRFLOW_VERSION}-python3.12
ARG AIRFLOW_VERSION
COPY requirements.txt /tmp/requirements.txt
# Se fija la versión de Airflow para que pip no la cambie al instalar el resto.
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /tmp/requirements.txt
