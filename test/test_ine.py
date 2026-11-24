import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from main import app
from src.ingestion.ine import (
    call_ckan,
    download_resource_file,
    get_dataset_resources,
    has_remote_changed,
    list_all_datasets,
    list_groups,
    query_datastore_sql,
    search_datasets,
    search_datastore
)

client = TestClient(app)


@patch("src.ingestion.ine.requests.get")
def test_call_ckan_success(mock_get):
    """Verificar ejecucion exitosa de call_ckan."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"success": True, "result": {"key": "val"}}
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    result = call_ckan("test_action", param1="test")
    assert result == {"key": "val"}
    mock_get.assert_called_once()


@patch("src.ingestion.ine.requests.get")
def test_call_ckan_error(mock_get):
    """Verificar manejo de error cuando ckan devuelve success false."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"success": False, "error": {"message": "not found"}}
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    with pytest.raises(RuntimeError) as exc_info:
        call_ckan("invalid_action")
    assert "ckan devolvio error" in str(exc_info.value)


@patch("src.ingestion.ine.call_ckan")
def test_search_datasets(mock_call):
    """Verificar busqueda y normalizacion de conjuntos de datos con filas por defecto de 10."""
    mock_call.return_value = {
        "count": 1,
        "results": [
            {
                "name": "censo-2025",
                "title": "censo nacional 2025",
                "notes": "datos censales",
                "author": "ine",
                "organization": {"title": "demografia"},
                "metadata_modified": "2025-01-10T00:00:00",
                "resources": [
                    {
                        "id": "res-123",
                        "name": "censo.csv",
                        "format": "CSV",
                        "url": "https://datos.ine.gob.gt/files/censo.csv",
                        "last_modified": "2025-01-10T00:00:00"
                    }
                ]
            }
        ]
    }

    result = search_datasets(query="2025")
    assert result["total"] == 1
    assert result["filas"] == 10
    assert result["conjuntos"][0]["id"] == "censo-2025"
    assert result["conjuntos"][0]["recursos_total"] == 1
    assert result["conjuntos"][0]["recursos"][0]["formato"] == "csv"


@patch("src.ingestion.ine.search_datasets")
def test_list_all_datasets(mock_search):
    """Verificar paginacion automatica de conjuntos de datos."""
    mock_search.side_effect = [
        {"total": 2, "conjuntos": [{"id": "pkg-1"}]},
        {"total": 2, "conjuntos": [{"id": "pkg-2"}]}
    ]

    all_pkgs = list_all_datasets(rows_per_page=1, pause_seconds=0.01, max_total=2)
    assert len(all_pkgs) == 2
    assert all_pkgs[0]["id"] == "pkg-1"
    assert all_pkgs[1]["id"] == "pkg-2"


@patch("src.ingestion.ine.call_ckan")
def test_list_groups(mock_call):
    """Verificar extraccion de grupos tematicos."""
    mock_call.return_value = [
        {"id": "g-1", "name": "demografia", "title": "Demografia", "package_count": 12}
    ]

    groups = list_groups()
    assert len(groups) == 1
    assert groups[0]["nombre"] == "demografia"
    assert groups[0]["total_paquetes"] == 12


@patch("src.ingestion.ine.call_ckan")
def test_get_dataset_resources(mock_call):
    """Verificar obtencion de recursos de un conjunto."""
    mock_call.return_value = {
        "metadata_modified": "2025-02-01T12:00:00",
        "license_id": "cc-by",
        "resources": [
            {
                "id": "res-abc",
                "name": "tabla-1.xlsx",
                "format": "XLSX",
                "url": "https://datos.ine.gob.gt/files/tabla-1.xlsx",
                "last_modified": "2025-02-01T12:00:00"
            }
        ]
    }

    res_list = get_dataset_resources("censo-2025")
    assert len(res_list) == 1
    assert res_list[0]["id"] == "res-abc"
    assert res_list[0]["dataset"] == "censo-2025"
    assert res_list[0]["license"] == "cc-by"


