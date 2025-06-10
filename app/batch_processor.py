import asyncio
from datetime import datetime
from sqlalchemy import and_
from models import BatchRun, Result, Document, DocumentSet, DocumentQuery, init_db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def process_document_with_prompt(document, prompt, batch_run, db):
    """
    Process a single document with a single prompt.
    In a real implementation, this would call your document processing logic.
    """
    try:
        # Simulate document processing - replace with actual implementation
        response = f"Processed document '{document.name}' with prompt '{prompt.name}'"
        
        result = Result(
            document=document,
            prompt=prompt,
            batch_run=batch_run,
            response=response
        )
        db.add(result)
        db.commit()
        
        logger.info(f"Processed document {document.name} with prompt {prompt.name}")
        return True
    except Exception as e:
        logger.error(f"Error processing document {document.name} with prompt {prompt.name}: {str(e)}")
        return False

async def process_batch_run(batch_run_id):
    """Process all documents and prompts in a batch run"""
    db = init_db()()
    try:
        batch_run = db.query(BatchRun).get(batch_run_id)
        if not batch_run:
            logger.error(f"Batch run {batch_run_id} not found")
            return
        
        batch_run.status = 'running'
        db.commit()
        
        success = True
        for document in batch_run.documents:
            for prompt in batch_run.prompts:
                result = await process_document_with_prompt(document, prompt, batch_run, db)
                if not result:
                    success = False
        
        batch_run.status = 'completed' if success else 'failed'
        batch_run.completed_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Completed batch run {batch_run_id} with status {batch_run.status}")
    except Exception as e:
        logger.error(f"Error processing batch run {batch_run_id}: {str(e)}")
        batch_run.status = 'failed'
        batch_run.completed_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()

async def process_document_queries(document: Document, db) -> None:
    """Process a document against all existing queries"""
    try:
        # Get all document sets with queries
        sets = db.query(DocumentSet).all()
        
        for doc_set in sets:
            for query in doc_set.queries:
                matches = False
                value = getattr(document, query.query_type)
                
                if query.operator == 'contains':
                    matches = query.query_value.lower() in value.lower()
                elif query.operator == 'equals':
                    matches = query.query_value.lower() == value.lower()
                elif query.operator == 'startswith':
                    matches = value.lower().startswith(query.query_value.lower())
                elif query.operator == 'endswith':
                    matches = value.lower().endswith(query.query_value.lower())
                
                if matches and document not in doc_set.documents:
                    doc_set.documents.append(document)
                    logger.info(f"Document {document.name} added to set {doc_set.name} based on query {query.name}")
        
        db.commit()
    except Exception as e:
        logger.error(f"Error processing queries for document {document.name}: {str(e)}")
        db.rollback()

async def check_and_process_scheduled_runs():
    """Check for scheduled runs and process them"""
    while True:
        try:
            db = init_db()()
            
            # Process any new documents against existing queries
            new_documents = db.query(Document).filter(
                ~Document.sets.any()  # Documents not in any sets
            ).all()
            
            for doc in new_documents:
                await process_document_queries(doc, db)
            
            # Find scheduled runs that should start now
            pending_runs = db.query(BatchRun).filter(
                and_(
                    BatchRun.status == 'pending',
                    BatchRun.scheduled_for <= datetime.utcnow()
                )
            ).all()
            
            for run in pending_runs:
                logger.info(f"Starting scheduled batch run {run.id}")
                asyncio.create_task(process_batch_run(run.id))
            
            db.close()
        except Exception as e:
            logger.error(f"Error checking scheduled runs: {str(e)}")
        
        # Check every minute
        await asyncio.sleep(60)

# Function to start the background processor
def start_background_processor():
    asyncio.create_task(check_and_process_scheduled_runs()) 