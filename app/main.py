from nicegui import ui, app
from datetime import datetime, timedelta
import os
from sqlalchemy.orm import Session
from models import init_db, Document, Prompt, BatchRun, Result, Feedback, DocumentSet, DocumentQuery, PromptSet, PromptQuery
from typing import List, Optional
import asyncio
from batch_processor import start_background_processor
from sample_data import initialize_sample_data

SessionLocal = init_db()

# Initialize sample data if needed
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

# Utility functions
def format_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")

# UI Components
class DocumentViewer:
    def __init__(self):
        self.selected_documents = set()
        
        with ui.card().classes('w-full'):
            ui.label('Available Documents').classes('text-h6')
            
            # Search and Set Management
            with ui.row().classes('w-full items-center justify-between'):
                with ui.column().classes('w-1/2'):
                    self.search_input = ui.input(label='Search Documents').classes('w-full')
                    self.search_input.on('change', self.update_documents)
                
                with ui.column().classes('w-1/2 flex justify-end'):
                    ui.button('Create New Set', on_click=self.show_create_set_dialog).props('color=primary')
                    ui.button('Manage Sets', on_click=self.show_manage_sets_dialog).props('color=secondary')
            
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
                # Preview button template
                actions_template = '''
                    <q-td key="actions" :props="props">
                        <q-btn flat color="primary" label="Preview" @click="$emit('preview', props.row)" />
                    </q-td>
                '''
                self.documents_table.add_slot('body-cell-actions', actions_template)
                self.documents_table.on('preview', lambda e: self.show_preview(e.args))
                self.documents_table.on('selection', self.handle_selection)
            
            # Selected documents actions
            with ui.row().classes('w-full mt-4'):
                self.selection_label = ui.label('0 documents selected')
                ui.button('Add to Set', on_click=self.show_add_to_set_dialog).props('color=primary')
            
            # Document preview dialog
            self.preview_dialog = ui.dialog()
            with self.preview_dialog:
                with ui.card().classes('p-4'):
                    self.preview_title = ui.label().classes('text-h6')
                    self.preview_content = ui.textarea(label='Content', value='').props('disable').classes('w-full min-w-[500px] min-h-[300px]')
                    
                    # Add prompt selection and submission
                    ui.label('Select Prompt').classes('text-h6 mt-4')
                    self.preview_prompt_select = ui.select(
                        options=self.get_prompts_options(),
                        label='Choose a prompt'
                    ).classes('w-full')
                    
                    # Result area
                    self.preview_result = ui.textarea(
                        label='Result',
                        value='',
                        placeholder='Result will appear here...'
                    ).props('disable').classes('w-full min-h-[200px] mt-4')
                    
                    # Submit button
                    with ui.row().classes('w-full justify-end mt-4'):
                        ui.button('Close', on_click=lambda: self.preview_dialog.close()).props('flat')
                        ui.button('Submit', on_click=self.handle_preview_submit).props('color=primary')
            
            # Create Set Dialog
            self.create_set_dialog = ui.dialog()
            with self.create_set_dialog:
                with ui.card().classes('p-4'):
                    ui.label('Create New Document Set').classes('text-h6 mb-4')
                    self.new_set_name = ui.input('Set Name').classes('w-full')
                    self.new_set_description = ui.textarea('Description').classes('w-full')
                    
                    # Query Builder
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
            
            # Add to Set Dialog
            self.add_to_set_dialog = ui.dialog()
            with self.add_to_set_dialog:
                with ui.card().classes('p-4'):
                    ui.label('Add to Set').classes('text-h6 mb-4')
                    self.set_selector = ui.select(
                        options=self.get_sets_options(), 
                        label='Select Sets',
                        multiple=True
                    ).classes('w-full')
                    # Add a summary label to show selected sets
                    self.set_selection_summary = ui.label('No sets selected').classes('text-sm text-gray-600 mt-1')
                    self.set_selector.on('update:model-value', self.update_set_selection_summary)
                    with ui.row().classes('w-full justify-end mt-4'):
                        ui.button('Cancel', on_click=lambda: self.add_to_set_dialog.close()).props('flat')
                        ui.button('Add', on_click=self.add_to_set).props('color=primary')
            
            # Manage Sets Dialog
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
                    
                    # Add slot for actions column
                    actions_template = '''
                        <q-td key="actions" :props="props">
                            <q-btn flat color="primary" label="View" @click="$emit('view', props.row)" />
                        </q-td>
                    '''
                    self.sets_table.add_slot('body-cell-actions', actions_template)
                    self.sets_table.on('view', lambda e: self.view_set(e.args['id']))

    def handle_selection(self, e):
        try:
            # Extract information from the event
            if isinstance(e.args, dict):
                rows = e.args.get('rows', [])
                added = e.args.get('added', False)
                
                # Update selected documents based on whether rows are being added or removed
                for row in rows:
                    if isinstance(row, dict) and 'id' in row:
                        if added:
                            self.selected_documents.add(row['id'])
                        else:
                            self.selected_documents.discard(row['id'])
                
                self.selection_label.text = f'{len(self.selected_documents)} documents selected'
        except Exception as ex:
            ui.notify(f'Error in handle_selection: {str(ex)}', type='negative')

    def get_documents(self, search_term: str = '') -> list:
        try:
            db = get_db()
            query = db.query(Document)
            
            if search_term:
                query = query.filter(Document.name.ilike(f'%{search_term}%'))
            
            documents = query.all()
            return [{
                'id': doc.id,
                'name': doc.name,
                'file_type': doc.file_type,
                'uploaded_at': format_datetime(doc.uploaded_at),
                'content': doc.content,
                'sets': ', '.join(s.name for s in doc.sets)
            } for doc in documents]
        except Exception as ex:
            ui.notify(f'Error getting documents: {str(ex)}', type='negative')
            return []

    def show_preview(self, row):
        self.preview_title.text = f'Preview: {row["name"]}'
        content = row['content']
        self.preview_content.value = content[:1000] + ('...' if len(content) > 1000 else '')
        # Reset the result area
        self.preview_result.value = ''
        # Refresh prompt options
        self.preview_prompt_select.options = self.get_prompts_options()
        self.preview_dialog.open()

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
            'actions': None  # This field is needed but will be rendered by the slot
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
        
        # Add selected documents if any
        if self.selected_documents:
            documents = db.query(Document).filter(Document.id.in_(self.selected_documents)).all()
            new_set.documents.extend(documents)
        
        # Add query if specified
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
        self.update_documents()  # Refresh the documents table

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
        
        # Add documents to each selected set
        for set_id in self.set_selector.value:
            doc_set = db.query(DocumentSet).get(set_id)
            if doc_set:
                for doc in documents:
                    if doc not in doc_set.documents:
                        doc_set.documents.append(doc)
        
        db.commit()
        
        ui.notify('Documents added to selected sets successfully')
        self.add_to_set_dialog.close()
        self.update_documents()  # Refresh the documents table

    def view_set(self, set_id):
        db = get_db()
        doc_set = db.query(DocumentSet).get(set_id)
        
        # Clear current selection and select only documents from this set
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
            
            # Here you would typically call your LLM or processing logic
            # For now, we'll just combine the prompt and content as an example
            result = f"Prompt: {prompt.content}\n\nDocument Content: {self.preview_content.value}\n\nResult: This is a placeholder result. Implement your actual processing logic here."
            
            self.preview_result.value = result
            ui.notify('Processing complete', type='positive')
            
        except Exception as ex:
            ui.notify(f'Error processing preview: {str(ex)}', type='negative')

