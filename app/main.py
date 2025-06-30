from nicegui import ui, app
from datetime import datetime, timedelta
import os
from sqlalchemy.orm import Session
from .models import init_db, Document, Prompt, BatchRun, Result, Feedback, DocumentSet, DocumentQuery, PromptSet, PromptQuery
from typing import List, Optional
import asyncio
from .batch_processor import start_background_processor
from .sample_data import initialize_sample_data

SessionLocal = init_db()

try:
    db = SessionLocal()
    if db.query(Prompt).count() == 0:
        initialize_sample_data()
finally:
    db.close()

def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

def format_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")

class SharedState:
    """Shared state between components"""
    def __init__(self):
        self.selected_documents = set()
        self.selected_document_details = {}  # Store document details for display
        self.on_selection_change_callbacks = []
        self.on_clear_selection_callbacks = []  # New list for clear selection callbacks

    def update_selection(self, doc_id: int, doc_details: dict, selected: bool):
        if selected:
            self.selected_documents.add(doc_id)
            self.selected_document_details[doc_id] = doc_details
        else:
            self.selected_documents.discard(doc_id)
            self.selected_document_details.pop(doc_id, None)
        
        # Notify all listeners
        for callback in self.on_selection_change_callbacks:
            callback()

    def get_selected_count(self) -> int:
        return len(self.selected_documents)

    def get_selected_names(self) -> str:
        return ", ".join(self.selected_document_details[doc_id]["name"] 
                        for doc_id in self.selected_documents)

    def clear_selection(self):
        self.selected_documents.clear()
        self.selected_document_details.clear()
        for callback in self.on_selection_change_callbacks:
            callback()

# Create a global shared state
shared_state = SharedState()

class SelectionHeader:
    def __init__(self):
        with ui.row().classes('w-full items-center bg-blue-100 p-4'):
            self.selection_label = ui.label('No documents selected').classes('flex-grow')
            ui.button('Clear Selection', on_click=self.clear_selection).props('flat')
        
        # Register for selection updates
        shared_state.on_selection_change_callbacks.append(self.update_header)
        
    def update_header(self):
        count = shared_state.get_selected_count()
        if count > 0:
            names = shared_state.get_selected_names()
            self.selection_label.text = f'{count} documents selected: {names}'
        else:
            self.selection_label.text = 'No documents selected'
    
    def clear_selection(self):
        shared_state.clear_selection()
        # Notify all document viewers to clear their table selection
        for callback in shared_state.on_clear_selection_callbacks:
            callback()

