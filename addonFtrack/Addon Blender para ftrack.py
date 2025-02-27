# Bloco para instalação do addon
bl_info = {
    "name": "Ftrack Tasks",
    "author": "Histeria Studio",
    "version": (1, 2, 0),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar > Ftrack",
    "description": "Gerenciador de tarefas do Ftrack para Blender",
    "warning": "",
    "category": "Interface",
}

import bpy
import json
import urllib.request
import ssl
import webbrowser
from datetime import datetime
from bpy.types import Panel, Operator, PropertyGroup
from bpy.props import StringProperty, CollectionProperty, IntProperty

def format_date(date_string):
    """Formata a data do formato ISO para dia/mês"""
    if not date_string:
        return ''
    try:
        date_obj = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        return date_obj.strftime('%d/%m')
    except Exception:
        return date_string

class FtrackAPI:
    """Classe para comunicação com a API do Ftrack"""

    def __init__(self, server_url, username, api_key):
        self.server_url = server_url.rstrip('/')
        self.username = username
        self.api_key = api_key
        self.api_endpoint = f"{self.server_url}/api"
        self.ssl_context = ssl._create_unverified_context()

    def call(self, operations):
        """Executa chamadas à API do Ftrack"""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'ftrack-user': self.username,
            'ftrack-api-key': self.api_key
        }
        try:
            request = urllib.request.Request(
                self.api_endpoint,
                data=json.dumps(operations).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            with urllib.request.urlopen(request, context=self.ssl_context) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            print(f"Erro na comunicação com a API: {str(e)}")
            raise

    def get_projects(self):
        """Busca projetos ativos onde o usuário tem tarefas atribuídas"""
        # Alteramos a abordagem para primeiro buscar as tarefas do usuário,
        # depois extrair os projetos únicos dessas tarefas
        operations = [{
            'action': 'query',
            'expression': (
                'select id, name, project.id, project.name, project.full_name '
                'from Task '
                'where assignments any (resource.username is "{0}") '
                'and project.status is "active"'
            ).format(self.username)
        }]

        try:
            print("Buscando projetos do usuário...")
            results = self.call(operations)

            # Verifica se obtivemos uma resposta válida
            if not results or not isinstance(results, list) or len(results) == 0:
                print("Nenhum resultado retornado pela API")
                return []

            print(f"Resposta da API: {results}")

            # Verifica se a estrutura contém os dados esperados
            if 'data' not in results[0]:
                print("Resposta não contém o campo 'data'")
                return []

            tasks_data = results[0]['data']
            if not isinstance(tasks_data, list):
                print("O campo 'data' não é uma lista")
                return []

            print(f"Encontradas {len(tasks_data)} tarefas")

            # Extrai projetos únicos das tarefas
            unique_projects = {}
            for task in tasks_data:
                # Extrai informações do projeto da tarefa
                project_data = task.get('project', {})
                if not project_data:
                    print(f"Tarefa {task.get('id')} não tem informações de projeto")
                    continue

                project_id = project_data.get('id')
                if not project_id:
                    print(f"Projeto da tarefa {task.get('id')} não tem ID")
                    continue

                # Armazena projetos únicos por ID
                if project_id not in unique_projects:
                    unique_projects[project_id] = {
                        'id': project_id,
                        'name': project_data.get('name', 'Sem nome'),
                        'full_name': project_data.get('full_name', project_data.get('name', 'Sem nome'))
                    }

            print(f"Extraídos {len(unique_projects)} projetos únicos")

            # Retorna a lista de projetos
            return list(unique_projects.values())

        except Exception as e:
            print(f"Erro detalhado ao buscar projetos: {str(e)}")
            return []

    def get_tasks(self, project_id=None):
        """
        Busca tarefas atribuídas ao usuário.
        Se project_id for fornecido, retorna apenas tarefas desse projeto.
        """
        # Base da expressão de consulta
        expression = (
            'select id, name, type.name, status.name, '
            'project.id, project.name, '
            'parent.name, start_date, end_date '
            'from Task '
            'where assignments any (resource.username is "{0}") '
        ).format(self.username)

        # Adiciona filtro por projeto se especificado
        if project_id:
            expression += f'and project.id is "{project_id}" '
        else:
            expression += 'and project.status is "active" '

        # Ordenação
        expression += 'order by name ascending'

        operations = [{'action': 'query', 'expression': expression}]

        try:
            print(f"Buscando tarefas com filtro de projeto: {project_id if project_id else 'todos'}")
            results = self.call(operations)

            # Verifica os resultados
            if not results or 'data' not in results[0]:
                print("Nenhum resultado válido retornado para tarefas")
                return []

            tasks = results[0]['data']
            print(f"Encontradas {len(tasks)} tarefas")
            return tasks

        except Exception as e:
            print(f"Erro detalhado ao buscar tarefas: {str(e)}")
            return []

# Classes para armazenar dados
class FtrackProjectItem(PropertyGroup):
    id: StringProperty()
    name: StringProperty()
    full_name: StringProperty()

class FtrackTaskItem(PropertyGroup):
    id: StringProperty()
    name: StringProperty()
    status: StringProperty()
    project_id: StringProperty()
    project: StringProperty()
    parent: StringProperty()
    end_date: StringProperty()
    url: StringProperty()

# Operador para copiar ID para a área de transferência
class FTRACK_OT_copy_task_id(Operator):
    bl_idname = "ftrack.copy_task_id"
    bl_label = "Copiar ID"
    bl_description = "Copia o ID da tarefa para a área de transferência"

    task_id: StringProperty()

    def execute(self, context):
        context.window_manager.clipboard = self.task_id
        self.report({'INFO'}, f"ID {self.task_id} copiado para a área de transferência")
        return {'FINISHED'}

# Operador para abrir URL da tarefa
class FTRACK_OT_open_task_url(Operator):
    bl_idname = "ftrack.open_task_url"
    bl_label = "Abrir Tarefa"
    bl_description = "Abre a tarefa no navegador"

    url: StringProperty()

    def execute(self, context):
        if self.url:
            webbrowser.open(self.url)
        return {'FINISHED'}

# Classe base para operadores de busca no Ftrack
class FtrackFetchOperator:
    """Classe base com métodos comuns para operadores de busca no Ftrack"""

    @staticmethod
    def get_api(context):
        """Inicializa e retorna o objeto API, ou None se não for possível"""
        server_url = context.scene.ftrack_server_url
        username = context.scene.ftrack_username
        api_key = context.scene.ftrack_api_key

        if not server_url or not username or not api_key:
            return None

        return FtrackAPI(server_url, username, api_key)

    @staticmethod
    def add_task_to_list(context, task):
        """Adiciona uma tarefa à lista de tarefas"""
        item = context.scene.ftrack_tasks.add()
        item.id = task.get('id', '')
        item.name = task.get('name', '')

        # Status
        status = task.get('status')
        item.status = status.get('name', '') if isinstance(status, dict) else ''

        # Projeto
        project = task.get('project')
        if isinstance(project, dict):
            item.project_id = project.get('id', '')
            item.project = project.get('name', '')
        else:
            item.project_id = ''
            item.project = ''

        # Parent
        parent = task.get('parent')
        item.parent = parent.get('name', '') if isinstance(parent, dict) else ''

        # Data de fim
        end_date = task.get('end_date')
        if end_date:
            if isinstance(end_date, dict):
                item.end_date = end_date.get('value', '')
            elif isinstance(end_date, str):
                item.end_date = end_date

        # URL
        if item.id and item.project_id:
            item.url = (
                f"{context.scene.ftrack_server_url}/#"
                f"slideEntityId={item.id}&"
                f"slideEntityType=task&"
                f"view=tasks&"
                f"itemId=projects&"
                f"entityId={item.project_id}&"
                f"entityType=show"
            )
        else:
            item.url = ""

# Operador para buscar projetos
class FTRACK_OT_fetch_projects(Operator, FtrackFetchOperator):
    bl_idname = "ftrack.fetch_projects"
    bl_label = "Buscar Projetos"
    bl_description = "Busca projetos onde você tem tarefas atribuídas"

    def execute(self, context):
        # Limpar listas
        context.scene.ftrack_projects.clear()
        context.scene.ftrack_tasks.clear()

        # Inicializa API
        api = self.get_api(context)
        if not api:
            self.report({'ERROR'}, "Preencha todos os campos de configuração")
            return {'CANCELLED'}

        try:
            print("Iniciando busca de projetos...")
            projects = api.get_projects()

            if not projects:
                print("Nenhum projeto encontrado")
                self.report({'INFO'}, "Nenhum projeto encontrado")
                return {'FINISHED'}

            print(f"Encontrados {len(projects)} projetos")

            # Adiciona projetos à lista
            for project in projects:
                item = context.scene.ftrack_projects.add()
                item.id = project.get('id', '')
                item.name = project.get('name', '')
                item.full_name = project.get('full_name', item.name)
                print(f"Adicionado projeto: {item.name} ({item.id})")

            # Seleciona o primeiro projeto
            context.scene.selected_project_index = 0 if projects else -1

            self.report({'INFO'}, f"Encontrados {len(projects)} projetos")
            return {'FINISHED'}

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"Erro ao buscar projetos: {str(e)}")
            return {'CANCELLED'}

