import chromadb
from chromadb.utils import embedding_functions
from app.config import get_settings

_client = None


def get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        settings = get_settings()
        _client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    return _client


def _ef():
    return embedding_functions.DefaultEmbeddingFunction()


def upsert_documents(namespace: str, session_id: str, docs: list[str], ids: list[str]):
    client = get_client()
    collection = client.get_or_create_collection(
        name=f"{namespace}_{session_id}",
        embedding_function=_ef(),
    )
    collection.upsert(documents=docs, ids=ids)


def query_documents(namespace: str, session_id: str, query: str, n_results: int = 5) -> list[str]:
    client = get_client()
    try:
        collection = client.get_collection(
            name=f"{namespace}_{session_id}",
            embedding_function=_ef(),
        )
        results = collection.query(query_texts=[query], n_results=n_results)
        return results["documents"][0] if results["documents"] else []
    except Exception:
        return []


def delete_session(session_id: str, namespaces: list[str]):
    client = get_client()
    for ns in namespaces:
        try:
            client.delete_collection(f"{ns}_{session_id}")
        except Exception:
            pass