def test_download_and_remote_change(tmp_path):
    """Verificar descarga de recurso y registro de procedencia en manifest."""
    mock_content = b"header1,header2\nval1,val2\n"

    with patch("src.ingestion.ine.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [mock_content]
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value.__enter__.return_value = mock_resp

        resource = {
            "id": "res-999",
            "name": "datos.csv",
            "format": "csv",
            "url": "https://datos.ine.gob.gt/download/datos.csv",
            "last_modified": "2025-05-01T00:00:00",
            "dataset": "dataset-prueba"
        }

        # primera descarga del archivo
        downloaded_file = download_resource_file(resource, base_dir=tmp_path)
        assert downloaded_file.exists()
        assert downloaded_file.read_bytes() == mock_content

        manifest_file = tmp_path / "manifest.jsonl"
        assert manifest_file.exists()

        # verificar que no hay cambio remoto con la misma fecha
        assert has_remote_changed(resource, base_dir=tmp_path) is False

        # verificar que reporta cambio remoto si la fecha remota cambia
        resource_updated = {**resource, "last_modified": "2025-06-01T00:00:00"}
        assert has_remote_changed(resource_updated, base_dir=tmp_path) is True


@patch("src.ingestion.ine.call_ckan")
def test_search_datastore(mock_call):
    """Verificar consulta a datastore_search con limite predeterminado de 10."""
    mock_call.return_value = {
        "total": 5,
        "fields": [{"id": "_id", "type": "int"}, {"id": "title", "type": "text"}],
        "records": [{"_id": 1, "title": "jones"}]
    }

    res = search_datastore("2ffc0ffd-74f5-4cae-bbd8-6fa0698e3492", query="jones")
    assert res["total"] == 5
    assert res["limite"] == 10
    assert len(res["registros"]) == 1
    assert res["registros"][0]["title"] == "jones"


@patch("src.ingestion.ine.call_ckan")
def test_query_datastore_sql(mock_call):
    """Verificar consulta a datastore_search_sql."""
    mock_call.return_value = {
        "fields": [{"id": "count", "type": "int"}],
        "records": [{"count": 120}]
    }

    res = query_datastore_sql('select count(*) from "tabla"')
    assert res["registros"] == [{"count": 120}]


@patch("src.api.v1.endpoints.ine_router.search_datasets")
def test_api_get_datasets(mock_search):
    """Verificar endpoint fastapi /api/v1/ine/conjuntos con limite por defecto de 10."""
    mock_search.return_value = {
        "total": 1,
        "inicio": 0,
        "filas": 10,
        "conjuntos": [{"id": "test-dataset", "nombre": "test"}]
    }

    resp = client.get("/api/v1/ine/conjuntos?consulta=2025")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["filas"] == 10
    assert data["conjuntos"][0]["id"] == "test-dataset"

    # probar tambien ruta directa /ine/conjuntos
    resp_direct = client.get("/ine/conjuntos?consulta=2025")
    assert resp_direct.status_code == 200


@patch("src.api.v1.endpoints.ine_router.list_groups")
def test_api_get_groups(mock_groups):
    """Verificar endpoint fastapi /api/v1/ine/grupos."""
    mock_groups.return_value = [{"id": "g-1", "nombre": "demografia"}]

    resp = client.get("/api/v1/ine/grupos")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@patch("src.api.v1.endpoints.ine_router.get_dataset_resources")
def test_api_get_resources(mock_res):
    """Verificar endpoint fastapi /api/v1/ine/{slug}/recursos."""
    mock_res.return_value = [{"id": "res-1", "nombre": "archivo.csv"}]

    resp = client.get("/api/v1/ine/censo-2025/recursos")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dataset"] == "censo-2025"
    assert len(data["recursos"]) == 1


@patch("src.api.v1.endpoints.ine_router.download_resource_file")
@patch("src.api.v1.endpoints.ine_router.get_dataset_resources")
def test_api_download_resource(mock_res, mock_download, tmp_path):
    """Verificar endpoint de descarga y que no lanza error de indices de string."""
    fake_file = tmp_path / "censo.csv"
    fake_file.write_bytes(b"col1,col2\n1,2")

    mock_res.return_value = [
        {"id": "res-ok", "nombre": "censo.csv", "dataset": "censo-2025", "url": "https://example.com/censo.csv"}
    ]
    mock_download.return_value = fake_file

    # probar endpoint con metodo post y get
    resp_post = client.post("/api/v1/ine/censo-2025/descargar/res-ok")
    assert resp_post.status_code == 200
    assert resp_post.content == b"col1,col2\n1,2"

    resp_get = client.get("/api/v1/ine/censo-2025/descargar/res-ok")
    assert resp_get.status_code == 200
    assert resp_get.content == b"col1,col2\n1,2"

    # probar respuesta cuando el recurso no existe
    resp_404 = client.get("/api/v1/ine/censo-2025/descargar/recurso-inexistente")
    assert resp_404.status_code == 404


@patch("src.api.v1.endpoints.ine_router.has_remote_changed")
@patch("src.api.v1.endpoints.ine_router.get_dataset_resources")
def test_api_check_remote_change(mock_res, mock_change):
    """Verificar endpoint fastapi para verificar cambios remotos."""
    mock_res.return_value = [{"id": "res-ok", "last_modified": "2025-01-01"}]
    mock_change.return_value = True

    resp = client.get("/api/v1/ine/censo-2025/verificar-cambio/res-ok")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cambio_remoto"] is True


@patch("src.api.v1.endpoints.ine_router.search_datastore")
def test_api_datastore_endpoints(mock_ds):
    """Verificar endpoints de datastore tanto get como post con limite por defecto de 10."""
    mock_ds.return_value = {"total": 1, "registros": [{"item": 1}]}

    # prueba de endpoint mediante metodo get
    resp_get = client.get("/api/v1/ine/datastore/consulta?recurso_id=res-123")
    assert resp_get.status_code == 200
    assert resp_get.json()["total"] == 1
    mock_ds.assert_called_with(resource_id="res-123", limit=10, offset=0, query=None)

    # prueba de endpoint mediante metodo post
    resp_post = client.post(
        "/api/v1/ine/datastore/consulta",
        json={"recurso_id": "res-123", "limite": 10, "desplazamiento": 0}
    )
    assert resp_post.status_code == 200
    assert resp_post.json()["total"] == 1


@patch("src.api.v1.endpoints.ine_router.query_datastore_sql")
def test_api_datastore_sql_endpoints(mock_sql):
    """Verificar endpoints de consulta sql tanto get como post."""
    mock_sql.return_value = {"registros": [{"resultado": "ok"}]}

    resp_get = client.get('/api/v1/ine/datastore/consulta-sql?sql=select * from "tabla"')
    assert resp_get.status_code == 200

    resp_post = client.post(
        "/api/v1/ine/datastore/consulta-sql",
        json={"sql": 'select * from "tabla"'}
    )
    assert resp_post.status_code == 200


@patch("src.api.v1.endpoints.ine_router.get_dataset_resources")
@patch("src.api.v1.endpoints.ine_router.search_datastore")
def test_api_preview_dataset_datastore(mock_ds, mock_res):
    """Verificar vista previa directa de recurso indexado en datastore sin descarga."""
    mock_res.return_value = [
        {"id": "res-1", "nombre": "Recurso 1", "formato": "xlsx", "url": "https://example.com/r1.xlsx"}
    ]
    mock_ds.return_value = {
        "fields": [{"id": "col1"}, {"id": "col2"}],
        "records": [{"col1": "A", "col2": 1}]
    }

    resp = client.get("/api/v1/ine/slug-prueba/vista-previa?limite=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["origen"] == "datastore_ckan"
    assert data["columnas"] == ["col1", "col2"]
    assert len(data["filas_muestra"]) == 1


@patch("src.api.v1.endpoints.ine_router.get_dataset_resources")
@patch("src.api.v1.endpoints.ine_router.search_datastore")
@patch("src.api.v1.endpoints.ine_router.download_resource_file")
@patch("src.api.v1.endpoints.ine_router.read_excel_sheets")
def test_api_preview_dataset_autodownload(mock_read, mock_dl, mock_ds, mock_res, tmp_path):
    """Verificar vista previa directa con descarga automatica transparente cuando no esta en datastore."""
    mock_res.return_value = [
        {"id": "res-1", "nombre": "Archivo Excel", "formato": "xlsx", "url": "https://example.com/test.xlsx"}
    ]
    mock_ds.side_effect = Exception("no datastore")

    fake_file = tmp_path / "test.xlsx"
    fake_file.write_bytes(b"EXCEL_DATA")
    mock_dl.return_value = fake_file

    mock_df = MagicMock()
    mock_df.columns = ["departamento", "accidentes"]
    mock_df.head.return_value.to_dicts.return_value = [{"departamento": "Guatemala", "accidentes": 50}]
    mock_read.side_effect = [
        {"hoja1": MagicMock()},
        mock_df
    ]

    resp = client.get("/api/v1/ine/slug-prueba/vista-previa?limite=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["origen"] == "archivo_local_autodescargado"
    assert data["columnas"] == ["departamento", "accidentes"]
    assert len(data["filas_muestra"]) == 1


@patch("src.api.v1.endpoints.ine_router.get_dataset_resources")
@patch("src.api.v1.endpoints.ine_router.search_datastore")
def test_api_preview_dataset_datastore_spanish_keys(mock_ds, mock_res):
    """Verificar vista previa cuando search_datastore retorna llaves normalizadas en espanol (campos y registros)."""
    mock_res.return_value = [
        {"id": "res-es", "nombre": "Recurso ES", "formato": "csv", "url": "https://example.com/r.csv"}
    ]
    mock_ds.return_value = {
        "campos": [{"id": "depto"}, {"id": "total"}],
        "registros": [{"depto": "Guatemala", "total": 100}]
    }

    resp = client.get("/api/v1/ine/slug-es/vista-previa?limite=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["origen"] == "datastore_ckan"
    assert data["columnas"] == ["depto", "total"]
    assert data["filas_muestra"] == [{"depto": "Guatemala", "total": 100}]


def test_api_root_and_health_endpoints():
    """Verificar endpoints de estado raiz (/), salud (/health) y documentacion scalar (/docs)."""
    resp_home = client.get("/", follow_redirects=False)
    assert resp_home.status_code in (302, 307)

    resp_health = client.get("/health")
    assert resp_health.status_code == 200
    health_data = resp_health.json()
    assert health_data["status"] == "ok"
    assert "Balam Data Systems" in health_data["service"]

    resp_docs = client.get("/docs")
    assert resp_docs.status_code == 200
    assert "text/html" in resp_docs.headers.get("content-type", "")