# Operador para buscar tarefas de um projeto
class FTRACK_OT_fetch_project_tasks(Operator, FtrackFetchOperator):
    bl_idname = "ftrack.fetch_project_tasks"
    bl_label = "Buscar Tarefas do Projeto"
    bl_description = "Busca tarefas do projeto selecionado"

    project_id: StringProperty()

    def execute(self, context):
        context.scene.ftrack_tasks.clear()

        if not self.project_id:
            self.report({'ERROR'}, "ID do projeto inválido")
            return {'CANCELLED'}

        api = self.get_api(context)
        if not api:
            self.report({'ERROR'}, "Preencha todos os campos de configuração")
            return {'CANCELLED'}

        try:
            tasks = api.get_tasks(self.project_id)

            if not tasks:
                self.report({'INFO'}, "Nenhuma tarefa encontrada neste projeto")
                return {'FINISHED'}

            # Adiciona tarefas à lista
            for task in tasks:
                self.add_task_to_list(context, task)

            # Seleciona a primeira tarefa
            context.scene.selected_task_index = 0 if tasks else -1

            self.report({'INFO'}, f"Encontradas {len(tasks)} tarefas")
            return {'FINISHED'}

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"Erro ao buscar tarefas: {str(e)}")
            return {'CANCELLED'}

