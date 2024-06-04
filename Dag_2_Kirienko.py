import os 
import sys
import requests
import pendulum
import pandas as pd
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

# Добавляем путь к директории, где находится transform_script.py
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from transform_script import transform  # импортируем функцию transfrom из скрипта

# Настройки по умолчанию для DAG
DAG_ID = 'Bondareva_Alina_dag2'  # имя DAG
default_args = {
    'owner': 'airflow',  # владелец DAG
    'start_date': pendulum.datetime(2023, 4, 5, tz=pendulum.timezone("Europe/Moscow")),  # дата начала выполнения DAG
    'schedule_interval': '0 0 5 * *',  # расписание запуска DAG (каждое 5-е число месяца в 00:00)
    'retries': 3,  # количество попыток перезапуска задач в случае ошибки
    "retry_delay": timedelta(seconds=60),  # время задержки между перезапусками
    'description': 'ETL DAG for monthly calculation of customer activity based on transactions.',  # описание DAG
    'max_active_runs': 10,  # максимальное количество активных запусков DAG
    'catchup': False,  # отключение догоняющего выполнения
}
# Шаг 1: Функция для скачивания данных
def DownloadData(date, **kwargs):
    """
    Функция для скачивания и сохранения данных из csv-файла.
    :param date: дата в формате 'YYYY-MM-DD'
    """
    url = 'https://drive.usercontent.google.com/download?id=1hkkOIxnYQTa7WD1oSIDUFgEoBoWfjxK2&export=download&authuser=0&confirm=t&uuid=af8f933c-070d-4ea5-857b-2c31f2bad050&at=APZUnTVuHs3BtcrjY_dbuHsDceYr:1716219233729'  # URL для загрузки данных
    data_dir = '/tmp/airflow/data/'  # временная директория для сохранения данных
    os.makedirs(data_dir, exist_ok=True)  # создаем директорию, если она не существует
    output_path = os.path.join(data_dir, f'profit_table_{date}.csv')  # путь для сохранения файла

    response = requests.get(url)  # загружаем данные по указанному URL
    response.raise_for_status()  # проверка успешности запроса

    with open(output_path, 'wb') as file:  # открываем файл для записи в бинарном режиме
        file.write(response.content)  # записываем содержимое ответа в файл

    # Логирование успешного скачивания данных
    ti = kwargs['ti'] # Получаем экземпляр TaskInstance из kwargs
    ti.xcom_push(key='download_success', value=True) # Сохраняем значение True в XCom
    print(f"Файл успешно загружен и сохранен в {output_path}")

# Шаг 2: Фцнкция для обработки данных
def ProcessProduct(product, date, **kwargs):
    """
    Функция для обработки данных по каждому продукту.
    :param product: название продукта (буква от 'a' до 'j')
    :param date: дата в формате 'YYYY-MM-DD'
    """
    data_path = f'/tmp/airflow/data/profit_table_{date}.csv'  # путь к файлу данных
    df = pd.read_csv(data_path)  # читаем данные из csv-файла
    transformed_df = transform(df, date, product)  # трансформируем данные с использованием функции `transfrom``
    Load(transformed_df, date, product)  # загружаем трансформированные данные

# Шаг 3: Функция для загрузки данных
def Load(df, date, product):
    """
    Функция для загрузки данных в csv-файл.
    :param df: DataFrame с трансформированными данными
    :param product: название продукта (буква от 'a' до 'j')
    """
    base_dir = '/tmp/airflow/data/'  # временная директория для сохранения файла
    output_path = os.path.join(base_dir, f'flags_activity_{product}_{date}.csv')  # путь для сохранения итогового файла
    if os.path.exists(output_path):
        existing_df = pd.read_csv(output_path)  # читаем существующий файл
        updated_df = pd.concat([existing_df, df], ignore_index=True)  # объединяем существующие данные с новыми
        updated_df.to_csv(output_path, index=False)  # сохраняем объединенные данные обратно в файл
    else:
        df.to_csv(output_path, index=False)  # сохраняем новые данные в новый файл, если файл не существует


# Определяем DAG
with DAG(
    DAG_ID,  # имя DAG
    default_args=default_args,  # аргументы по умолчанию
    description=default_args.get("description"),
    start_date=default_args.get("start_date"),
    schedule_interval=default_args.get("schedule_interval"),
    catchup=default_args.get("catchup"),
    max_active_runs=default_args.get("max_active_runs")
) as dag:

    # Задача для загрузки данных
    download_task = PythonOperator(
        task_id='download_data',  # идентификатор задачи
        python_callable=DownloadData,  # вызываемая функция
        op_kwargs={'date': '{{ ds }}'},  # аргументы функции (дата запуска DAG)
        provide_context=True  # включаем контекст
    )

    # Создаем задачи для каждого продукта
    product_tasks = []
    for product in 'abcdefghij':
        task = PythonOperator(
            task_id=f'process_{product}',  # идентификатор задачи
            python_callable=ProcessProduct,  # вызываемая функция
            op_kwargs={'product': product, 'date': '{{ ds }}'}, # аргументы функции (название продукта и дата)
            provide_context=True  # включаем контекст
        )
        product_tasks.append(task)  # добавляем задачу в список
        download_task >> task  # задаем порядок выполнения задач (сначала download_task, затем каждая задача по продукту)
