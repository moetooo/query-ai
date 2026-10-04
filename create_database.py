import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "amazon.db")


def create_database(db_path: str = DB_PATH) -> None:
    """Create or reset the database with clean schema and sample data."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")

        # Step 1: Drop existing tables in reverse foreign key order
        cursor.execute("DROP TABLE IF EXISTS order_items;")
        cursor.execute("DROP TABLE IF EXISTS orders;")
        cursor.execute("DROP TABLE IF EXISTS products;")
        cursor.execute("DROP TABLE IF EXISTS customers;")

        # Step 2: Create Tables
        cursor.execute("""
        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            city TEXT,
            join_date TEXT
        );
        """)

        cursor.execute("""
        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            price REAL NOT NULL
        );
        """)

        cursor.execute("""
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            order_date TEXT,
            total_amount REAL,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        );
        """)

        cursor.execute("""
        CREATE TABLE order_items (
            order_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            subtotal REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );
        """)

        # Step 3: Enter dummy data
        customers = [
            ('Alice Johnson', 'alice@example.com', 'New York', '2024-01-10'),
            ('Bob Smith', 'bob@example.com', 'Los Angeles', '2024-02-14'),
            ('Charlie Lee', 'charlie@example.com', 'Chicago', '2024-03-01'),
            ('Diana King', 'diana@example.com', 'Houston', '2024-04-20')
        ]
        cursor.executemany(
            "INSERT INTO customers (name, email, city, join_date) VALUES (?, ?, ?, ?)",
            customers
        )

        products = [
            ('Wireless Mouse', 'Electronics', 25.99),
            ('Laptop Sleeve', 'Accessories', 15.49),
            ('Bluetooth Headphones', 'Electronics', 45.99),
            ('Water Bottle', 'Home & Kitchen', 12.00),
            ('Notebook', 'Stationery', 3.50)
        ]
        cursor.executemany(
            "INSERT INTO products (name, category, price) VALUES (?, ?, ?)",
            products
        )

        orders = [
            (1, '2024-05-05', 83.47),
            (2, '2024-05-07', 15.49),
            (3, '2024-06-02', 57.99),
            (1, '2024-06-10', 12.00)
        ]
        cursor.executemany(
            "INSERT INTO orders (customer_id, order_date, total_amount) VALUES (?, ?, ?)",
            orders
        )

        order_items = [
            (1, 1, 2, 25.99 * 2),  # Alice bought 2 Mice
            (1, 3, 1, 45.99),      # Alice bought 1 Headphone
            (2, 2, 1, 15.49),      # Bob bought 1 Laptop Sleeve
            (3, 3, 1, 45.99),      # Charlie bought 1 Headphone
            (3, 5, 2, 3.50 * 2),   # Charlie bought 2 Notebooks
            (4, 4, 1, 12.00)       # Alice bought 1 Water Bottle (order 4)
        ]
        cursor.executemany(
            "INSERT INTO order_items (order_id, product_id, quantity, subtotal) VALUES (?, ?, ?, ?)",
            order_items
        )

        conn.commit()

    print(f"[SUCCESS] Database '{db_path}' created with dummy data!")


if __name__ == '__main__':
    create_database()