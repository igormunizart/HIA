bl_info = {
    "name": "PeS",
    "author": "Igor Muniz",
    "version": (0, 0, 5),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > PeS",
    "description": "Addon feito para facilitar o processo de atualição e import de rigs de Poba e Sagu",
    "warning": "",
    "category": "Import",
}

import bpy
import os
import requests
from bpy.types import Panel, Operator
from bpy.props import StringProperty

# URL do arquivo JSON que contém as informações dos rigs
JSON_URL = "https://igormunizart.github.io/HIA/pes/rigs.json"

def get_version_from_filename(filename):
    """Extrai o número da versão e nome base do arquivo"""
    try:
        parts = filename.rsplit('_v', 1)
        if len(parts) == 2:
            base_name = parts[0]
            version = int(parts[1].split('.')[0])
            return base_name, version
    except:
        pass
    return filename, 0

def get_download_path():
    """Retorna o caminho para download baseado no arquivo .blend atual"""
    current_blend = bpy.data.filepath
    if not current_blend:
        return None
    parent_dir = os.path.dirname(os.path.dirname(current_blend))
    return os.path.join(parent_dir, "0_IN", "3_RIGs")

def load_rigs_database():
    """Carrega o banco de dados de rigs do JSON"""
    try:
        response = requests.get(JSON_URL)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Erro ao carregar banco de dados: {str(e)}")
        return {"rigs": {}}

def get_relative_path(filepath):
    """Converte um caminho absoluto para relativo ao arquivo .blend atual"""
    blend_file = bpy.data.filepath
    if not blend_file:
        return filepath  # Se o arquivo .blend não foi salvo, usa o caminho absoluto

    # Normaliza os caminhos para garantir que a comparação funcione corretamente
    blend_dir = os.path.normpath(os.path.dirname(blend_file))
    filepath = os.path.normpath(filepath)

    try:
        # Verifica se estão no mesmo drive
        if os.path.splitdrive(blend_dir)[0] != os.path.splitdrive(filepath)[0]:
            return filepath  # Se estiverem em drives diferentes, mantém absoluto

        # Calcula o caminho relativo usando '//' como prefixo (formato que o Blender reconhece)
        relative_path = os.path.relpath(filepath, blend_dir)
        # Substitui backslashes por forward slashes
        relative_path = relative_path.replace('\\', '/')
        # Adiciona o prefixo '//' que o Blender usa para caminhos relativos
        if not relative_path.startswith('//'):
            relative_path = '//' + relative_path

        return relative_path
    except ValueError:
        return filepath  # Em caso de erro, mantém o caminho absoluto

class DOWNLOADRIG_OT_download(Operator):
    bl_idname = "downloadrig.download"
    bl_label = "Baixar"

    rig_id: StringProperty()

    def execute(self, context):
        database = load_rigs_database()
        if self.rig_id not in database["rigs"]:
            self.report({'ERROR'}, "Rig não encontrado no banco de dados")
            return {'CANCELLED'}

        rig_data = database["rigs"][self.rig_id]
        download_url = rig_data["download_url"]

        download_dir = get_download_path()
        if not download_dir:
            self.report({'ERROR'}, "Por favor, salve seu arquivo .blend primeiro!")
            return {'CANCELLED'}

        try:
            os.makedirs(download_dir, exist_ok=True)
            filename = download_url.split('/')[-1].split('?')[0]
            filepath = os.path.join(download_dir, filename)

            response = requests.get(download_url, stream=True)
            response.raise_for_status()

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            self.report({'INFO'}, f"Rig baixado com sucesso em: {filepath}")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Erro ao baixar: {str(e)}")
            return {'CANCELLED'}