# Operador para buscar todas as tarefas
class FTRACK_OT_fetch_all_tasks(Operator, FtrackFetchOperator):
    bl_idname = "ftrack.fetch_all_tasks"
    bl_label = "Buscar Todas Tarefas"
    bl_description = "Busca todas as tarefas atribuídas a você"

    def execute(self, context):
        context.scene.ftrack_tasks.clear()

        api = self.get_api(context)
        if not api:
            self.report({'ERROR'}, "Preencha todos os campos de configuração")
            return {'CANCELLED'}

        try:
            tasks = api.get_tasks()

            if not tasks:
                self.report({'INFO'}, "Nenhuma tarefa encontrada")
                return {'FINISHED'}

            # Adiciona tarefas à lista
            for task in tasks:
                self.add_task_to_list(context, task)

            # Seleciona a primeira tarefa
            context.scene.selected_task_index = 0 if tasks else -1

            self.report({'INFO'}, f"Encontradas {len(tasks)} tarefas")
            return {'FINISHED'}

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"Erro ao buscar tarefas: {str(e)}")
            return {'CANCELLED'}

# Painel para exibir projetos e tarefas do Ftrack
class FTRACK_PT_tasks_panel(Panel):
    bl_label = "Ftrack"
    bl_idname = "FTRACK_PT_tasks_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Ftrack'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Configurações de conexão
        box = layout.box()
        box.label(text="Configurações")
        box.prop(scene, "ftrack_server_url", text="URL")
        box.prop(scene, "ftrack_username", text="Usuário")
        box.prop(scene, "ftrack_api_key", text="API Key")

        # Botões para buscar dados
        row = layout.row(align=True)
        row.operator("ftrack.fetch_projects", icon='FILE_FOLDER')
        row.operator("ftrack.fetch_all_tasks", icon='CHECKBOX_HLT')

        # Lista de projetos
        if scene.ftrack_projects:
            box = layout.box()
            box.label(text="Projetos:")

            row = box.row()
            row.template_list("UI_UL_list", "ftrack_projects", scene, "ftrack_projects",
                             scene, "selected_project_index", rows=3)

            # Botão para buscar tarefas do projeto selecionado
            if scene.selected_project_index >= 0 and scene.selected_project_index < len(scene.ftrack_projects):
                selected_project = scene.ftrack_projects[scene.selected_project_index]

                row = box.row()
                op = row.operator("ftrack.fetch_project_tasks", text=f"Tarefas de '{selected_project.name}'", icon='TRIA_RIGHT')
                op.project_id = selected_project.id

        # Lista de tarefas
        if scene.ftrack_tasks:
            box = layout.box()
            box.label(text="Tarefas:")

            row = box.row()
            row.template_list("UI_UL_list", "ftrack_tasks", scene, "ftrack_tasks",
                             scene, "selected_task_index", rows=5)

            # Detalhes da tarefa selecionada
            if scene.selected_task_index >= 0 and scene.selected_task_index < len(scene.ftrack_tasks):
                selected_task = scene.ftrack_tasks[scene.selected_task_index]

                detail_box = box.box()
                detail_box.label(text="Detalhes da Tarefa:", icon='INFO')

                # ID e botão para copiar
                row = detail_box.row()
                row.label(text=f"ID: {selected_task.id}")
                op = row.operator("ftrack.copy_task_id", text="", icon='COPYDOWN')
                op.task_id = selected_task.id

                # Outras informações
                col = detail_box.column()
                col.label(text=f"Projeto: {selected_task.project}")
                col.label(text=f"Parent: {selected_task.parent}")
                col.label(text=f"Status: {selected_task.status}")

                if selected_task.end_date:
                    col.label(text=f"Data Fim: {format_date(selected_task.end_date)}")

                # Botão para abrir no navegador
                row = detail_box.row()
                op = row.operator("ftrack.open_task_url", text="Abrir no Navegador", icon='URL')
                op.url = selected_task.url

