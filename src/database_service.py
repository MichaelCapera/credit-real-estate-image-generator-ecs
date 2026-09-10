import os
import logging
import psycopg2
from psycopg2.extras import execute_values

logger = logging.getLogger(__name__)

class DatabaseService:
    """
    Service responsible for managing database records in PostgreSQL with a rolling window strategy.
    """
    def __init__(self):
        pass

    def save_to_database(self, properties: list, db_config: dict):
        """
        Clears previous records and saves the fresh batch of properties into PostgreSQL,
        ensuring the table only contains the active daily batch.
        """
        if not properties:
            logger.warning("[DB] No properties array provided to save.")
            return

        connection = None
        try:
            connection = psycopg2.connect(
                dbname=db_config.get('dbname'),
                user=db_config.get('user'),
                password=db_config.get('password'),
                host=db_config.get('host'),
                port=db_config.get('port', '5432')
            )
            cursor = connection.cursor()

            cursor.execute("TRUNCATE TABLE property_stories;")
            
            records = []
            for prop in properties:
                prop_id = str(prop.get('id', ''))
                title = prop.get('title', 'Untitled Real Estate Node')
                image_url = prop.get('image_url', '')
                records.append((prop_id, title, image_url))

            insert_query = """
                INSERT INTO property_stories (property_id, title, image_url)
                VALUES %s;
            """
            
            execute_values(cursor, insert_query, records)
            connection.commit()
            logger.info(f"[DB] Rolling window synchronized. Successfully replaced table content with {len(records)} active records.")

        except Exception as e:
            if connection:
                connection.rollback()
            logger.error(f"[DB EXCEPTION] Failed to persist data into database: {str(e)}")
        finally:
            if connection:
                cursor.close()
                connection.close()