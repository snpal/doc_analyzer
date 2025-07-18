from .models import Prompt, PromptSet, PromptQuery, Document, BatchRun, Result, Feedback, init_db
from datetime import datetime, timedelta

sample_documents = [
    {
        'name': 'Project Proposal.docx',
        'content': 'This project proposal outlines our plan to implement a new customer relationship management system. Key objectives include improving customer satisfaction by 25% and reducing response time by 40%. The implementation will require 6 months and a budget of $150,000. Risk factors include data migration challenges and staff training requirements.',
        'file_type': 'docx'
    },
    {
        'name': 'Technical Specs.pdf',
        'content': 'System Requirements:\n- Python 3.11+\n- PostgreSQL 13+\n- 8GB RAM minimum\n- 100GB storage\n\nAPI Endpoints:\n- /api/v1/users\n- /api/v1/products\n- /api/v1/orders\n\nSecurity measures include OAuth2 authentication and rate limiting.',
        'file_type': 'pdf'
    },
    {
        'name': 'Meeting Minutes.txt',
        'content': 'Date: 2024-03-15\nAttendees: John, Sarah, Mike\n\nAction Items:\n1. Sarah to complete security audit by March 30\n2. Mike to prepare user training materials\n3. John to coordinate with vendors\n\nNext meeting scheduled for March 22.',
        'file_type': 'txt'
    }
]

sample_prompts = [
    {
        'name': 'Document Summary',
        'content': 'Please provide a concise summary of the main points in this document.'
    },
    {
        'name': 'Key Findings',
        'content': 'What are the key findings or conclusions presented in this document?'
    },
    {
        'name': 'Action Items',
        'content': 'Please identify and list all action items or next steps mentioned in this document.'
    },
    {
        'name': 'Technical Analysis',
        'content': 'Analyze the technical aspects discussed in this document, including any specifications, requirements, or implementation details.'
    },
    {
        'name': 'Risk Assessment',
        'content': 'Identify and evaluate any risks, challenges, or potential issues mentioned in this document.'
    }
]

sample_sets = [
    {
        'name': 'Basic Analysis',
        'description': 'Common prompts for basic document analysis',
        'prompts': ['Document Summary', 'Key Findings']
    },
    {
        'name': 'Technical Review',
        'description': 'Prompts for technical document review',
        'prompts': ['Technical Analysis', 'Risk Assessment']
    },
    {
        'name': 'Project Management',
        'description': 'Prompts for project management documents',
        'prompts': ['Action Items', 'Risk Assessment', 'Key Findings']
    }
]

