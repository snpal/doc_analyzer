from .models import Base, init_db
from .sample_data import initialize_sample_data
import os

def init_database():
    # Remove existing database if it exists
    if os.path.exists('doc_analyzer.db'):
        os.remove('doc_analyzer.db')
    
    # Create database and tables
    engine = init_db()().get_bind()
    Base.metadata.create_all(engine)
    
    # Initialize sample data
    initialize_sample_data()
    
    print("Database initialized successfully!")

if __name__ == '__main__':
    init_database() 