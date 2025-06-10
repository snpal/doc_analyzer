from datetime import datetime
from typing import List, Optional
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Table, Boolean, JSON
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.ext.declarative import declared_attr

Base = declarative_base()

# Association tables for many-to-many relationships
document_batch = Table(
    'document_batch',
    Base.metadata,
    Column('document_id', Integer, ForeignKey('documents.id')),
    Column('batch_run_id', Integer, ForeignKey('batch_runs.id'))
)

prompt_batch = Table(
    'prompt_batch',
    Base.metadata,
    Column('prompt_id', Integer, ForeignKey('prompts.id')),
    Column('batch_run_id', Integer, ForeignKey('batch_runs.id'))
)

document_set = Table(
    'document_set',
    Base.metadata,
    Column('document_id', Integer, ForeignKey('documents.id')),
    Column('set_id', Integer, ForeignKey('document_sets.id'))
)

prompt_set = Table(
    'prompt_set',
    Base.metadata,
    Column('prompt_id', Integer, ForeignKey('prompts.id')),
    Column('set_id', Integer, ForeignKey('prompt_sets.id'))
)

class Document(Base):
    __tablename__ = 'documents'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    content = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    file_type = Column(String)
    
    batch_runs = relationship('BatchRun', secondary=document_batch, back_populates='documents')
    results = relationship('Result', back_populates='document')
    sets = relationship('DocumentSet', secondary=document_set, back_populates='documents')

class DocumentSet(Base):
    __tablename__ = 'document_sets'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    documents = relationship('Document', secondary=document_set, back_populates='sets')
    queries = relationship('DocumentQuery', back_populates='document_set')

class DocumentQuery(Base):
    __tablename__ = 'document_queries'
    
    id = Column(Integer, primary_key=True)
    set_id = Column(Integer, ForeignKey('document_sets.id'))
    name = Column(String, nullable=False)
    query_type = Column(String, nullable=False)  # 'name', 'content', 'file_type'
    query_value = Column(String, nullable=False)
    operator = Column(String, nullable=False)  # 'contains', 'equals', 'startswith', etc.
    created_at = Column(DateTime, default=datetime.utcnow)
    
    document_set = relationship('DocumentSet', back_populates='queries')

class Prompt(Base):
    __tablename__ = 'prompts'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    batch_runs = relationship('BatchRun', secondary=prompt_batch, back_populates='prompts')
    results = relationship('Result', back_populates='prompt')
    sets = relationship('PromptSet', secondary=prompt_set, back_populates='prompts')

class PromptSet(Base):
    __tablename__ = 'prompt_sets'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    prompts = relationship('Prompt', secondary=prompt_set, back_populates='sets')
    queries = relationship('PromptQuery', back_populates='prompt_set')

class PromptQuery(Base):
    __tablename__ = 'prompt_queries'
    
    id = Column(Integer, primary_key=True)
    set_id = Column(Integer, ForeignKey('prompt_sets.id'))
    name = Column(String, nullable=False)
    query_type = Column(String, nullable=False)  # 'name', 'content'
    query_value = Column(String, nullable=False)
    operator = Column(String, nullable=False)  # 'contains', 'equals', 'startswith', etc.
    created_at = Column(DateTime, default=datetime.utcnow)
    
    prompt_set = relationship('PromptSet', back_populates='queries')

class BatchRun(Base):
    __tablename__ = 'batch_runs'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    status = Column(String, default='pending')  # pending, running, completed, failed
    scheduled_for = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    documents = relationship('Document', secondary=document_batch, back_populates='batch_runs')
    prompts = relationship('Prompt', secondary=prompt_batch, back_populates='batch_runs')
    results = relationship('Result', back_populates='batch_run')

class Result(Base):
    __tablename__ = 'results'
    
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('documents.id'))
    prompt_id = Column(Integer, ForeignKey('prompts.id'))
    batch_run_id = Column(Integer, ForeignKey('batch_runs.id'))
    response = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    document = relationship('Document', back_populates='results')
    prompt = relationship('Prompt', back_populates='results')
    batch_run = relationship('BatchRun', back_populates='results')
    feedback = relationship('Feedback', back_populates='result')

class Feedback(Base):
    __tablename__ = 'feedback'
    
    id = Column(Integer, primary_key=True)
    result_id = Column(Integer, ForeignKey('results.id'))
    rating = Column(Integer)  # 1-5 rating
    comment = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    result = relationship('Result', back_populates='feedback')

# Database initialization
def init_db(db_url='sqlite:///doc_analyzer.db'):
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine) 