sample_batch_runs = [
    {
        'name': 'Q1 Documentation Review',
        'description': 'Comprehensive review of all Q1 project documentation including technical specs, meeting minutes, and project proposals. Focus on identifying project risks and timeline adherence.',
        'status': 'completed',
        'scheduled_for': datetime.utcnow() - timedelta(days=5),
        'completed_at': datetime.utcnow() - timedelta(days=4, hours=18),
    },
    {
        'name': 'Security Implementation Analysis',
        'description': 'Detailed analysis of security implementation documents. Review OAuth2 configuration, rate limiting setup, and API endpoint security measures. Critical for compliance requirements.',
        'status': 'completed',
        'scheduled_for': datetime.utcnow() - timedelta(days=3),
        'completed_at': datetime.utcnow() - timedelta(days=2, hours=14),
    },
    {
        'name': 'Sprint Planning Documents',
        'description': 'Analysis of upcoming sprint planning documents including resource allocation, task breakdowns, and dependency mapping. Will help identify potential bottlenecks.',
        'status': 'running',
        'scheduled_for': datetime.utcnow() - timedelta(hours=2),
        'completed_at': None,
    },
    {
        'name': 'Infrastructure Upgrade Impact',
        'description': 'Assessment of infrastructure upgrade impact across all system components. Includes analysis of hardware requirements, deployment strategies, and migration risks.',
        'status': 'pending_approval',
        'scheduled_for': datetime.utcnow() + timedelta(days=1),
        'completed_at': None,
    },
    {
        'name': 'User Training Materials Review',
        'description': 'Comprehensive review of all user training materials and documentation. Focus on clarity, completeness, and alignment with system functionality.',
        'status': 'approved',
        'scheduled_for': datetime.utcnow() + timedelta(hours=16),
        'completed_at': None,
    },
    {
        'name': 'Data Migration Plan Analysis',
        'description': 'Analysis failed due to missing database schema mappings and incomplete source data documentation.',
        'status': 'failed',
        'scheduled_for': datetime.utcnow() - timedelta(hours=8),
        'completed_at': datetime.utcnow() - timedelta(hours=7),
    },
    {
        'name': 'Legacy System Comparison',
        'description': 'Comparative analysis between current system and legacy system documentation.',
        'status': 'rejected',
        'rejection_reason': 'Legacy system documentation is outdated (last updated 2+ years ago). Please obtain updated documentation before proceeding with the analysis.',
        'scheduled_for': None,
        'completed_at': None,
    },
    {
        'name': 'Vendor Integration Specs',
        'description': 'Review of vendor integration specifications and API documentation for upcoming third-party integrations.',
        'status': 'pending_approval',
        'scheduled_for': datetime.utcnow() + timedelta(days=2),
        'completed_at': None,
    },
    {
        'name': 'Compliance Requirements Update',
        'description': 'Analysis of updated compliance requirements and their impact on existing system documentation.',
        'status': 'approved',
        'scheduled_for': datetime.utcnow() + timedelta(days=1, hours=4),
        'completed_at': None,
    }
]

sample_results = {
    'Project Proposal.docx': {
        'Document Summary': {
            'response': 'This proposal outlines a 6-month CRM implementation project with a $150,000 budget, aiming to improve customer satisfaction by 25% and reduce response time by 40%.',
            'feedback': [
                {'rating': 5, 'comment': 'Excellent summary, captured all key points'},
                {'rating': 4, 'comment': 'Good overview but could mention implementation approach'}
            ]
        },
        'Risk Assessment': {
            'response': 'Key risks identified: 1) Data migration challenges during system transition, 2) Staff training requirements and potential resistance to change.',
            'feedback': [
                {'rating': 5, 'comment': 'Very thorough risk analysis'},
                {'rating': 5, 'comment': 'Clearly identified major concerns'}
            ]
        },
        'Key Findings': {
            'response': 'The project has clear metrics for success: 25% improvement in customer satisfaction and 40% reduction in response time. Budget and timeline are well-defined.',
            'feedback': [
                {'rating': 4, 'comment': 'Good analysis but could include ROI estimates'},
                {'rating': 3, 'comment': 'Missing analysis of resource allocation'}
            ]
        }
    },
    'Technical Specs.pdf': {
        'Technical Analysis': {
            'response': 'The system requires modern infrastructure with Python 3.11+ and PostgreSQL 13+. API design follows RESTful principles with proper security measures including OAuth2 and rate limiting.',
            'feedback': [
                {'rating': 3, 'comment': 'Missed some technical details about scalability'},
                {'rating': 4, 'comment': 'Good coverage of security aspects'},
                {'rating': 5, 'comment': 'Excellent API endpoint documentation'}
            ]
        },
        'Key Findings': {
            'response': 'The technical specifications are comprehensive, covering system requirements, API endpoints, and security measures. Hardware requirements are clearly specified.',
            'feedback': [
                {'rating': 5, 'comment': 'Perfect summary of technical requirements'},
                {'rating': 4, 'comment': 'Well-structured but could include deployment steps'}
            ]
        },
        'Risk Assessment': {
            'response': 'System requirements may pose upgrade challenges for existing infrastructure. Security implementation (OAuth2) will require careful configuration.',
            'feedback': [
                {'rating': 4, 'comment': 'Good security considerations'},
                {'rating': 3, 'comment': 'Should mention potential scalability risks'}
            ]
        }
    },
    'Meeting Minutes.txt': {
        'Action Items': {
            'response': '1. Security audit completion by Sarah (Due: March 30)\n2. User training materials preparation by Mike\n3. Vendor coordination by John\n4. Follow-up meeting on March 22',
            'feedback': [
                {'rating': 5, 'comment': 'Very clear action items list'},
                {'rating': 5, 'comment': 'Well-organized with clear ownership'}
            ]
        },
        'Document Summary': {
            'response': 'Meeting held on March 15 with John, Sarah, and Mike. Key action items assigned including security audit, training materials, and vendor coordination.',
            'feedback': [
                {'rating': 4, 'comment': 'Good summary but could include meeting duration'},
                {'rating': 5, 'comment': 'Excellent capture of key points and assignments'}
            ]
        },
        'Key Findings': {
            'response': 'Three main tasks were assigned with one specific deadline. Team is focusing on security, training, and vendor management aspects.',
            'feedback': [
                {'rating': 4, 'comment': 'Clear identification of main points'},
                {'rating': 3, 'comment': 'Could highlight priority order of tasks'}
            ]
        }
    }
}