class DOWNLOADRIG_OT_download_and_link(Operator):
    bl_idname = "downloadrig.download_and_link"
    bl_label = "Baixar e Importar"

    rig_id: StringProperty()

    def execute(self, context):
        download_dir = get_download_path()
        if not download_dir:
            self.report({'ERROR'}, "Por favor, salve seu arquivo .blend primeiro!")
            return {'CANCELLED'}

        database = load_rigs_database()
        if self.rig_id not in database["rigs"]:
            self.report({'ERROR'}, "Rig não encontrado no banco de dados")
            return {'CANCELLED'}

        rig_data = database["rigs"][self.rig_id]
        download_url = rig_data["download_url"]

        try:
            # Download
            os.makedirs(download_dir, exist_ok=True)
            filename = download_url.split('/')[-1].split('?')[0]
            filepath = os.path.join(download_dir, filename)

            response = requests.get(download_url, stream=True)
            response.raise_for_status()

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # Convertendo para caminho relativo
            relative_filepath = get_relative_path(filepath)

            # Importa a collection
            collection_name = f"chr.{self.rig_id.split('_')[-2].lower()}_rig"

            with bpy.data.libraries.load(relative_filepath, link=True) as (data_from, data_to):
                if collection_name in data_from.collections:
                    data_to.collections = [collection_name]
                else:
                    self.report({'ERROR'}, f"Collection {collection_name} não encontrada no arquivo")
                    return {'CANCELLED'}

            # Adiciona a collection à cena
            for collection in data_to.collections:
                if collection is not None:
                    bpy.context.scene.collection.children.link(collection)

            self.report({'INFO'}, f"Rig baixado e importado com sucesso!")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Erro: {str(e)}")
            return {'CANCELLED'}