class DocumentViewer:
    def __init__(self):
        self.selected_documents = shared_state.selected_documents  # Use shared state
        
        with ui.card().classes('w-full'):
            ui.label('Available Documents').classes('text-h6')
            
            # Preview dialog - Initialize first
            self.preview_dialog = ui.dialog()
            with self.preview_dialog:
                with ui.card().classes('p-4'):
                    self.preview_title = ui.label().classes('text-h6 mb-4')
                    self.preview_content = ui.textarea(
                        label='Content',
                        value=''
                    ).props('disable').classes('w-full min-w-[600px] min-h-[400px]')
                    with ui.row().classes('w-full justify-end mt-4'):
                        ui.button('Close', on_click=lambda: self.preview_dialog.close()).props('flat')
            
            # Search and filter section
            with ui.row().classes('w-full items-end justify-between'):
                with ui.column().classes('w-full'):
                    with ui.row().classes('w-full items-end'):
                        with ui.column().classes('w-1/4 pr-2'):
                            self.search_input = ui.input(label='Search').classes('w-full')
                            self.search_input.on('change', self.update_documents)
                        
                        with ui.column().classes('w-1/4 pr-2'):
                            self.search_column = ui.select(
                                options=[
                                    {'label': 'All Columns', 'value': 'all'},
                                    {'label': 'Document Name', 'value': 'name'},
                                    {'label': 'File Type', 'value': 'file_type'},
                                    {'label': 'Sets', 'value': 'sets'}
                                ],
                                label='Search In'
                            ).classes('w-full')
                            self.search_column.value = 'all'
                            self.search_column.on('change', self.update_documents)
                        
                        with ui.column().classes('w-1/4 pr-2'):
                            type_options = [{'label': 'All Types', 'value': 'all'}]
                            self.type_filter = ui.select(
                                options=type_options,
                                label='File Type'
                            ).classes('w-full')
                            self.type_filter.value = 'all'
                            self.type_filter.on('change', self.update_documents)
                        
                        with ui.column().classes('w-1/4'):
                            set_options = [{'label': 'All Sets', 'value': 'all'}]
                            self.set_filter = ui.select(
                                options=set_options,
                                label='Set'
                            ).classes('w-full')
                            self.set_filter.value = 'all'
                            self.set_filter.on('change', self.update_documents)
                
                with ui.column().classes('ml-4'):
                    with ui.row():
                        ui.button('Create New Set', on_click=self.show_create_set_dialog).props('color=primary')
                        ui.button('Manage Sets', on_click=self.show_manage_sets_dialog).props('color=secondary')
            
            # Initialize filter options
            self.update_filter_options()
            
            # Documents table
            with ui.table(
                columns=[
                    {'name': 'name', 'label': 'Document Name', 'field': 'name', 'sortable': True},
                    {'name': 'file_type', 'label': 'Type', 'field': 'file_type'},
                    {'name': 'uploaded_at', 'label': 'Upload Date', 'field': 'uploaded_at', 'sortable': True},
                    {'name': 'sets', 'label': 'Sets', 'field': 'sets'},
                    {'name': 'actions', 'label': 'Actions', 'field': 'actions'},
                ],
                rows=self.get_documents(),
                pagination=10,
                row_key='id',
                selection='multiple'
            ).classes('w-full') as self.documents_table:
                actions_template = '''
                    <q-td key="actions" :props="props">
                        <q-btn flat color="primary" label="Preview" @click="$emit('preview', props.row)" />
                    </q-td>
                '''
                self.documents_table.add_slot('body-cell-actions', actions_template)
                self.documents_table.on('preview', self.handle_preview)
                self.documents_table.on('selection', self.handle_selection)
                
                # Register for clear selection events
                shared_state.on_clear_selection_callbacks.append(self.clear_table_selection)
            
            with ui.row().classes('w-full mt-4'):
                self.selection_label = ui.label('0 documents selected')
                ui.button('Add to Set', on_click=self.show_add_to_set_dialog).props('color=primary')
            
            self.create_set_dialog = ui.dialog()
            with self.create_set_dialog:
                with ui.card().classes('p-4'):
                    ui.label('Create New Document Set').classes('text-h6 mb-4')
                    self.new_set_name = ui.input('Set Name').classes('w-full')
                    self.new_set_description = ui.textarea('Description').classes('w-full')
                    
                    ui.label('Add Query (Optional)').classes('mt-4')
                    with ui.row().classes('w-full items-end'):
                        query_type_options = [
                            {'label': 'Document Name', 'value': 'name'},
                            {'label': 'Content', 'value': 'content'},
                            {'label': 'File Type', 'value': 'file_type'}
                        ]
                        self.query_type = ui.select(options=query_type_options, label='Query Type').classes('w-1/3')
                        
                        operator_options = [
                            {'label': 'Contains', 'value': 'contains'},
                            {'label': 'Equals', 'value': 'equals'},
                            {'label': 'Starts With', 'value': 'startswith'},
                            {'label': 'Ends With', 'value': 'endswith'}
                        ]
                        self.query_operator = ui.select(options=operator_options, label='Operator').classes('w-1/3')
                        self.query_value = ui.input('Value').classes('w-1/3')
                    
                    with ui.row().classes('w-full justify-end mt-4'):
                        ui.button('Cancel', on_click=lambda: self.create_set_dialog.close()).props('flat')
                        ui.button('Create', on_click=self.create_set).props('color=primary')
            
            self.add_to_set_dialog = ui.dialog()
            with self.add_to_set_dialog:
                with ui.card().classes('p-4'):
                    ui.label('Add to Set').classes('text-h6 mb-4')
                    self.set_selector = ui.select(
                        options=self.get_sets_options(), 
                        label='Select Sets',
                        multiple=True
                    ).classes('w-full')
                    self.set_selection_summary = ui.label('No sets selected').classes('text-sm text-gray-600 mt-1')
                    self.set_selector.on('update:model-value', self.update_set_selection_summary)
                    with ui.row().classes('w-full justify-end mt-4'):
                        ui.button('Cancel', on_click=lambda: self.add_to_set_dialog.close()).props('flat')
                        ui.button('Add', on_click=self.add_to_set).props('color=primary')
            
            self.manage_sets_dialog = ui.dialog()
            with self.manage_sets_dialog:
                with ui.card().classes('p-4 min-w-[600px]'):
                    ui.label('Manage Document Sets').classes('text-h6 mb-4')
                    self.sets_table = ui.table(
                        columns=[
                            {'name': 'name', 'label': 'Set Name', 'field': 'name'},
                            {'name': 'description', 'label': 'Description', 'field': 'description'},
                            {'name': 'doc_count', 'label': 'Documents', 'field': 'doc_count'},
                            {'name': 'actions', 'label': 'Actions', 'field': 'actions'},
                        ],
                        rows=self.get_sets(),
                        pagination=5,
                    ).classes('w-full')
                    
                    actions_template = '''
                        <q-td key="actions" :props="props">
                            <q-btn flat color="primary" label="View" @click="$emit('view', props.row)" />
                        </q-td>
                    '''
                    self.sets_table.add_slot('body-cell-actions', actions_template)
                    self.sets_table.on('view', lambda e: self.view_set(e.args['id']))

    def update_filter_options(self):
        """Update the options in the filter dropdowns"""
        try:
            db = get_db()
            
            # Get unique file types
            file_types = db.query(Document.file_type).distinct().all()
            type_options = [{'label': 'All Types', 'value': 'all'}]
            type_options.extend([
                {'label': ft[0], 'value': ft[0]} for ft in file_types if ft[0]
            ])
            self.type_filter.options = type_options
            
            # Get unique sets
            sets = db.query(DocumentSet.name).distinct().all()
            set_options = [{'label': 'All Sets', 'value': 'all'}]
            set_options.extend([
                {'label': s[0], 'value': s[0]} for s in sets if s[0]
            ])
            self.set_filter.options = set_options
            
            # Reset values to 'all' after updating options
            self.type_filter.value = 'all'
            self.set_filter.value = 'all'
            
        except Exception as ex:
            ui.notify(f'Error updating filter options: {str(ex)}', type='negative')

    def get_documents(self, search_term: str = '') -> list:
        try:
            db = get_db()
            query = db.query(Document)
            
            # Apply search filter
            if search_term:
                if self.search_column.value == 'all':
                    query = query.filter(
                        Document.name.ilike(f'%{search_term}%') |
                        Document.file_type.ilike(f'%{search_term}%')
                    )
                elif self.search_column.value == 'name':
                    query = query.filter(Document.name.ilike(f'%{search_term}%'))
                elif self.search_column.value == 'file_type':
                    query = query.filter(Document.file_type.ilike(f'%{search_term}%'))
            
            # Apply file type filter
            if self.type_filter.value and self.type_filter.value != 'all':
                query = query.filter(Document.file_type == self.type_filter.value)
            
            # Apply set filter
            if self.set_filter.value and self.set_filter.value != 'all':
                query = query.join(Document.sets).filter(DocumentSet.name == self.set_filter.value)
            
            documents = query.all()
            
            result = []
            for doc in documents:
                doc_data = {
                    'id': doc.id,
                    'name': doc.name,
                    'file_type': doc.file_type,
                    'uploaded_at': format_datetime(doc.uploaded_at),
                    'content': doc.content,
                    'sets': ', '.join(s.name for s in doc.sets)
                }
                result.append(doc_data)
            return result
        except Exception as ex:
            ui.notify(f'Error getting documents: {str(ex)}', type='negative')
            return []

    def handle_preview(self, e):
        """Handle preview button click"""
        try:
            ui.notify('Preview clicked')  # Debug notification
            print("Preview event:", e)  # Debug print
            print("Preview event args:", e.args)  # Debug print
            
            if hasattr(e, 'args'):
                row_data = e.args
                print("Row data:", row_data)  # Debug print
                
                if isinstance(row_data, dict):
                    print("Opening preview for:", row_data.get('name'))  # Debug print
                    self.preview_title.text = f'Preview: {row_data.get("name", "")}'
                    self.preview_content.value = row_data.get('content', '')
                    self.preview_dialog.open()
                else:
                    ui.notify('Invalid document data format', type='warning')
            else:
                ui.notify('No event data received', type='warning')
        except Exception as ex:
            print("Error in handle_preview:", ex)  # Debug print
            ui.notify(f'Error showing preview: {str(ex)}', type='negative')

    def update_documents(self):
        try:
            self.documents_table.rows = self.get_documents(self.search_input.value)
        except Exception as ex:
            ui.notify(f'Error updating documents: {str(ex)}', type='negative')

    def show_create_set_dialog(self):
        self.create_set_dialog.open()

    def show_add_to_set_dialog(self):
        try:
            if not self.selected_documents:
                ui.notify('Please select documents first', type='warning')
                return
            self.set_selector.options = self.get_sets_options()
            self.add_to_set_dialog.open()
        except Exception as ex:
            ui.notify(f'Error showing dialog: {str(ex)}', type='negative')

    def show_manage_sets_dialog(self):
        self.sets_table.rows = self.get_sets()
        self.manage_sets_dialog.open()

    def get_sets_options(self) -> list:
        db = get_db()
        sets = db.query(DocumentSet).all()
        return [{'label': f"{s.name} ({len(s.documents)} documents)", 'value': s.id} for s in sets]

    def get_sets(self) -> list:
        db = get_db()
        sets = db.query(DocumentSet).all()
        return [{
            'id': s.id,
            'name': s.name,
            'description': s.description,
            'doc_count': len(s.documents),
            'actions': None  
        } for s in sets]

    def create_set(self):
        if not self.new_set_name.value:
            ui.notify('Please enter a set name', type='warning')
            return
        
        db = get_db()
        new_set = DocumentSet(
            name=self.new_set_name.value,
            description=self.new_set_description.value
        )
        
        if self.selected_documents:
            documents = db.query(Document).filter(Document.id.in_(self.selected_documents)).all()
            new_set.documents.extend(documents)
        
        if all([self.query_type.value, self.query_operator.value, self.query_value.value]):
            query = DocumentQuery(
                name=f"Auto-query for {self.new_set_name.value}",
                query_type=self.query_type.value,
                operator=self.query_operator.value,
                query_value=self.query_value.value
            )
            new_set.queries.append(query)
        
        db.add(new_set)
        db.commit()
        
        ui.notify('Set created successfully')
        self.create_set_dialog.close()
        self.update_documents()  
    def update_set_selection_summary(self, e):
        """Update the summary of selected sets"""
        if not e.value:
            self.set_selection_summary.text = 'No sets selected'
            return
        
        db = get_db()
        selected_sets = db.query(DocumentSet).filter(DocumentSet.id.in_(e.value)).all()
        set_names = ', '.join(s.name for s in selected_sets)
        self.set_selection_summary.text = f"Selected sets: {set_names}"

    def add_to_set(self):
        if not self.set_selector.value:
            ui.notify('Please select at least one set', type='warning')
            return
        
        db = get_db()
        documents = db.query(Document).filter(Document.id.in_(self.selected_documents)).all()
        
        for set_id in self.set_selector.value:
            doc_set = db.query(DocumentSet).get(set_id)
            if doc_set:
                for doc in documents:
                    if doc not in doc_set.documents:
                        doc_set.documents.append(doc)
        
        db.commit()
        
        ui.notify('Documents added to selected sets successfully')
        self.add_to_set_dialog.close()
        self.update_documents()  

    def view_set(self, set_id):
        db = get_db()
        doc_set = db.query(DocumentSet).get(set_id)
        
        self.selected_documents.clear()
        self.selected_documents.update(d.id for d in doc_set.documents)
        
        self.update_documents()
        self.manage_sets_dialog.close()
        ui.notify(f'Viewing documents in set: {doc_set.name}')

    def get_prompts_options(self) -> list:
        """Get available prompts for the select component"""
        db = get_db()
        prompts = db.query(Prompt).all()
        return [{'label': p.name, 'value': p.id} for p in prompts]

    def handle_preview_submit(self):
        """Handle the submission of a prompt for preview"""
        try:
            if not self.preview_prompt_select.value:
                ui.notify('Please select a prompt first', type='warning')
                return
            
            db = get_db()
            prompt = db.query(Prompt).get(self.preview_prompt_select.value)
            if not prompt:
                ui.notify('Selected prompt not found', type='negative')
                return
            
            result = f"Prompt: {prompt.content}\n\nDocument Content: {self.preview_content.value}\n\nResult: This is a placeholder result. Implement your actual processing logic here."
            
            self.preview_result.value = result
            ui.notify('Processing complete', type='positive')
            
        except Exception as ex:
            ui.notify(f'Error processing preview: {str(ex)}', type='negative')

    def clear_table_selection(self):
        """Clear the table selection"""
        self.documents_table.selected = []  # Clear the table's selection

    def handle_selection(self, e):
        """Handle selection events from the documents table"""
        try:
            if isinstance(e.args, dict):
                rows = e.args.get('rows', [])
                added = e.args.get('added', False)
                
                for row in rows:
                    if isinstance(row, dict) and 'id' in row:
                        doc_id = row['id']
                        if added:
                            shared_state.update_selection(doc_id, row, True)
                        else:
                            shared_state.update_selection(doc_id, row, False)
        except Exception as ex:
            ui.notify(f'Error in handle_selection: {str(ex)}', type='negative')