def initialize_sample_data():
    """Initialize the database with sample prompts and sets"""
    db = init_db()()
    
    doc_dict = {}
    for doc_data in sample_documents:
        doc = Document(
            name=doc_data['name'],
            content=doc_data['content'],
            file_type=doc_data['file_type'],
            uploaded_at=datetime.utcnow() - timedelta(days=1)  # Yesterday
        )
        db.add(doc)
        doc_dict[doc.name] = doc
    
    # Add prompts
    prompt_dict = {}
    for prompt_data in sample_prompts:
        prompt = Prompt(
            name=prompt_data['name'],
            content=prompt_data['content']
        )
        db.add(prompt)
        prompt_dict[prompt.name] = prompt
    
    # Add sets
    for set_data in sample_sets:
        prompt_set = PromptSet(
            name=set_data['name'],
            description=set_data['description']
        )
        
        # Add prompts to set
        for prompt_name in set_data['prompts']:
            if prompt_name in prompt_dict:
                prompt_set.prompts.append(prompt_dict[prompt_name])
        
        db.add(prompt_set)
    
    # Create batch runs and results
    for batch_data in sample_batch_runs:
        batch_run = BatchRun(
            name=batch_data['name'],
            description=batch_data['description'],
            status=batch_data['status'],
            scheduled_for=batch_data['scheduled_for'],
            completed_at=batch_data['completed_at'],
            rejection_reason=batch_data.get('rejection_reason')
        )
        db.add(batch_run)
        
        # Only add results for completed batch runs
        if batch_data['status'] == 'completed':
            # Add all documents and prompts to this batch
            for doc in doc_dict.values():
                batch_run.documents.append(doc)
            for prompt in prompt_dict.values():
                batch_run.prompts.append(prompt)
            
            # Add results and feedback
            for doc in batch_run.documents:
                for prompt in batch_run.prompts:
                    result = Result(
                        document=doc,
                        prompt=prompt,
                        batch_run=batch_run,
                        response=f"Sample result for {doc.name} with prompt {prompt.name}"
                    )
                    db.add(result)
                    
                    # Add some sample feedback
                    feedback = Feedback(
                        result=result,
                        rating=4,
                        comment="Good analysis of the document content"
                    )
                    db.add(feedback)
        
        elif batch_data['status'] in ['pending_approval', 'approved']:
            # For pending and approved runs, just add the documents and prompts
            for doc in list(doc_dict.values())[:2]:  # Add first two documents
                batch_run.documents.append(doc)
            for prompt in list(prompt_dict.values())[:2]:  # Add first two prompts
                batch_run.prompts.append(prompt)
    
    db.commit()
    db.close()

if __name__ == '__main__':
    initialize_sample_data() 