import asyncio
import httpx
from legifrance_mcp import server
from legifrance_mcp.client import LegifranceClient


def make(handler):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    server._client = LegifranceClient("id", "secret", http=http)


def handler(req: httpx.Request) -> httpx.Response:
    if "oauth" in req.url.host:
        return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
    assert req.headers["authorization"] == "Bearer t"
    if req.url.path.endswith("/consult/getArticle"):
        return httpx.Response(200, json={"article": {
            "id": "LEGIARTI1", "num": "1240", "etat": "VIGUEUR", "dateDebut": 1456790400000,
            "texteHtml": "<p>Tout fait quelconque de l&apos;homme</p>"}})
    if req.url.path.endswith("/search"):
        return httpx.Response(200, json={"totalResultNumber": 1, "results": [
            {"title": "Article 1240", "origin": "LEGI", "titles": [{"id": "LEGIARTI1", "title": "Art 1240"}]}]})
    return httpx.Response(404, text="nope")


def test_search_and_article():
    make(handler)
    out = asyncio.run(server.rechercher("responsabilité", fond="CODE_DATE", date_version="2024-01-01"))
    assert "LEGIARTI1" in out
    out = asyncio.run(server.get_article("LEGIARTI1"))
    assert "Article 1240" in out and "2016-03-01" in out


def test_search_body_date_filter():
    b = server.build_search_body("x", "CODE_DATE", "EXACTE", 1, 10, "2024-01-01")
    assert b["recherche"]["filtres"][0]["singleDate"] == 1704067200000
    assert server.build_search_body("x", "JURI", "EXACTE", 1, 10, "2024-01-01")["recherche"]["filtres"] == []


def test_tools_registered():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert {"rechercher", "get_article", "get_code", "get_decision", "lister_codes"} <= names