class PromptManager:
    def __init__(self):
        self.selected_prompts = set()
        self.current_results = []
        
        with ui.card().classes('w-full'):
            ui.label('Manage Prompts').classes('text-h6')
            
            # Search and filter section
            with ui.row().classes('w-full items-end mb-4'):
                with ui.column().classes('w-1/3 pr-2'):
                    self.search_input = ui.input(label='Search').classes('w-full')
                    self.search_input.on('change', self.update_prompts)
                
                with ui.column().classes('w-1/3 pr-2'):
                    self.search_column = ui.select(
                        options=[
                            {'label': 'All Columns', 'value': 'all'},
                            {'label': 'Name', 'value': 'name'},
                            {'label': 'Content', 'value': 'content'}
                        ],
                        label='Search In'
                    ).classes('w-full')
                    self.search_column.value = 'all'
                    self.search_column.on('change', self.update_prompts)
                
                with ui.column().classes('w-1/3'):
                    self.date_filter = ui.select(
                        options=[
                            {'label': 'All Time', 'value': 'all'},
                            {'label': 'Last 24 Hours', 'value': '24h'},
                            {'label': 'Last 7 Days', 'value': '7d'},
                            {'label': 'Last 30 Days', 'value': '30d'}
                        ],
                        label='Created'
                    ).classes('w-full')
                    self.date_filter.value = 'all'
                    self.date_filter.on('change', self.update_prompts)
            
            # Create prompt form
            with ui.row().classes('w-full mt-4'):
                self.prompt_name = ui.input(label='Prompt Name').classes('w-1/3')
                self.prompt_content = ui.textarea(label='Prompt Content').classes('w-2/3')
                ui.button('Save Prompt', on_click=self.save_prompt).props('color=primary')
            
            # Run section
            with ui.row().classes('w-full mt-4 items-center'):
                self.selected_docs_label = ui.label().classes('mr-4')
                with ui.row().classes('gap-2'):
                    ui.button('Run Selected Prompts', on_click=self.run_prompts).props('color=primary')
                    ui.button('Request Batch Run', on_click=self.show_batch_request_dialog).props('color=secondary')
                
                # Register for selection updates
                shared_state.on_selection_change_callbacks.append(self.update_selection_label)
                # Initial update
                self.update_selection_label()
            
            # Prompts table
            with ui.table(
                columns=[
                    {'name': 'name', 'label': 'Name', 'field': 'name', 'sortable': True},
                    {'name': 'content', 'label': 'Content', 'field': 'content'},
                    {'name': 'created', 'label': 'Created', 'field': 'created_at', 'sortable': True},
                    {'name': 'actions', 'label': 'Actions', 'field': 'actions'},
                ],
                rows=self.get_prompts(),
                pagination=10,
                row_key='id',
                selection='multiple'
            ).classes('w-full') as self.prompts_table:
                actions_template = '''
                    <q-td key="actions" :props="props">
                        <q-btn flat color="secondary" label="Feedback" @click="$emit('feedback', props.row)" />
                    </q-td>
                '''
                self.prompts_table.add_slot('body-cell-actions', actions_template)
                self.prompts_table.on('edit', self.show_edit_dialog)
                self.prompts_table.on('selection', self.handle_selection)
            
            # Results section with filters
            with ui.card().classes('w-full mt-6'):
                ui.label('Results').classes('text-h6 mb-4')
                
                # Results filters
                with ui.row().classes('w-full items-end mb-4'):
                    with ui.column().classes('w-1/4 pr-2'):
                        self.results_date_filter = ui.select(
                            options=[
                                {'label': 'Today', 'value': 'today'},
                                {'label': 'Last 24 Hours', 'value': '24h'},
                                {'label': 'Last 7 Days', 'value': '7d'},
                                {'label': 'Last 30 Days', 'value': '30d'},
                                {'label': 'All Time', 'value': 'all'}
                            ],
                            label='Date Range'
                        ).classes('w-full')
                        self.results_date_filter.value = 'today'  # Default to today
                        self.results_date_filter.on('change', self.update_results)
                    
                    with ui.column().classes('w-1/4 pr-2'):
                        self.results_batch_filter = ui.select(
                            options=[{'label': 'All Batch Runs', 'value': None}] + self.get_batch_runs_options(),
                            label='Batch Run'
                        ).classes('w-full')
                        self.results_batch_filter.on('change', self.update_results)
                    
                    with ui.column().classes('w-1/4 pr-2'):
                        self.results_doc_filter = ui.select(
                            options=[{'label': 'All Documents', 'value': None}] + self.get_documents_options(),
                            label='Document'
                        ).classes('w-full')
                        self.results_doc_filter.on('change', self.update_results)
                    
                    with ui.column().classes('w-1/4'):
                        self.results_prompt_filter = ui.select(
                            options=[{'label': 'All Prompts', 'value': None}] + self.get_prompts_options_for_filter(),
                            label='Prompt'
                        ).classes('w-full')
                        self.results_prompt_filter.on('change', self.update_results)
                
                # Results table
                self.results_table = ui.table(
                    columns=[
                        {'name': 'expand', 'label': '', 'field': 'expand', 'style': 'width: 50px;'},
                        {'name': 'batch_run', 'label': 'Batch Run', 'field': 'batch_run', 'sortable': True, 'style': 'width: 150px;'},
                        {'name': 'document', 'label': 'Document', 'field': 'document', 'sortable': True, 'style': 'width: 150px;'},
                        {'name': 'prompt', 'label': 'Prompt', 'field': 'prompt', 'sortable': True, 'style': 'width: 150px;'},
                        {'name': 'response', 'label': 'Response', 'field': 'response', 'style': 'width: 200px; max-width: 200px; word-wrap: break-word; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'},
                        {'name': 'created', 'label': 'Created', 'field': 'created_at', 'sortable': True, 'style': 'width: 120px;'},
                        {'name': 'avg_rating', 'label': 'Avg Rating', 'field': 'avg_rating', 'style': 'width: 100px;'},
                        {'name': 'feedback_count', 'label': 'Feedback Count', 'field': 'feedback_count', 'style': 'width: 120px;'},
                        {'name': 'actions', 'label': 'Actions', 'field': 'actions', 'style': 'width: 150px;'},
                    ],
                    rows=self.get_results_data(),
                    pagination=10,
                    row_key='id',
                    selection='none'
                ).classes('w-full')
                
                expand_template = '''
                    <q-td key="expand" :props="props">
                        <q-btn flat :icon="props.row.expanded ? 'expand_less' : 'expand_more'" 
                               @click="$emit('expand', props.row)" />
                    </q-td>
                '''
                self.results_table.add_slot('body-cell-expand', expand_template)
                
                response_template = '''
                    <q-td key="response" :props="props">
                        <q-tooltip v-if="props.row.full_response && props.row.full_response.length > 100">
                            {{ props.row.full_response }}
                        </q-tooltip>
                        <div style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            {{ props.row.response }}
                        </div>
                    </q-td>
                '''
                self.results_table.add_slot('body-cell-response', response_template)
                
                actions_template = '''
                    <q-td key="actions" :props="props">
                        <q-btn flat color="secondary" label="Feedback" @click="$emit('feedback', props.row)" />
                    </q-td>
                '''
                self.results_table.add_slot('body-cell-actions', actions_template)
                self.results_table.on('feedback', self.show_feedback_dialog)
                self.results_table.on('expand', self.handle_row_expand)

            # Save dialog
            self.save_dialog = ui.dialog()
            with self.save_dialog:
                with ui.card().classes('p-4'):
                    ui.label('Save Results').classes('text-h6 mb-4')
                    self.save_run_name = ui.input(label='Run Name').classes('w-full mb-4')
                    with ui.row().classes('w-full justify-end'):
                        ui.button('Cancel', on_click=lambda: self.save_dialog.close()).props('flat')
                        ui.button('Save', on_click=self.save_results).props('color=primary')

            # Edit dialog
            self.edit_dialog = ui.dialog()
            with self.edit_dialog:
                with ui.card().classes('p-4'):
                    ui.label('Edit Prompt').classes('text-h6 mb-4')
                    self.edit_prompt_id = None
                    self.edit_name = ui.input(label='Prompt Name').classes('w-full mb-4')
                    self.edit_content = ui.textarea(label='Prompt Content').classes('w-full min-h-[300px] mb-4')
                    with ui.row().classes('w-full justify-end'):
                        ui.button('Cancel', on_click=lambda: self.edit_dialog.close()).props('flat')
                        ui.button('Save Changes', on_click=self.save_edit).props('color=primary')

            # Batch Request Dialog
            self.batch_request_dialog = ui.dialog()
            with self.batch_request_dialog:
                with ui.card().classes('p-4 min-w-[600px]'):
                    ui.label('Request Batch Run').classes('text-h6 mb-4')
                    
                    self.batch_name = ui.input(label='Batch Run Name').classes('w-full mb-4')
                    self.batch_description = ui.textarea(label='Description/Purpose').classes('w-full mb-4')
                    
                    ui.label('Select Document Sets').classes('text-subtitle1 mb-2')
                    self.doc_set_selection = ui.select(
                        label='Document Sets',
                        options=self.get_document_sets(),
                        multiple=True
                    ).classes('w-full mb-4')
                    self.doc_summary = ui.label('No sets selected').classes('text-sm text-gray-600 mb-4')
                    self.doc_set_selection.on('update:model-value', self.update_doc_summary)
                    
                    ui.label('Select Prompts').classes('text-subtitle1 mb-2')
                    self.prompt_selection = ui.select(
                        label='Prompts',
                        options=self.get_prompts_options(),
                        multiple=True
                    ).classes('w-full mb-4')
                    self.prompt_summary = ui.label('No prompts selected').classes('text-sm text-gray-600 mb-4')
                    self.prompt_selection.on('update:model-value', self.update_prompt_summary)
                    
                    with ui.row().classes('w-full justify-end'):
                        ui.button('Cancel', on_click=lambda: self.batch_request_dialog.close()).props('flat')
                        ui.button('Submit Request', on_click=self.submit_batch_request).props('color=primary')

            # Result details dialog
            self.result_details_dialog = ui.dialog()
            with self.result_details_dialog:
                with ui.card().classes('p-4'):
                    ui.label('Result Details').classes('text-h6 mb-4')
                    self.result_details_content = ui.textarea(
                        label='Response',
                        value=''
                    ).props('disable').classes('w-full min-w-[600px] min-h-[300px]')
                    
                    ui.label('Feedback History').classes('text-h6 mt-4 mb-2')
                    self.feedback_details = ui.column().classes('w-full')
                    
                    with ui.row().classes('w-full justify-end mt-4'):
                        ui.button('Close', on_click=lambda: self.result_details_dialog.close()).props('flat')

            # Feedback dialog
            self.feedback_dialog = ui.dialog()
            with self.feedback_dialog:
                with ui.card().classes('p-4'):
                    ui.label('Add Feedback').classes('text-h6 mb-4')
                    self.current_result_id = None
                    
                    with ui.column().classes('w-full'):
                        self.rating_select = ui.select(
                            options=[
                                {'label': '⭐ Poor', 'value': 1},
                                {'label': '⭐⭐ Fair', 'value': 2},
                                {'label': '⭐⭐⭐ Good', 'value': 3},
                                {'label': '⭐⭐⭐⭐ Very Good', 'value': 4},
                                {'label': '⭐⭐⭐⭐⭐ Excellent', 'value': 5},
                            ],
                            label='Rating'
                        ).classes('w-full')
                        
                        self.feedback_comment = ui.textarea('Comment (optional)').classes('w-full')
                        
                        with ui.row().classes('w-full justify-end mt-4'):
                            ui.button('Cancel', on_click=lambda: self.feedback_dialog.close()).props('flat')
                            ui.button('Submit', on_click=self.submit_feedback).props('color=primary')

    def get_document_sets(self):
        """Get available document sets for selection"""
        db = get_db()
        sets = db.query(DocumentSet).all()
        return [{'label': f"{s.name} ({len(s.documents)} documents)", 'value': s.id} for s in sets]

    def get_prompts_options(self):
        """Get available prompts for selection"""
        db = get_db()
        prompts = db.query(Prompt).all()
        return [{'label': p.name, 'value': p.id} for p in prompts]

    def update_doc_summary(self, e):
        """Update document sets selection summary"""
        if not e.value:
            self.doc_summary.text = 'No sets selected'
            return
        
        db = get_db()
        selected_sets = db.query(DocumentSet).filter(DocumentSet.id.in_(e.value)).all()
        total_docs = sum(len(s.documents) for s in selected_sets)
        set_names = ', '.join(s.name for s in selected_sets)
        self.doc_summary.text = f"Selected {total_docs} documents from sets: {set_names}"

    def update_prompt_summary(self, e):
        """Update prompts selection summary"""
        if not e.value:
            self.prompt_summary.text = 'No prompts selected'
            return
        
        db = get_db()
        selected_prompts = db.query(Prompt).filter(Prompt.id.in_(e.value)).all()
        prompt_names = ', '.join(p.name for p in selected_prompts)
        self.prompt_summary.text = f"Selected prompts: {prompt_names}"

    def show_batch_request_dialog(self):
        """Show the batch request dialog"""
        self.doc_set_selection.options = self.get_document_sets()
        self.prompt_selection.options = self.get_prompts_options()
        self.batch_request_dialog.open()

    def submit_batch_request(self):
        """Submit a new batch run request"""
        if not self.batch_name.value:
            ui.notify('Please enter a batch run name', type='warning')
            return
        
        if not self.doc_set_selection.value or not self.prompt_selection.value:
            ui.notify('Please select both document sets and prompts', type='warning')
            return
        
        try:
            db = get_db()
            
            batch_run = BatchRun(
                name=self.batch_name.value,
                description=self.batch_description.value,
                status='pending_approval',
                scheduled_for=None  # Will be set by admin during approval
            )
            db.add(batch_run)
            
            # Add documents from selected sets
            doc_sets = db.query(DocumentSet).filter(DocumentSet.id.in_(self.doc_set_selection.value)).all()
            for doc_set in doc_sets:
                batch_run.documents.extend(doc_set.documents)
            
            # Add selected prompts
            prompts = db.query(Prompt).filter(Prompt.id.in_(self.prompt_selection.value)).all()
            batch_run.prompts.extend(prompts)
            
            db.commit()
            ui.notify('Batch run request submitted successfully!')
            
            self.batch_request_dialog.close()
            self.batch_name.value = ''
            self.batch_description.value = ''
            self.doc_set_selection.value = []
            self.prompt_selection.value = []
            
        except Exception as ex:
            ui.notify(f'Error submitting batch run request: {str(ex)}', type='negative')

    def run_prompts(self):
        if not shared_state.get_selected_count():
            ui.notify('Please select at least one document', type='warning')
            return
        
        if not self.selected_prompts:
            ui.notify('Please select at least one prompt', type='warning')
            return
        
        try:
            # Clear previous results
            self.current_results = []  # Clear stored results
            
            db = get_db()
            prompts = db.query(Prompt).filter(Prompt.id.in_(self.selected_prompts)).all()
            
            # Create a temporary batch run for these results
            temp_batch_run = BatchRun(
                name=f"Manual Run - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                status='completed',
                completed_at=datetime.utcnow()
            )
            db.add(temp_batch_run)
            
            # Add documents and prompts to the batch run
            for doc_id in shared_state.selected_documents:
                doc = db.query(Document).get(doc_id)
                if doc:
                    temp_batch_run.documents.append(doc)
            
            for prompt in prompts:
                temp_batch_run.prompts.append(prompt)
            
            # Process each document with each prompt
            for doc_id in shared_state.selected_documents:
                doc_details = shared_state.selected_document_details[doc_id]
                doc = db.query(Document).get(doc_id)
                
                for prompt in prompts:
                    # For now, use placeholder text
                    result_text = f"Processed document '{doc_details['name']}' with prompt '{prompt.name}'\n"
                    result_text += "This is a placeholder result. In a real implementation, this would be the output of your processing logic."
                    
                    # Create result in database
                    result = Result(
                        document=doc,
                        prompt=prompt,
                        batch_run=temp_batch_run,
                        response=result_text
                    )
                    db.add(result)
                    
                    # Store result for later saving
                    result_data = {
                        'document_id': doc_id,
                        'document_name': doc_details['name'],
                        'prompt_id': prompt.id,
                        'prompt_name': prompt.name,
                        'result': result_text
                    }
                    self.current_results.append(result_data)
            
            db.commit()
            
            # Update the results table to show the new results
            self.update_results()
            
            ui.notify('Processing complete! Results have been saved and are now visible in the table.', type='positive')
            
        except Exception as ex:
            ui.notify(f'Error running prompts: {str(ex)}', type='negative')

    def show_save_dialog(self, results=None):
        """Show save dialog for specified results or all results if none specified"""
        self.results_to_save = results or self.current_results
        self.save_run_name.value = ''
        self.save_dialog.open()

    def save_results(self):
        """Save the selected results to the database"""
        if not self.save_run_name.value:
            ui.notify('Please enter a run name', type='warning')
            return
        
        try:
            db = get_db()
            
            # Create a new batch run
            batch_run = BatchRun(
                name=self.save_run_name.value,
                status='completed',
                completed_at=datetime.utcnow()
            )
            db.add(batch_run)
            
            # Add results
            for result_data in self.results_to_save:
                result = Result(
                    document_id=result_data['document_id'],
                    prompt_id=result_data['prompt_id'],
                    batch_run=batch_run,
                    response=result_data['result']
                )
                db.add(result)
            
            db.commit()
            ui.notify('Results saved successfully!', type='positive')
            self.save_dialog.close()
            
            # Update the results table
            self.update_results()
            
        except Exception as ex:
            ui.notify(f'Error saving results: {str(ex)}', type='negative')

    def handle_selection(self, e):
        try:
            if isinstance(e.args, dict):
                rows = e.args.get('rows', [])
                added = e.args.get('added', False)
                
                for row in rows:
                    if isinstance(row, dict) and 'id' in row:
                        if added:
                            self.selected_prompts.add(row['id'])
                        else:
                            self.selected_prompts.discard(row['id'])
        except Exception as ex:
            ui.notify(f'Error in handle_selection: {str(ex)}', type='negative')

    def get_prompts(self, search_term: str = '') -> list:
        try:
            db = get_db()
            query = db.query(Prompt)
            
            # Apply search filter
            if search_term:
                if self.search_column.value == 'all':
                    query = query.filter(
                        Prompt.name.ilike(f'%{search_term}%') |
                        Prompt.content.ilike(f'%{search_term}%')
                    )
                elif self.search_column.value == 'name':
                    query = query.filter(Prompt.name.ilike(f'%{search_term}%'))
                elif self.search_column.value == 'content':
                    query = query.filter(Prompt.content.ilike(f'%{search_term}%'))
            
            # Apply date filter
            if self.date_filter.value and self.date_filter.value != 'all':
                now = datetime.utcnow()
                if self.date_filter.value == '24h':
                    cutoff = now - timedelta(hours=24)
                elif self.date_filter.value == '7d':
                    cutoff = now - timedelta(days=7)
                elif self.date_filter.value == '30d':
                    cutoff = now - timedelta(days=30)
                query = query.filter(Prompt.created_at >= cutoff)
            
            prompts = query.all()
            return [{
                'id': p.id,
                'name': p.name,
                'content': p.content,
                'created_at': format_datetime(p.created_at),
            } for p in prompts]
        except Exception as ex:
            ui.notify(f'Error getting prompts: {str(ex)}', type='negative')
            return []

    def show_edit_dialog(self, row_data):
        """Opens the edit dialog with the prompt data"""
        try:
            if isinstance(row_data, dict):
                self.edit_prompt_id = row_data.get('id')
                self.edit_name.value = row_data.get('name', '')
                self.edit_content.value = row_data.get('content', '')
                self.edit_dialog.open()
            else:
                ui.notify('Invalid row data', type='negative')
        except Exception as ex:
            ui.notify(f'Error opening edit dialog: {str(ex)}', type='negative')

    def save_edit(self):
        if not self.edit_name.value or not self.edit_content.value:
            ui.notify('Please enter both name and content', type='warning')
            return
        
        try:
            db = get_db()
            prompt = db.query(Prompt).get(self.edit_prompt_id)
            if prompt:
                prompt.name = self.edit_name.value
                prompt.content = self.edit_content.value
                db.commit()
                ui.notify('Prompt updated successfully!', type='positive')
                self.edit_dialog.close()
                self.update_prompts()
            else:
                ui.notify('Prompt not found', type='negative')
        except Exception as ex:
            ui.notify(f'Error updating prompt: {str(ex)}', type='negative')

    def update_prompts(self):
        try:
            self.prompts_table.rows = self.get_prompts(self.search_input.value)
        except Exception as ex:
            ui.notify(f'Error updating prompts: {str(ex)}', type='negative')

    def save_prompt(self):
        if not self.prompt_name.value or not self.prompt_content.value:
            ui.notify('Please enter both name and content', type='warning')
            return
        
        db = get_db()
        prompt = Prompt(
            name=self.prompt_name.value,
            content=self.prompt_content.value
        )
        db.add(prompt)
        db.commit()
        ui.notify('Prompt saved successfully!')
        
        # Clear form
        self.prompt_name.value = ''
        self.prompt_content.value = ''
        
        # Update prompts table
        self.update_prompts()

    def update_selection_label(self):
        """Update the selected documents label"""
        count = shared_state.get_selected_count()
        if count > 0:
            names = shared_state.get_selected_names()
            self.selected_docs_label.text = f'{count} document(s) selected: {names}'
        else:
            self.selected_docs_label.text = 'No documents selected'

    def get_batch_runs_options(self):
        """Get available batch runs for filtering"""
        db = get_db()
        runs = db.query(BatchRun).all()
        return [{'label': f"{r.name} ({r.status})", 'value': r.id} for r in runs]

    def get_documents_options(self):
        """Get available documents for filtering"""
        db = get_db()
        docs = db.query(Document).all()
        return [{'label': d.name, 'value': d.id} for d in docs]

    def get_prompts_options_for_filter(self):
        """Get available prompts for filtering"""
        db = get_db()
        prompts = db.query(Prompt).all()
        return [{'label': p.name, 'value': p.id} for p in prompts]

    def get_results_data(self):
        """Get results data based on current filters"""
        try:
            db = get_db()
            query = db.query(Result)
            
            # Apply date filter
            if self.results_date_filter.value and self.results_date_filter.value != 'all':
                now = datetime.utcnow()
                if self.results_date_filter.value == 'today':
                    cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
                elif self.results_date_filter.value == '24h':
                    cutoff = now - timedelta(hours=24)
                elif self.results_date_filter.value == '7d':
                    cutoff = now - timedelta(days=7)
                elif self.results_date_filter.value == '30d':
                    cutoff = now - timedelta(days=30)
                query = query.filter(Result.created_at >= cutoff)
            
            # Apply batch filter
            if self.results_batch_filter.value:
                query = query.filter(Result.batch_run_id == self.results_batch_filter.value)
            
            # Apply document filter
            if self.results_doc_filter.value:
                query = query.filter(Result.document_id == self.results_doc_filter.value)
            
            # Apply prompt filter
            if self.results_prompt_filter.value:
                query = query.filter(Result.prompt_id == self.results_prompt_filter.value)
            
            # Order by most recent first
            query = query.order_by(Result.created_at.desc())
            
            results = query.all()
            return [{
                'id': r.id,
                'expand': None,  # Rendered by slot
                'batch_run': r.batch_run.name if r.batch_run else 'N/A',
                'document': r.document.name if r.document else 'N/A',
                'prompt': r.prompt.name if r.prompt else 'N/A',
                'response': r.response[:100] + '...' if len(r.response) > 100 else r.response,  # Truncate to 100 chars
                'full_response': r.response,  # Store full response for expand functionality
                'created_at': format_datetime(r.created_at),
                'avg_rating': self.calculate_average_rating(r.feedback),
                'feedback_count': len(r.feedback) if r.feedback else 0,
                'actions': None  # Rendered by slot
            } for r in results]
        except Exception as ex:
            ui.notify(f'Error getting results data: {str(ex)}', type='negative')
            return []

    def calculate_average_rating(self, feedback_list):
        """Calculate the average rating from a list of feedback"""
        if not feedback_list:
            return 'N/A'
        
        total_rating = sum(f.rating for f in feedback_list)
        return f"{total_rating / len(feedback_list):.2f}" if len(feedback_list) > 0 else 'N/A'

    def show_result_details(self, row):
        """Show result details in a dialog"""
        try:
            # Use the full response from the row data
            full_response = row.get('full_response', row.get('response', ''))
            
            # Show the full result text
            self.result_details_content.value = full_response
            
            # Get feedback from database
            db = get_db()
            result = db.query(Result).get(row['id'])
            
            if result:
                # Clear and populate feedback details
                self.feedback_details.clear()
                with self.feedback_details:
                    if result.feedback:
                        for fb in sorted(result.feedback, key=lambda x: x.created_at, reverse=True):
                            with ui.card().classes('w-full mb-2'):
                                with ui.row().classes('w-full items-center justify-between'):
                                    stars = '⭐' * fb.rating
                                    ui.label(f"{stars} ({fb.rating}/5)").classes('text-subtitle1')
                                    ui.label(f"Added: {format_datetime(fb.created_at)}").classes('text-sm text-gray-600')
                                if fb.comment:
                                    ui.label(fb.comment).classes('text-sm mt-1')
                    else:
                        ui.label('No feedback yet').classes('text-sm text-gray-600')
                
                self.result_details_dialog.open()
            else:
                ui.notify('Result not found', type='negative')
        except Exception as ex:
            ui.notify(f'Error showing result details: {str(ex)}', type='negative')

    def update_results(self):
        """Update the results table based on current filters"""
        batch_id = self.results_batch_filter.value
        doc_id = self.results_doc_filter.value
        prompt_id = self.results_prompt_filter.value
        min_rating = self.rating_filter.value
        
        # Get filtered results
        results = self.get_results(batch_id, doc_id, prompt_id, min_rating)
        
        # Update the table
        self.results_table.rows = results
        
        # Update stats
        count = len(results)
        self.stats_label.text = f'Showing {count} result{"s" if count != 1 else ""}'

    def show_feedback_dialog(self, row):
        """Show feedback dialog for a result"""
        self.current_result_id = row['id']
        self.rating_select.value = None
        self.feedback_comment.value = ''
        self.feedback_dialog.open()

    def submit_feedback(self):
        """Submit feedback for a result"""
        if not self.rating_select.value:
            ui.notify('Please select a rating', type='warning')
            return
        
        try:
            db = get_db()
            feedback = Feedback(
                result_id=self.current_result_id,
                rating=self.rating_select.value,
                comment=self.feedback_comment.value
            )
            db.add(feedback)
            db.commit()
            
            ui.notify('Feedback submitted successfully', type='positive')
            self.feedback_dialog.close()
            self.update_results()
            
        except Exception as ex:
            ui.notify(f'Error submitting feedback: {str(ex)}', type='negative')

    def handle_row_expand(self, e):
        """Handle row expand event"""
        try:
            if isinstance(e.args, dict):
                row_data = e.args
                self.show_result_details(row_data)
        except Exception as ex:
            ui.notify(f'Error handling row expand: {str(ex)}', type='negative')

