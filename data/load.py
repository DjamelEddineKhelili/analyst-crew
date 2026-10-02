"""
MILESTONE 1a — Load the Olist CSVs into one SQLite database.

Run:   python data/load.py
Result: data/olist.db with one table per CSV.

Put the CSVs you downloaded from Kaggle in data/raw/ first.
"""
from pathlib import Path
import sqlite3

import pandas as pd

RAW = Path(__file__).parent / "raw"
DB_PATH = Path(__file__).parent / "olist.db"

# CSV file name  ->  table name you want in SQL.
# Short names make the agent's life (and yours) easier: "orders" beats "olist_orders_dataset".
TABLES = {
    "olist_orders_dataset.csv": "orders",
    "olist_order_items_dataset.csv": "order_items",
    "olist_order_payments_dataset.csv": "order_payments",
    "olist_order_reviews_dataset.csv": "reviews",
    "olist_customers_dataset.csv": "customers",
    "olist_sellers_dataset.csv": "sellers",
    "olist_products_dataset.csv": "products",
    "olist_geolocation_dataset.csv": "geolocation",
    "product_category_name_translation.csv": "category_translation",}


def build():
    if DB_PATH.exists():
        DB_PATH.unlink()  # delete the existing database file
    
    con = sqlite3.connect(DB_PATH)
   
    for csv_name, table in TABLES.items():
        df = pd.read_csv(RAW / csv_name)
        df.to_sql(table, con, index=False)
        print(len(df), "rows loaded into", table)
    
    con.close()
    


if __name__ == "__main__":
    build()
