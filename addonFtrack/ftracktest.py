import os
import ftrack_api
from config import SERVER_URL, USERNAME, API_KEY

class FtrackUploader:
    def __init__(self, session):
        """
        Inicializa o uploader com uma sessão do Ftrack

        :param session: Sessão do Ftrack
        """
        self.session = session
        self.server_location = self._get_location('ftrack.server')
        self.origin_location = self._get_location('ftrack.origin')

    def _get_location(self, location_name):
        """
        Busca uma localização específica

        :param location_name: Nome da localização
        :return: Objeto de localização
        """
        location = self.session.query(f'Location where name is "{location_name}"').first()
        if not location:
            raise ValueError(f"Localização '{location_name}' não encontrada")
        return location

    def _get_or_create_asset(self, asset_name, project, asset_type):
        """
        Busca ou cria um asset

        :param asset_name: Nome do asset
        :param project: Projeto do Ftrack
        :param asset_type: Tipo do asset
        :return: Asset existente ou recém-criado
        """
        existing_asset = self.session.query(
            f'Asset where name is "{asset_name}" and type.name is "Upload" and parent.id is "{project["id"]}"'
        ).first()

        if existing_asset:
            print(f"Asset '{asset_name}' já existe. Usando o asset existente.")
            return existing_asset

        return self.session.create('Asset', {
            'name': asset_name,
            'type': asset_type,
            'parent': project
        })

    def upload_and_encode(self, task_id, file_path, asset_name=None):
        """
        Faz upload e encode de um arquivo para o Ftrack

        :param task_id: ID da task
        :param file_path: Caminho do arquivo
        :param asset_name: Nome opcional do asset
        :return: Dicionário com detalhes do upload
        """
        # Validações iniciais
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

        # Determinar nomes
        file_name = os.path.splitext(os.path.basename(file_path))[0]
        asset_name = asset_name or file_name

        # Buscar objetos do Ftrack
        task = self.session.query(f'Task where id is "{task_id}"').first()
        project = self.session.query(f'Project where id is "{task["project"]["id"]}"').first()
        asset_type = self.session.query('AssetType where name is "Upload"').first()

        # Criar ou buscar asset
        asset = self._get_or_create_asset(asset_name, project, asset_type)

        # Determinar número da versão
        version_count = len(self.session.query(f'AssetVersion where asset.id is "{asset["id"]}"').all())
        next_version = version_count + 1

        # Criar versão do asset
        asset_version = self.session.create('AssetVersion', {
            'asset': asset,
            'task': task,
            'version': next_version,
            'comment': f'Upload de {os.path.basename(file_path)}'
        })

        # Criar componente
        component = asset_version.create_component(file_path)

        # Definir nome do componente
        try:
            component['name'] = os.path.basename(file_path)
        except Exception as name_error:
            print(f"Erro ao definir nome do componente: {name_error}")

        # Commit das mudanças
        self.session.commit()

        # Transferir para localização do servidor
        try:
            self.server_location.add_components([component], sources=[self.origin_location])
            self.session.commit()
        except Exception as transfer_error:
            print(f"Erro ao transferir componente: {transfer_error}")

        # Tentar encode
        encode_job = self._try_encode(component, asset_version)

        # Preparar resultado
        return {
            'task_name': task['name'],
            'project_name': project['name'],
            'asset_name': asset['name'],
            'asset_version_number': asset_version['version'],
            'asset_version_id': asset_version['id'],
            'component_id': component['id'],
            'component_name': component.get('name', 'Sem nome'),
            'encode_job_id': encode_job['id'] if encode_job else None,
            'encode_job_data': str(encode_job) if encode_job else None
        }

    def _try_encode(self, component, asset_version):
        """
        Tenta fazer encode do componente

        :param component: Componente do Ftrack
        :param asset_version: Versão do asset
        :return: Job de encode ou None
        """
        try:
            encode_job = self.session.encode_media(
                component,
                version_id=asset_version['id'],
                keep_original=True
            )
            self.session.commit()
            return encode_job
        except Exception as encode_error:
            print(f"Erro ao iniciar encode: {encode_error}")

            # Tentar encode sem especificar version_id
            try:
                encode_job = self.session.encode_media(
                    component,
                    keep_original=True
                )
                self.session.commit()
                return encode_job
            except Exception as fallback_error:
                print(f"Erro no fallback de encode: {fallback_error}")
                return None

def main():
    try:
        # Criar sessão do ftrack
        session = ftrack_api.Session(
            server_url=SERVER_URL,
            api_key=API_KEY,
            api_user=USERNAME
        )

        # Criar uploader
        uploader = FtrackUploader(session)

        # ID da task e caminho do arquivo
        TASK_ID = "eca8b1db-ded1-43f7-aa70-b19df97fd9c8"
        FILE_PATH = r"C:\Users\Igor\Pictures\Screenshots\Captura de tela 2025-02-11 185553.png"

        # Fazer upload e encode
        result = uploader.upload_and_encode(TASK_ID, FILE_PATH)

        # Imprimir detalhes do upload
        print("Detalhes do upload e encode:")
        for key, value in result.items():
            print(f"{key}: {value}")

    except Exception as e:
        print(f"Erro geral: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Sempre fechar a sessão
        if 'session' in locals():
            session.close()

if __name__ == "__main__":
    main()