class DOWNLOADRIG_OT_update(Operator):
    bl_idname = "downloadrig.update"
    bl_label = "Atualizar"

    filepath: StringProperty()

    def execute(self, context):
        try:
            current_file = os.path.basename(self.filepath)
            base_name, current_version = get_version_from_filename(current_file)

            database = load_rigs_database()

            rig_found = False
            for rig_id, rig_data in database["rigs"].items():
                if rig_id in base_name:
                    rig_found = True
                    latest_version = rig_data["latest_version"]
                    download_url = rig_data["download_url"]
                    break

            if not rig_found:
                self.report({'ERROR'}, "Rig não encontrado no banco de dados")
                return {'CANCELLED'}

            if latest_version <= current_version:
                self.report({'INFO'}, f"Já está na versão mais recente (v{current_version})")
                return {'CANCELLED'}

            download_dir = os.path.dirname(self.filepath)
            new_filename = download_url.split('/')[-1].split('?')[0]
            new_filepath = os.path.join(download_dir, new_filename)

            response = requests.get(download_url, stream=True)
            response.raise_for_status()

            with open(new_filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # Convertendo para caminho relativo
            relative_filepath = get_relative_path(new_filepath)

            for lib in bpy.data.libraries:
                if lib.filepath == self.filepath:
                    lib.filepath = relative_filepath
                    lib.reload()

            self.report({'INFO'}, f"Rig atualizado para v{latest_version} e links atualizados!")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Erro ao atualizar: {str(e)}")
            return {'CANCELLED'}

class DOWNLOADRIG_OT_change_version(Operator):
    bl_idname = "downloadrig.change_version"
    bl_label = "Alterar Versão"

    filepath: StringProperty()
    version: StringProperty()
    download_url: StringProperty()

    def execute(self, context):
        try:
            download_dir = os.path.dirname(self.filepath)
            new_filename = self.download_url.split('/')[-1].split('?')[0]
            new_filepath = os.path.join(download_dir, new_filename)

            response = requests.get(self.download_url, stream=True)
            response.raise_for_status()

            with open(new_filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # Convertendo para caminho relativo
            relative_filepath = get_relative_path(new_filepath)

            for lib in bpy.data.libraries:
                if lib.filepath == self.filepath:
                    lib.filepath = relative_filepath
                    lib.reload()

            self.report({'INFO'}, f"Versão alterada para v{self.version}")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Erro ao mudar versão: {str(e)}")
            return {'CANCELLED'}

class DOWNLOADRIG_OT_show_versions(Operator):
    bl_idname = "downloadrig.show_versions"
    bl_label = "Versões Disponíveis"

    filepath: StringProperty()

    def execute(self, context):
        try:
            current_file = os.path.basename(self.filepath)
            base_name, current_version = get_version_from_filename(current_file)
            filepath = self.filepath

            database = load_rigs_database()

            for rig_id, rig_data in database["rigs"].items():
                if rig_id in base_name and "versions" in rig_data:
                    def draw_menu(self_menu, context):
                        layout = self_menu.layout
                        for version in sorted(rig_data["versions"].keys(), reverse=True):
                            op = layout.operator(
                                "downloadrig.change_version",
                                text=f"Versão {version}" + (" (atual)" if int(version) == current_version else "")
                            )
                            op.filepath = filepath
                            op.version = version
                            op.download_url = rig_data["versions"][version]

                    bpy.context.window_manager.popup_menu(draw_menu, title="Versões Disponíveis")
                    break

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Erro ao mostrar versões: {str(e)}")
            return {'CANCELLED'}

class DOWNLOADRIG_PT_update_panel(Panel):
    bl_label = "Atualizar rigs"
    bl_idname = "DOWNLOADRIG_PT_update_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'PeS'

    def draw(self, context):
        layout = self.layout
        database = load_rigs_database()

        linked_files = set()
        for lib in bpy.data.libraries:
            if lib.filepath:
                linked_files.add(lib.filepath)

        if linked_files:
            for filepath in sorted(linked_files):
                filename = os.path.basename(filepath)
                base_name, current_version = get_version_from_filename(filename)

                rig_found = False
                for rig_id, rig_data in database["rigs"].items():
                    if rig_id in base_name:
                        rig_found = True
                        latest_version = rig_data["latest_version"]
                        rig_name = rig_id.split('_')[-2]
                        break

                if not rig_found:
                    continue

                box = layout.box()

                header_row = box.row()
                header_row.scale_y = 1.2

                title_row = header_row.row()
                title_row.label(text="", icon='MESH_MONKEY')
                title_row.label(text=f"{rig_name} - v{current_version}")

                button_row = header_row.row(align=True)
                button_row.alignment = 'RIGHT'

                if latest_version > current_version:
                    button_row.operator(
                        "downloadrig.update",
                        text="",
                        icon='FILE_REFRESH',
                        emboss=True
                    ).filepath = filepath
                else:
                    button_row.label(text="", icon='CHECKMARK')

                versions_op = button_row.operator(
                    "downloadrig.show_versions",
                    text="",
                    icon='DOWNARROW_HLT',
                    emboss=True
                )
                versions_op.filepath = filepath

                path_row = box.row()
                path_row.scale_y = 0.8
                path_row.label(text=filepath, icon='FILE_FOLDER')
                path_row.enabled = False
        else:
            layout.label(text="Nenhum rig linkado", icon='INFO')

class DOWNLOADRIG_PT_download_panel(Panel):
    bl_label = "Baixar/Importar"
    bl_idname = "DOWNLOADRIG_PT_download_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'PeS'
    bl_options = {'DEFAULT_CLOSED'}
    bl_parent_id = "DOWNLOADRIG_PT_update_panel"  # Define o pai como o painel de atualização

    def draw(self, context):
        layout = self.layout

        database = load_rigs_database()
        for rig_id, rig_data in database["rigs"].items():
            box = layout.box()
            row = box.row()
            char_name = rig_id.split('_')[-2]
            row.label(text=char_name)
            row = box.row()
            row.label(text=f"Versão: v{rig_data['latest_version']}")
            if "description" in rig_data:
                row = box.row()
                row.label(text=rig_data["description"])

            row = box.row(align=True)
            download_op = row.operator(
                "downloadrig.download",
                text="Baixar",
                icon='IMPORT'
            )
            download_op.rig_id = rig_id

            link_op = row.operator(
                "downloadrig.download_and_link",
                text="Baixar e Importar",
                icon='LINKED'
            )
            link_op.rig_id = rig_id

classes = (
    DOWNLOADRIG_OT_download,
    DOWNLOADRIG_OT_download_and_link,
    DOWNLOADRIG_OT_update,
    DOWNLOADRIG_OT_change_version,
    DOWNLOADRIG_OT_show_versions,
    DOWNLOADRIG_PT_update_panel,
    DOWNLOADRIG_PT_download_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