class BatchRunScheduler:
    def __init__(self):
        with ui.card().classes('w-full'):
            ui.label('Review Batch Run Requests').classes('text-h6')
            
            # Filter section
            with ui.row().classes('w-full items-end mb-4'):
                self.status_filter = ui.select(
                    options=[
                        {'label': 'All Statuses', 'value': 'all'},
                        {'label': 'Pending Approval', 'value': 'pending_approval'},
                        {'label': 'Approved', 'value': 'approved'},
                        {'label': 'Rejected', 'value': 'rejected'},
                        {'label': 'Running', 'value': 'running'},
                        {'label': 'Completed', 'value': 'completed'},
                        {'label': 'Failed', 'value': 'failed'}
                    ],
                    label='Status'
                ).classes('w-1/3')
                self.status_filter.value = 'pending_approval'
                self.status_filter.on('change', self.update_runs)
            
            # Batch runs table
            self.runs_table = ui.table(
                columns=[
                    {'name': 'name', 'label': 'Name', 'field': 'name'},
                    {'name': 'description', 'label': 'Description', 'field': 'description'},
                    {'name': 'status', 'label': 'Status', 'field': 'status'},
                    {'name': 'doc_sets', 'label': 'Document Sets', 'field': 'doc_sets'},
                    {'name': 'prompt_sets', 'label': 'Prompts', 'field': 'prompt_sets'},
                    {'name': 'actions', 'label': 'Actions', 'field': 'actions'},
                ],
                rows=self.get_batch_runs()
            ).classes('w-full')
            
            actions_template = '''
                <q-td key="actions" :props="props">
                    <template v-if="props.row.status === 'pending_approval'">
                        <q-btn flat color="positive" label="Approve" @click="$emit('approve', props.row)" class="q-mr-sm" />
                        <q-btn flat color="negative" label="Reject" @click="$emit('reject', props.row)" />
                    </template>
                    <q-btn flat color="primary" label="View Details" @click="$emit('view', props.row)" />
                </q-td>
            '''
            self.runs_table.add_slot('body-cell-actions', actions_template)
            self.runs_table.on('approve', self.show_approve_dialog)
            self.runs_table.on('reject', self.show_reject_dialog)
            self.runs_table.on('view', self.show_details_dialog)
            
            # Approve Dialog
            self.approve_dialog = ui.dialog()
            with self.approve_dialog:
                with ui.card().classes('p-4'):
                    ui.label('Approve Batch Run').classes('text-h6 mb-4')
                    self.current_run_id = None
                    self.schedule_time = ui.input(label='Schedule Time').props('type=datetime-local').classes('w-full mb-4')
                    with ui.row().classes('w-full justify-end'):
                        ui.button('Cancel', on_click=lambda: self.approve_dialog.close()).props('flat')
                        ui.button('Approve', on_click=self.approve_run).props('color=positive')
            
            # Reject Dialog
            self.reject_dialog = ui.dialog()
            with self.reject_dialog:
                with ui.card().classes('p-4'):
                    ui.label('Reject Batch Run').classes('text-h6 mb-4')
                    self.reject_reason = ui.textarea(label='Reason for Rejection').classes('w-full mb-4')
                    with ui.row().classes('w-full justify-end'):
                        ui.button('Cancel', on_click=lambda: self.reject_dialog.close()).props('flat')
                        ui.button('Reject', on_click=self.reject_run).props('color=negative')
            
            # Details Dialog
            self.details_dialog = ui.dialog()
            with self.details_dialog:
                with ui.card().classes('p-4 min-w-[800px]'):
                    self.details_content = ui.column().classes('w-full')

    def get_batch_runs(self):
        db = get_db()
        query = db.query(BatchRun)
        
        if self.status_filter.value != 'all':
            query = query.filter(BatchRun.status == self.status_filter.value)
        
        runs = query.all()
        return [{
            'id': r.id,
            'name': r.name,
            'description': r.description,
            'status': r.status,
            'doc_sets': self.get_set_names_for_docs(r.documents),
            'prompt_sets': self.get_prompt_names(r.prompts)
        } for r in runs]

    def get_set_names_for_docs(self, documents):
        """Get unique set names for a list of documents"""
        sets = set()
        for doc in documents:
            sets.update(s.name for s in doc.sets)
        return ', '.join(sorted(sets)) if sets else 'No sets'

    def get_prompt_names(self, prompts):
        """Get names of prompts"""
        return ', '.join(p.name for p in prompts) if prompts else 'No prompts'

    def show_approve_dialog(self, row):
        """Show the approve dialog for a batch run"""
        self.current_run_id = row['id']
        self.schedule_time.value = ''
        self.approve_dialog.open()

    def show_reject_dialog(self, row):
        """Show the reject dialog for a batch run"""
        self.current_run_id = row['id']
        self.reject_reason.value = ''
        self.reject_dialog.open()

    def show_details_dialog(self, row):
        """Show detailed information about a batch run"""
        try:
            db = get_db()
            run = db.query(BatchRun).get(row['id'])
            
            self.details_content.clear()
            with self.details_content:
                ui.label(f"Batch Run: {run.name}").classes('text-h6 mb-4')
                
                if run.description:
                    ui.label('Description').classes('text-subtitle1')
                    ui.label(run.description).classes('mb-4')
                
                ui.label('Status').classes('text-subtitle1')
                ui.label(run.status).classes('mb-4')
                
                if run.scheduled_for:
                    ui.label('Scheduled For').classes('text-subtitle1')
                    ui.label(format_datetime(run.scheduled_for)).classes('mb-4')
                
                ui.label('Documents').classes('text-subtitle1')
                with ui.table(
                    columns=[
                        {'name': 'name', 'label': 'Name', 'field': 'name'},
                        {'name': 'sets', 'label': 'Sets', 'field': 'sets'}
                    ],
                    rows=[{
                        'name': doc.name,
                        'sets': ', '.join(s.name for s in doc.sets)
                    } for doc in run.documents]
                ).classes('w-full mb-4'): pass
                
                ui.label('Prompts').classes('text-subtitle1')
                with ui.table(
                    columns=[
                        {'name': 'name', 'label': 'Name', 'field': 'name'},
                        {'name': 'content', 'label': 'Content', 'field': 'content'}
                    ],
                    rows=[{
                        'name': prompt.name,
                        'content': prompt.content
                    } for prompt in run.prompts]
                ).classes('w-full'): pass
            
            self.details_dialog.open()
        except Exception as ex:
            ui.notify(f'Error showing details: {str(ex)}', type='negative')

    def approve_run(self):
        """Approve a batch run request"""
        if not self.schedule_time.value:
            ui.notify('Please select a schedule time', type='warning')
            return
        
        try:
            db = get_db()
            run = db.query(BatchRun).get(self.current_run_id)
            
            if run:
                run.status = 'approved'
                run.scheduled_for = datetime.fromisoformat(self.schedule_time.value)
                db.commit()
                
                ui.notify('Batch run approved successfully!')
                self.approve_dialog.close()
                self.update_runs()
            else:
                ui.notify('Batch run not found', type='negative')
        except Exception as ex:
            ui.notify(f'Error approving batch run: {str(ex)}', type='negative')

    def reject_run(self):
        """Reject a batch run request"""
        if not self.reject_reason.value:
            ui.notify('Please provide a reason for rejection', type='warning')
            return
        
        try:
            db = get_db()
            run = db.query(BatchRun).get(self.current_run_id)
            
            if run:
                run.status = 'rejected'
                run.rejection_reason = self.reject_reason.value
                db.commit()
                
                ui.notify('Batch run rejected')
                self.reject_dialog.close()
                self.update_runs()
            else:
                ui.notify('Batch run not found', type='negative')
        except Exception as ex:
            ui.notify(f'Error rejecting batch run: {str(ex)}', type='negative')

    def update_runs(self):
        """Update the batch runs table"""
        self.runs_table.rows = self.get_batch_runs()