class PromptManager:
    def __init__(self):
        self.selected_prompts = set()
        
        with ui.card().classes('w-full'):
            ui.label('Manage Prompts').classes('text-h6')
            
            # Search and Set Management
            with ui.row().classes('w-full items-center justify-between'):
                with ui.column().classes('w-1/2'):
                    self.search_input = ui.input(label='Search Prompts').classes('w-full')
                    self.search_input.on('change', self.update_prompts)
                
                with ui.column().classes('w-1/2 flex justify-end'):
                    ui.button('Create New Set', on_click=self.show_create_set_dialog).props('color=primary')
                    ui.button('Manage Sets', on_click=self.show_manage_sets_dialog).props('color=secondary')
            
            # Create prompt form
            with ui.row().classes('w-full mt-4'):
                self.prompt_name = ui.input(label='Prompt Name').classes('w-1/3')
                self.prompt_content = ui.textarea(label='Prompt Content').classes('w-2/3')
                ui.button('Save Prompt', on_click=self.save_prompt).props('color=primary')
            
            # Prompts table
            with ui.table(
                columns=[
                    {'name': 'name', 'label': 'Name', 'field': 'name', 'sortable': True},
                    {'name': 'content', 'label': 'Content', 'field': 'content'},
                    {'name': 'created', 'label': 'Created', 'field': 'created_at', 'sortable': True},
                    {'name': 'sets', 'label': 'Sets', 'field': 'sets'},
                    {'name': 'actions', 'label': 'Actions', 'field': 'actions'},
                ],
                rows=self.get_prompts(),
                pagination=10,
                row_key='id',
                selection='multiple'
            ).classes('w-full') as self.prompts_table:
                # Preview button template
                actions_template = '''
                    <q-td key="actions" :props="props">
                        <q-btn flat color="primary" label="Preview" @click="$emit('preview', props.row)" />
                    </q-td>
                '''
                self.prompts_table.add_slot('body-cell-actions', actions_template)
                self.prompts_table.on('preview', lambda e: self.show_preview(e.args))
                self.prompts_table.on('selection', self.handle_selection)
            
            # Selected prompts actions
            with ui.row().classes('w-full mt-4'):
                self.selection_label = ui.label('0 prompts selected')
                ui.button('Add to Set', on_click=self.show_add_to_set_dialog).props('color=primary')
            
            # Prompt preview dialog
            self.preview_dialog = ui.dialog()
            with self.preview_dialog:
                with ui.card().classes('p-4'):
                    self.preview_title = ui.label().classes('text-h6')
                    self.preview_content = ui.textarea(label='Content', value='').props('disable').classes('w-full min-w-[500px] min-h-[300px]')
            
            # Create Set Dialog
            self.create_set_dialog = ui.dialog()
            with self.create_set_dialog:
                with ui.card().classes('p-4'):
                    ui.label('Create New Prompt Set').classes('text-h6 mb-4')
                    self.new_set_name = ui.input('Set Name').classes('w-full')
                    self.new_set_description = ui.textarea('Description').classes('w-full')
                    
                    # Query Builder
                    ui.label('Add Query (Optional)').classes('mt-4')
                    with ui.row().classes('w-full items-end'):
                        query_type_options = [
                            {'label': 'Prompt Name', 'value': 'name'},
                            {'label': 'Content', 'value': 'content'}
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
            
            # Add to Set Dialog
            self.add_to_set_dialog = ui.dialog()
            with self.add_to_set_dialog:
                with ui.card().classes('p-4'):
                    ui.label('Add to Set').classes('text-h6 mb-4')
                    self.set_selector = ui.select(
                        options=self.get_sets_options(), 
                        label='Select Sets',
                        multiple=True
                    ).classes('w-full')
                    # Add a summary label to show selected sets
                    self.set_selection_summary = ui.label('No sets selected').classes('text-sm text-gray-600 mt-1')
                    self.set_selector.on('update:model-value', self.update_set_selection_summary)
                    with ui.row().classes('w-full justify-end mt-4'):
                        ui.button('Cancel', on_click=lambda: self.add_to_set_dialog.close()).props('flat')
                        ui.button('Add', on_click=self.add_to_set).props('color=primary')
            
            # Manage Sets Dialog
            self.manage_sets_dialog = ui.dialog()
            with self.manage_sets_dialog:
                with ui.card().classes('p-4 min-w-[600px]'):
                    ui.label('Manage Prompt Sets').classes('text-h6 mb-4')
                    self.sets_table = ui.table(
                        columns=[
                            {'name': 'name', 'label': 'Set Name', 'field': 'name'},
                            {'name': 'description', 'label': 'Description', 'field': 'description'},
                            {'name': 'prompt_count', 'label': 'Prompts', 'field': 'prompt_count'},
                            {'name': 'actions', 'label': 'Actions', 'field': 'actions'},
                        ],
                        rows=self.get_sets(),
                        pagination=5,
                    ).classes('w-full')
                    
                    # Add slot for actions column
                    actions_template = '''
                        <q-td key="actions" :props="props">
                            <q-btn flat color="primary" label="View" @click="$emit('view', props.row)" />
                        </q-td>
                    '''
                    self.sets_table.add_slot('body-cell-actions', actions_template)
                    self.sets_table.on('view', lambda e: self.view_set(e.args['id']))

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
                
                self.selection_label.text = f'{len(self.selected_prompts)} prompts selected'
        except Exception as ex:
            ui.notify(f'Error in handle_selection: {str(ex)}', type='negative')

    def get_prompts(self, search_term: str = '') -> list:
        try:
            db = get_db()
            query = db.query(Prompt)
            
            if search_term:
                query = query.filter(Prompt.name.ilike(f'%{search_term}%'))
            
            prompts = query.all()
            return [{
                'id': p.id,
                'name': p.name,
                'content': p.content,
                'created_at': format_datetime(p.created_at),
                'sets': ', '.join(s.name for s in p.sets)
            } for p in prompts]
        except Exception as ex:
            ui.notify(f'Error getting prompts: {str(ex)}', type='negative')
            return []

    def show_preview(self, row):
        self.preview_title.text = f'Preview: {row["name"]}'
        self.preview_content.value = row['content']
        self.preview_dialog.open()

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
        self.prompts_table.rows = self.get_prompts()
        self.prompt_name.value = ''
        self.prompt_content.value = ''

    def show_create_set_dialog(self):
        self.create_set_dialog.open()

    def show_add_to_set_dialog(self):
        try:
            if not self.selected_prompts:
                ui.notify('Please select prompts first', type='warning')
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
        sets = db.query(PromptSet).all()
        return [{'label': f"{s.name} ({len(s.prompts)} prompts)", 'value': s.id} for s in sets]

    def get_sets(self) -> list:
        db = get_db()
        sets = db.query(PromptSet).all()
        return [{
            'id': s.id,
            'name': s.name,
            'description': s.description,
            'prompt_count': len(s.prompts),
            'actions': None  # This field is needed but will be rendered by the slot
        } for s in sets]

    def create_set(self):
        if not self.new_set_name.value:
            ui.notify('Please enter a set name', type='warning')
            return
        
        db = get_db()
        new_set = PromptSet(
            name=self.new_set_name.value,
            description=self.new_set_description.value
        )
        
        # Add selected prompts if any
        if self.selected_prompts:
            prompts = db.query(Prompt).filter(Prompt.id.in_(self.selected_prompts)).all()
            new_set.prompts.extend(prompts)
        
        # Add query if specified
        if all([self.query_type.value, self.query_operator.value, self.query_value.value]):
            query = PromptQuery(
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
        self.update_prompts()  # Refresh the prompts table

    def update_set_selection_summary(self, e):
        """Update the summary of selected sets"""
        if not e.value:
            self.set_selection_summary.text = 'No sets selected'
            return
        
        db = get_db()
        selected_sets = db.query(PromptSet).filter(PromptSet.id.in_(e.value)).all()
        set_names = ', '.join(s.name for s in selected_sets)
        self.set_selection_summary.text = f"Selected sets: {set_names}"

    def add_to_set(self):
        if not self.set_selector.value:
            ui.notify('Please select at least one set', type='warning')
            return
        
        db = get_db()
        prompts = db.query(Prompt).filter(Prompt.id.in_(self.selected_prompts)).all()
        
        # Add prompts to each selected set
        for set_id in self.set_selector.value:
            prompt_set = db.query(PromptSet).get(set_id)
            if prompt_set:
                for prompt in prompts:
                    if prompt not in prompt_set.prompts:
                        prompt_set.prompts.append(prompt)
        
        db.commit()
        
        ui.notify('Prompts added to selected sets successfully')
        self.add_to_set_dialog.close()
        self.update_prompts()  # Refresh the prompts table

    def view_set(self, set_id):
        db = get_db()
        prompt_set = db.query(PromptSet).get(set_id)
        
        # Clear current selection and select only prompts from this set
        self.selected_prompts.clear()
        self.selected_prompts.update(p.id for p in prompt_set.prompts)
        
        self.update_prompts()
        self.manage_sets_dialog.close()
        ui.notify(f'Viewing prompts in set: {prompt_set.name}')

class BatchRunScheduler:
    def __init__(self):
        with ui.card().classes('w-full'):
            ui.label('Schedule Batch Runs').classes('text-h6')
            with ui.row():
                self.run_name = ui.input(label='Batch Run Name')
                self.schedule_time = ui.input(label='Schedule Time').props('type=datetime-local')
            
            # Document set selection
            ui.label('Select Document Sets').classes('text-h6 mt-4')
            self.doc_set_selection = ui.select(
                label='Select Document Sets',
                options=self.get_document_sets(),
                multiple=True
            ).classes('w-full')
            
            # Selected documents summary
            self.doc_summary = ui.label('No documents selected').classes('text-sm text-gray-600 mt-1')
            self.doc_set_selection.on('update:model-value', self.update_doc_summary)
            
            # Prompt set selection
            ui.label('Select Prompt Sets').classes('text-h6 mt-4')
            self.prompt_set_selection = ui.select(
                label='Select Prompt Sets',
                options=self.get_prompt_sets(),
                multiple=True
            ).classes('w-full')
            
            # Selected prompts summary
            self.prompt_summary = ui.label('No prompts selected').classes('text-sm text-gray-600 mt-1')
            self.prompt_set_selection.on('update:model-value', self.update_prompt_summary)
            
            ui.button('Schedule Run', on_click=self.schedule_run).props('color=primary')
            
            # Batch runs table
            self.runs_table = ui.table(
                columns=[
                    {'name': 'name', 'label': 'Name', 'field': 'name'},
                    {'name': 'status', 'label': 'Status', 'field': 'status'},
                    {'name': 'scheduled', 'label': 'Scheduled For', 'field': 'scheduled_for'},
                    {'name': 'doc_sets', 'label': 'Document Sets', 'field': 'doc_sets'},
                    {'name': 'prompt_sets', 'label': 'Prompt Sets', 'field': 'prompt_sets'},
                ],
                rows=self.get_batch_runs()
            ).classes('w-full')

    def get_document_sets(self):
        db = get_db()
        sets = db.query(DocumentSet).all()
        return [{'label': f"{s.name} ({len(s.documents)} documents)", 'value': s.id} for s in sets]

    def get_prompt_sets(self):
        db = get_db()
        sets = db.query(PromptSet).all()
        return [{'label': f"{s.name} ({len(s.prompts)} prompts)", 'value': s.id} for s in sets]

    def update_doc_summary(self, e):
        if not e.value:
            self.doc_summary.text = 'No documents selected'
            return
        
        db = get_db()
        selected_sets = db.query(DocumentSet).filter(DocumentSet.id.in_(e.value)).all()
        total_docs = sum(len(s.documents) for s in selected_sets)
        set_names = ', '.join(s.name for s in selected_sets)
        self.doc_summary.text = f"Selected {total_docs} documents from sets: {set_names}"

    def update_prompt_summary(self, e):
        if not e.value:
            self.prompt_summary.text = 'No prompts selected'
            return
        
        db = get_db()
        selected_sets = db.query(PromptSet).filter(PromptSet.id.in_(e.value)).all()
        total_prompts = sum(len(s.prompts) for s in selected_sets)
        set_names = ', '.join(s.name for s in selected_sets)
        self.prompt_summary.text = f"Selected {total_prompts} prompts from sets: {set_names}"

    def schedule_run(self):
        if not self.run_name.value:
            ui.notify('Please enter a batch run name', type='warning')
            return
        
        if not self.schedule_time.value:
            ui.notify('Please select a schedule time', type='warning')
            return
        
        if not self.doc_set_selection.value or not self.prompt_set_selection.value:
            ui.notify('Please select both document sets and prompt sets', type='warning')
            return
        
        try:
            db = get_db()
            
            # Create batch run
            batch_run = BatchRun(
                name=self.run_name.value,
                scheduled_for=datetime.fromisoformat(self.schedule_time.value)
            )
            db.add(batch_run)
            
            # Add documents from selected sets
            doc_sets = db.query(DocumentSet).filter(DocumentSet.id.in_(self.doc_set_selection.value)).all()
            for doc_set in doc_sets:
                batch_run.documents.extend(doc_set.documents)
            
            # Add prompts from selected sets
            prompt_sets = db.query(PromptSet).filter(PromptSet.id.in_(self.prompt_set_selection.value)).all()
            for prompt_set in prompt_sets:
                batch_run.prompts.extend(prompt_set.prompts)
            
            db.commit()
            ui.notify('Batch run scheduled successfully!')
            
            # Reset form
            self.run_name.value = ''
            self.schedule_time.value = ''
            self.doc_set_selection.value = []
            self.prompt_set_selection.value = []
            self.update_doc_summary(None)
            self.update_prompt_summary(None)
            
            # Update table
            self.runs_table.rows = self.get_batch_runs()
            
        except Exception as ex:
            ui.notify(f'Error scheduling batch run: {str(ex)}', type='negative')

    def get_batch_runs(self):
        db = get_db()
        runs = db.query(BatchRun).all()
        return [{
            'name': r.name,
            'status': r.status,
            'scheduled_for': format_datetime(r.scheduled_for),
            'doc_sets': self.get_set_names_for_docs(r.documents),
            'prompt_sets': self.get_set_names_for_prompts(r.prompts)
        } for r in runs]

    def get_set_names_for_docs(self, documents):
        """Get unique set names for a list of documents"""
        sets = set()
        for doc in documents:
            sets.update(s.name for s in doc.sets)
        return ', '.join(sorted(sets)) if sets else 'No sets'

    def get_set_names_for_prompts(self, prompts):
        """Get unique set names for a list of prompts"""
        sets = set()
        for prompt in prompts:
            sets.update(s.name for s in prompt.sets)
        return ', '.join(sorted(sets)) if sets else 'No sets'

class ResultsViewer:
    def __init__(self):
        with ui.card().classes('w-full'):
            ui.label('View Results').classes('text-h6')
            
            # Filters
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
            
            # Clear filters button
            with ui.row().classes('w-full justify-end mt-2'):
                ui.button('Clear All Filters', on_click=self.clear_filters).props('flat color=grey-7')
            
            # Results statistics
            with ui.row().classes('w-full mt-4'):
                self.stats_label = ui.label('Showing all results').classes('text-sm text-gray-600')
            
            # Results table
            self.results_table = ui.table(
                columns=[
                    {'name': 'batch_run', 'label': 'Batch Run', 'field': 'batch_run'},
                    {'name': 'document', 'label': 'Document', 'field': 'document'},
                    {'name': 'prompt', 'label': 'Prompt', 'field': 'prompt'},
                    {'name': 'response', 'label': 'Response', 'field': 'response'},
                    {'name': 'created', 'label': 'Created', 'field': 'created_at'},
                    {'name': 'feedback', 'label': 'Feedback', 'field': 'feedback'},
                    {'name': 'actions', 'label': 'Actions', 'field': 'actions'},
                ],
                rows=self.get_results(),
                pagination=10,
                selection='none'
            ).classes('w-full')
            
            # Add slot for actions column
            actions_template = '''
                <q-td key="actions" :props="props">
                    <q-btn flat color="primary" label="Add Feedback" @click="$emit('feedback', props.row)" />
                </q-td>
            '''
            self.results_table.add_slot('body-cell-actions', actions_template)
            self.results_table.on('feedback', lambda e: self.show_feedback_dialog(e.args))
            
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

    def clear_filters(self):
        """Reset all filters to their default values"""
        self.batch_filter.value = None
        self.doc_filter.value = None
        self.prompt_filter.value = None
        self.rating_filter.value = None
        self.update_results()

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
        
        # Apply filters
        if batch_id:
            query = query.filter(Result.batch_run_id == batch_id)
        if doc_id:
            query = query.filter(Result.document_id == doc_id)
        if prompt_id:
            query = query.filter(Result.prompt_id == prompt_id)
        
        results = query.all()
        filtered_results = []
        
        for r in results:
            # Get the highest rating if there are multiple feedbacks
            max_rating = max([f.rating for f in r.feedback], default=0) if r.feedback else 0
            
            # Apply rating filter
            if min_rating and max_rating < min_rating:
                continue
            
            filtered_results.append({
                'id': r.id,
                'batch_run': r.batch_run.name,
                'document': r.document.name,
                'prompt': r.prompt.name,
                'response': r.response,
                'created_at': format_datetime(r.created_at),
                'feedback': self.format_feedback(r.feedback),
                'actions': None  # Rendered by slot
            })
        
        return filtered_results

    def format_feedback(self, feedback_list):
        """Format feedback for display in the table"""
        if not feedback_list:
            return 'No feedback yet'
        
        # Show all feedback, sorted by rating (highest first)
        sorted_feedback = sorted(feedback_list, key=lambda x: (-x.rating, x.created_at))
        feedback_texts = []
        
        for fb in sorted_feedback:
            stars = '⭐' * fb.rating
            comment = f": {fb.comment}" if fb.comment else ""
            feedback_texts.append(f"{stars}{comment}")
        
        return '\n'.join(feedback_texts)

    def update_results(self):
        try:
            results = self.get_results(
                batch_id=self.batch_filter.value,
                doc_id=self.doc_filter.value,
                prompt_id=self.prompt_filter.value,
                min_rating=self.rating_filter.value
            )
            self.results_table.rows = results
            
            # Update statistics
            filters_applied = []
            if self.batch_filter.value:
                filters_applied.append("batch run")
            if self.doc_filter.value:
                filters_applied.append("document")
            if self.prompt_filter.value:
                filters_applied.append("prompt")
            if self.rating_filter.value:
                filters_applied.append(f"{self.rating_filter.value}+ star rating")
            
            if filters_applied:
                filter_text = ", ".join(filters_applied)
                self.stats_label.text = f"Showing {len(results)} results filtered by {filter_text}"
            else:
                self.stats_label.text = f"Showing all {len(results)} results"
            
        except Exception as ex:
            ui.notify(f'Error updating results: {str(ex)}', type='negative')

    def show_feedback_dialog(self, row):
        self.current_result_id = row['id']
        self.rating_select.value = None
        self.feedback_comment.value = ''
        self.feedback_dialog.open()

    def submit_feedback(self):
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

# Main application setup
@ui.page('/')
def main_page():
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

# Initialize batch processor if enabled
if os.getenv('ENABLE_BATCH_PROCESSOR') == 'true':
    start_background_processor()
    ui.notify('Batch processor started')

ui.run(title='Document Analyzer', port=8080) 