# Registro do addon
def register():
    bpy.utils.register_class(FtrackProjectItem)
    bpy.utils.register_class(FtrackTaskItem)
    bpy.utils.register_class(FTRACK_OT_copy_task_id)
    bpy.utils.register_class(FTRACK_OT_open_task_url)
    bpy.utils.register_class(FTRACK_OT_fetch_projects)
    bpy.utils.register_class(FTRACK_OT_fetch_project_tasks)
    bpy.utils.register_class(FTRACK_OT_fetch_all_tasks)
    bpy.utils.register_class(FTRACK_PT_tasks_panel)

    # Propriedades
    bpy.types.Scene.ftrack_projects = CollectionProperty(type=FtrackProjectItem)
    bpy.types.Scene.ftrack_tasks = CollectionProperty(type=FtrackTaskItem)
    bpy.types.Scene.selected_project_index = IntProperty(default=-1)
    bpy.types.Scene.selected_task_index = IntProperty(default=-1)
    bpy.types.Scene.ftrack_server_url = StringProperty(
        name="Server URL",
        description="URL do servidor Ftrack",
        default="https://histeria.ftrackapp.com"
    )
    bpy.types.Scene.ftrack_username = StringProperty(
        name="Username",
        description="Nome de usuário do Ftrack",
        default="igor@histeria.studio"
    )
    bpy.types.Scene.ftrack_api_key = StringProperty(
        name="API Key",
        description="Chave de API do Ftrack",
        default=""
    )

def unregister():
    # Remove propriedades
    del bpy.types.Scene.ftrack_tasks
    del bpy.types.Scene.ftrack_projects
    del bpy.types.Scene.selected_project_index
    del bpy.types.Scene.selected_task_index
    del bpy.types.Scene.ftrack_server_url
    del bpy.types.Scene.ftrack_username
    del bpy.types.Scene.ftrack_api_key

    # Desregistra classes
    bpy.utils.unregister_class(FTRACK_PT_tasks_panel)
    bpy.utils.unregister_class(FTRACK_OT_fetch_all_tasks)
    bpy.utils.unregister_class(FTRACK_OT_fetch_project_tasks)
    bpy.utils.unregister_class(FTRACK_OT_fetch_projects)
    bpy.utils.unregister_class(FTRACK_OT_open_task_url)
    bpy.utils.unregister_class(FTRACK_OT_copy_task_id)
    bpy.utils.unregister_class(FtrackTaskItem)
    bpy.utils.unregister_class(FtrackProjectItem)

if __name__ == "__main__":
    register()