class ResultsViewer:
    def __init__(self):
        with ui.card().classes('w-full'):
            ui.label('View Results').classes('text-h6')
            
            with ui.row().classes('w-full items-end'):
                with ui.column().classes('w-1/4 pr-2'):
                    with ui.row().classes('w-full items-end'):
                        self.batch_filter = ui.select(
                            options=[{'label': 'All Batch Runs', 'value': None}] + self.get_batch_runs(),
                            label='Batch Run'
                        ).classes('w-full')
                        self.batch_filter.on('update:model-value', self.update_results)
                
                with ui.column().classes('w-1/4 pr-2'):
                    with ui.row().classes('w-full items-end'):
                        self.doc_filter = ui.select(
                            options=[{'label': 'All Documents', 'value': None}] + self.get_documents(),
                            label='Document'
                        ).classes('w-full')
                        self.doc_filter.on('update:model-value', self.update_results)
                
                with ui.column().classes('w-1/4 pr-2'):
                    with ui.row().classes('w-full items-end'):
                        self.prompt_filter = ui.select(
                            options=[{'label': 'All Prompts', 'value': None}] + self.get_prompts(),
                            label='Prompt'
                        ).classes('w-full')
                        self.prompt_filter.on('update:model-value', self.update_results)
                
                with ui.column().classes('w-1/4'):
                    with ui.row().classes('w-full items-end'):
                        self.rating_filter = ui.select(
                            options=[
                                {'label': 'Any Rating', 'value': None},
                                {'label': '⭐ 1+ Stars', 'value': 1},
                                {'label': '⭐⭐ 2+ Stars', 'value': 2},
                                {'label': '⭐⭐⭐ 3+ Stars', 'value': 3},
                                {'label': '⭐⭐⭐⭐ 4+ Stars', 'value': 4},
                                {'label': '⭐⭐⭐⭐⭐ 5 Stars', 'value': 5},
                            ],
                            label='Minimum Rating'
                        ).classes('w-full')
                        self.rating_filter.on('update:model-value', self.update_results)

            with ui.row().classes('w-full justify-end mt-2'):
                ui.button('Clear All Filters', on_click=self.clear_filters).props('flat color=grey-7')
            
            with ui.row().classes('w-full mt-4'):
                self.stats_label = ui.label('Showing all results').classes('text-sm text-gray-600')
            
            self.results_table = ui.table(
                columns=[
                    {'name': 'expand', 'label': '', 'field': 'expand', 'style': 'width: 50px;'},
                    {'name': 'batch_run', 'label': 'Batch Run', 'field': 'batch_run', 'sortable': True, 'style': 'width: 150px;'},
                    {'name': 'document', 'label': 'Document', 'field': 'document', 'sortable': True, 'style': 'width: 150px;'},
                    {'name': 'prompt', 'label': 'Prompt', 'field': 'prompt', 'sortable': True, 'style': 'width: 150px;'},
                    {'name': 'response', 'label': 'Response', 'field': 'response', 'style': 'width: 200px; max-width: 200px; word-wrap: break-word; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'},
                    {'name': 'created', 'label': 'Created', 'field': 'created_at', 'sortable': True, 'style': 'width: 120px;'},
                    {'name': 'avg_rating', 'label': 'Avg Rating', 'field': 'avg_rating', 'style': 'width: 100px;'},
                    {'name': 'feedback_count', 'label': 'Feedback Count', 'field': 'feedback_count', 'style': 'width: 120px;'},
                    {'name': 'actions', 'label': 'Actions', 'field': 'actions', 'style': 'width: 150px;'},
                ],
                rows=self.get_results(),
                pagination=10,
                row_key='id',
                selection='none'
            ).classes('w-full')
            
            expand_template = '''
                <q-td key="expand" :props="props">
                    <q-btn flat :icon="props.row.expanded ? 'expand_less' : 'expand_more'" 
                           @click="$emit('expand', props.row)" />
                </q-td>
            '''
            self.results_table.add_slot('body-cell-expand', expand_template)
            
            response_template = '''
                <q-td key="response" :props="props">
                    <q-tooltip v-if="props.row.full_response && props.row.full_response.length > 100">
                        {{ props.row.full_response }}
                    </q-tooltip>
                    <div style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                        {{ props.row.response }}
                    </div>
                </q-td>
            '''
            self.results_table.add_slot('body-cell-response', response_template)
            
            actions_template = '''
                <q-td key="actions" :props="props">
                    <q-btn flat color="secondary" label="Feedback" @click="$emit('feedback', props.row)" />
                </q-td>
            '''
            self.results_table.add_slot('body-cell-actions', actions_template)
            self.results_table.on('feedback', self.show_feedback_dialog)
            self.results_table.on('expand', self.handle_row_expand)
            
            self.feedback_dialog = ui.dialog()
            with self.feedback_dialog:
                with ui.card().classes('p-4'):
                    ui.label('Add Feedback').classes('text-h6 mb-4')
                    self.current_result_id = None
                    
                    with ui.column().classes('w-full'):
                        self.rating_select = ui.select(
                            options=[
                                {'label': '⭐ Poor', 'value': 1},
                                {'label': '⭐⭐ Fair', 'value': 2},
                                {'label': '⭐⭐⭐ Good', 'value': 3},
                                {'label': '⭐⭐⭐⭐ Very Good', 'value': 4},
                                {'label': '⭐⭐⭐⭐⭐ Excellent', 'value': 5},
                            ],
                            label='Rating'
                        ).classes('w-full')
                        
                        self.feedback_comment = ui.textarea('Comment (optional)').classes('w-full')
                        
                        with ui.row().classes('w-full justify-end mt-4'):
                            ui.button('Cancel', on_click=lambda: self.feedback_dialog.close()).props('flat')
                            ui.button('Submit', on_click=self.submit_feedback).props('color=primary')

            # Result details dialog
            self.result_details_dialog = ui.dialog()
            with self.result_details_dialog:
                with ui.card().classes('p-4'):
                    ui.label('Result Details').classes('text-h6 mb-4')
                    self.result_details_content = ui.textarea(
                        label='Response',
                        value=''
                    ).props('disable').classes('w-full min-w-[600px] min-h-[300px]')
                    
                    ui.label('Feedback History').classes('text-h6 mt-4 mb-2')
                    self.feedback_details = ui.column().classes('w-full')
                    
                    with ui.row().classes('w-full justify-end mt-4'):
                        ui.button('Close', on_click=lambda: self.result_details_dialog.close()).props('flat')

    def clear_filters(self):
        """Reset all filters to their default values"""
        self.batch_filter.value = None
        self.doc_filter.value = None
        self.prompt_filter.value = None
        self.rating_filter.value = None
        self.update_results()

    def update_results(self):
        """Update the results table based on current filters"""
        batch_id = self.batch_filter.value
        doc_id = self.doc_filter.value
        prompt_id = self.prompt_filter.value
        min_rating = self.rating_filter.value
        
        # Get filtered results
        results = self.get_results(batch_id, doc_id, prompt_id, min_rating)
        
        # Update the table
        self.results_table.rows = results
        
        # Update stats
        count = len(results)
        self.stats_label.text = f'Showing {count} result{"s" if count != 1 else ""}'

    def get_batch_runs(self):
        db = get_db()
        runs = db.query(BatchRun).all()
        return [{'label': f"{r.name} ({r.status})", 'value': r.id} for r in runs]

    def get_documents(self):
        db = get_db()
        docs = db.query(Document).all()
        return [{'label': d.name, 'value': d.id} for d in docs]

    def get_prompts(self):
        db = get_db()
        prompts = db.query(Prompt).all()
        return [{'label': p.name, 'value': p.id} for p in prompts]

    def get_results(self, batch_id: Optional[int] = None, doc_id: Optional[int] = None, 
                   prompt_id: Optional[int] = None, min_rating: Optional[int] = None):
        db = get_db()
        query = db.query(Result)
        
        if batch_id:
            query = query.filter(Result.batch_run_id == batch_id)
        if doc_id:
            query = query.filter(Result.document_id == doc_id)
        if prompt_id:
            query = query.filter(Result.prompt_id == prompt_id)
        
        results = query.all()
        filtered_results = []
        
        for r in results:
            max_rating = max([f.rating for f in r.feedback], default=0) if r.feedback else 0
            
            if min_rating and max_rating < min_rating:
                continue
            
            filtered_results.append({
                'id': r.id,
                'expand': None,  # Rendered by slot
                'batch_run': r.batch_run.name if r.batch_run else 'N/A',
                'document': r.document.name if r.document else 'N/A',
                'prompt': r.prompt.name if r.prompt else 'N/A',
                'response': r.response[:100] + '...' if len(r.response) > 100 else r.response,  # Truncate to 100 chars
                'full_response': r.response,  # Store full response for expand functionality
                'created_at': format_datetime(r.created_at),
                'avg_rating': self.calculate_average_rating(r.feedback),
                'feedback_count': len(r.feedback),
                'actions': None  # Rendered by slot
            })
        
        return filtered_results

    def calculate_average_rating(self, feedback_list):
        """Calculate the average rating from a list of feedback"""
        if not feedback_list:
            return 'N/A'
        
        total_rating = sum(f.rating for f in feedback_list)
        return f"{total_rating / len(feedback_list):.2f}" if len(feedback_list) > 0 else 'N/A'

    def show_result_details(self, row):
        """Show result details in a dialog"""
        try:
            # Use the full response from the row data
            full_response = row.get('full_response', row.get('response', ''))
            
            # Show the full result text
            self.result_details_content.value = full_response
            
            # Get feedback from database
            db = get_db()
            result = db.query(Result).get(row['id'])
            
            if result:
                # Clear and populate feedback details
                self.feedback_details.clear()
                with self.feedback_details:
                    if result.feedback:
                        for fb in sorted(result.feedback, key=lambda x: x.created_at, reverse=True):
                            with ui.card().classes('w-full mb-2'):
                                with ui.row().classes('w-full items-center justify-between'):
                                    stars = '⭐' * fb.rating
                                    ui.label(f"{stars} ({fb.rating}/5)").classes('text-subtitle1')
                                    ui.label(f"Added: {format_datetime(fb.created_at)}").classes('text-sm text-gray-600')
                                if fb.comment:
                                    ui.label(fb.comment).classes('text-sm mt-1')
                    else:
                        ui.label('No feedback yet').classes('text-sm text-gray-600')
                
                self.result_details_dialog.open()
            else:
                ui.notify('Result not found', type='negative')
        except Exception as ex:
            ui.notify(f'Error showing result details: {str(ex)}', type='negative')

    def show_feedback_dialog(self, row):
        """Show feedback dialog for a result"""
        self.current_result_id = row['id']
        self.rating_select.value = None
        self.feedback_comment.value = ''
        self.feedback_dialog.open()

    def submit_feedback(self):
        """Submit feedback for a result"""
        if not self.rating_select.value:
            ui.notify('Please select a rating', type='warning')
            return
        
        try:
            db = get_db()
            feedback = Feedback(
                result_id=self.current_result_id,
                rating=self.rating_select.value,
                comment=self.feedback_comment.value
            )
            db.add(feedback)
            db.commit()
            
            ui.notify('Feedback submitted successfully', type='positive')
            self.feedback_dialog.close()
            self.update_results()
            
        except Exception as ex:
            ui.notify(f'Error submitting feedback: {str(ex)}', type='negative')

    def handle_row_expand(self, e):
        """Handle row expand event"""
        try:
            if isinstance(e.args, dict):
                row_data = e.args
                self.show_result_details(row_data)
        except Exception as ex:
            ui.notify(f'Error handling row expand: {str(ex)}', type='negative')

@ui.page('/')
def main_page():
    # Add the persistent header
    SelectionHeader()
    
    with ui.tabs().classes('w-full') as tabs:
        ui.tab('Documents')
        ui.tab('Prompts')
        ui.tab('Batch Runs')
        ui.tab('Results')

    with ui.tab_panels(tabs, value='Documents').classes('w-full'):
        with ui.tab_panel('Documents'):
            DocumentViewer()
        
        with ui.tab_panel('Prompts'):
            PromptManager()
            
        with ui.tab_panel('Batch Runs'):
            BatchRunScheduler()
            
        with ui.tab_panel('Results'):
            ResultsViewer()

if os.getenv('ENABLE_BATCH_PROCESSOR') == 'true':
    start_background_processor()
    ui.notify('Batch processor started')

ui.run(title='Document Analyzer', port=8080) 