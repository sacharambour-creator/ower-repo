"""MCP server exposing the Légifrance API (codes, lois, jurisprudence)."""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timezone
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .client import LegifranceClient

MAX_CHARS = 20000

_secret = os.environ.get("MCP_PATH_SECRET", "").strip("/")
mcp = FastMCP(
    "legifrance",
    host=os.environ.get("HOST", "0.0.0.0"),
    port=int(os.environ.get("PORT", "8000")),
    streamable_http_path=f"/{_secret}/mcp" if _secret else "/mcp",
    stateless_http=True,
)

_client: LegifranceClient | None = None


def client() -> LegifranceClient:
    global _client
    if _client is None:
        _client = LegifranceClient()
    return _client


def _html_to_text(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = (
        s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
        .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    )
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def _ms(d: str | None) -> int:
    """ISO date (YYYY-MM-DD) → epoch milliseconds; default today."""
    dt = datetime.fromisoformat(d) if d else datetime.combine(date.today(), datetime.min.time())
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _fmt_ms(v: Any) -> str | None:
    if isinstance(v, (int, float)) and v > 0:
        return datetime.fromtimestamp(v / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    return None


def _truncate(s: str) -> str:
    if len(s) <= MAX_CHARS:
        return s
    return s[:MAX_CHARS] + f"\n\n[… tronqué à {MAX_CHARS} caractères]"


Fond = Literal[
    "ALL", "CODE_DATE", "CODE_ETAT", "LODA_DATE", "LODA_ETAT", "JURI", "CETAT",
    "CONSTIT", "JORF", "CIRC", "ACCO", "KALI",
]


def build_search_body(
    query: str,
    fond: str,
    search_type: str,
    page: int,
    page_size: int,
    date_version: str | None,
) -> dict[str, Any]:
    filtres: list[dict[str, Any]] = []
    if date_version and fond.endswith("_DATE"):
        filtres.append({"facette": "DATE_VERSION", "singleDate": _ms(date_version)})
    return {
        "fond": fond,
        "recherche": {
            "champs": [
                {
                    "typeChamp": "ALL",
                    "criteres": [
                        {"typeRecherche": search_type, "valeur": query, "operateur": "ET"}
                    ],
                    "operateur": "ET",
                }
            ],
            "filtres": filtres,
            "pageNumber": page,
            "pageSize": page_size,
            "operateur": "ET",
            "sort": "PERTINENCE",
            "typePagination": "DEFAUT",
        },
    }


@mcp.tool()
async def rechercher(
    query: str,
    fond: Fond = "ALL",
    type_recherche: Literal[
        "UN_DES_MOTS", "TOUS_LES_MOTS_DANS_UN_CHAMP", "EXACTE", "AUCUN_DES_MOTS"
    ] = "TOUS_LES_MOTS_DANS_UN_CHAMP",
    page: int = 1,
    page_size: int = 10,
    date_version: str | None = None,
) -> str:
    """Recherche dans Légifrance.

    fond : ALL (tout), CODE_DATE (codes en vigueur à une date), LODA_DATE (lois et
    décrets), JURI (jurisprudence judiciaire), CETAT (Conseil d'État), CONSTIT
    (Conseil constitutionnel), JORF (Journal officiel), KALI (conventions
    collectives), CIRC (circulaires), ACCO (accords d'entreprise).
    date_version : AAAA-MM-JJ (fonds *_DATE uniquement).
    Retourne les identifiants (LEGIARTI…, LEGITEXT…, JURITEXT…) à passer aux autres outils.
    """
    body = build_search_body(query, fond, type_recherche, page, min(page_size, 50), date_version)
    data = await client().post("/search", body)
    lines = [f"{data.get('totalResultNumber', 0)} résultat(s) — page {page}"]
    for r in data.get("results", []):
        title = _html_to_text(r.get("title") or "")
        titles = r.get("titles") or []
        ids = ", ".join(f"{t.get('id')} ({_html_to_text(t.get('title'))})" for t in titles if t.get("id"))
        lines.append(f"- {title}\n  origine: {r.get('origin')} | nature: {r.get('nature') or '-'}"
                     f" | date: {_fmt_ms(r.get('date')) or '-'}"
                     + (f"\n  ids: {ids}" if ids else ""))
        for sec in r.get("sections", [])[:3]:
            for ex in (sec.get("extracts") or [])[:2]:
                txt = _html_to_text(ex.get("values", [""])[0] if ex.get("values") else "")
                if txt:
                    lines.append(f"  > {txt[:300]}")
    return _truncate("\n".join(lines))


@mcp.tool()
async def get_article(article_id: str) -> str:
    """Texte complet d'un article (id LEGIARTI…, JORFARTI…, etc.) avec sa version, ses dates de vigueur et son état."""
    data = await client().post("/consult/getArticle", {"id": article_id})
    a = data.get("article") or {}
    head = (
        f"Article {a.get('num') or ''} — {a.get('id')}\n"
        f"Texte: {a.get('textTitles', [{}])[0].get('titre', '') if a.get('textTitles') else ''}\n"
        f"État: {a.get('etat')} | du {_fmt_ms(a.get('dateDebut'))} au {_fmt_ms(a.get('dateFin'))}\n\n"
    )
    return _truncate(head + _html_to_text(a.get("texteHtml") or a.get("texte")))


@mcp.tool()
async def get_code(text_id: str, date_version: str | None = None, section_id: str | None = None) -> str:
    """Sommaire (table des matières) d'un code à une date donnée (AAAA-MM-JJ, défaut: aujourd'hui).

    text_id : LEGITEXT… (ex. LEGITEXT000006070721 = Code civil). Si section_id (LEGISCTA…)
    est fourni, retourne cette section avec ses articles.
    """
    if section_id:
        data = await client().post(
            "/consult/legiPart", {"textId": text_id, "date": _ms(date_version), "sectionId": section_id}
        )
    else:
        data = await client().post("/consult/legiPart", {"textId": text_id, "date": _ms(date_version)})
    out: list[str] = [_html_to_text(data.get("title") or "")]

    def walk(sections: list[dict[str, Any]], depth: int) -> None:
        for s in sections or []:
            out.append(f"{'  ' * depth}[{s.get('id')}] {_html_to_text(s.get('title'))}")
            for art in s.get("articles") or []:
                out.append(f"{'  ' * (depth + 1)}Art. {art.get('num')} ({art.get('id')})")
            walk(s.get("sections") or [], depth + 1)

    for art in data.get("articles") or []:
        out.append(f"Art. {art.get('num')} ({art.get('id')})")
    walk(data.get("sections") or [], 0)
    return _truncate("\n".join(out))


@mcp.tool()
async def get_article_by_number(code_text_id: str, article_num: str, date_version: str | None = None) -> str:
    """Retrouve un article par son numéro (ex. '1240', 'L121-1') dans un code, à une date donnée, puis renvoie son texte.

    code_text_id : LEGITEXT… du code.
    """
    data = await client().post(
        "/search",
        {
            "fond": "CODE_DATE",
            "recherche": {
                "champs": [
                    {
                        "typeChamp": "NUM_ARTICLE",
                        "criteres": [{"typeRecherche": "EXACTE", "valeur": article_num, "operateur": "ET"}],
                        "operateur": "ET",
                    }
                ],
                "filtres": [
                    {"facette": "DATE_VERSION", "singleDate": _ms(date_version)},
                    {"facette": "TEXT_ID", "valeur": code_text_id},
                ],
                "pageNumber": 1,
                "pageSize": 5,
                "operateur": "ET",
                "sort": "PERTINENCE",
                "typePagination": "ARTICLE",
            },
        },
    )
    for r in data.get("results", []):
        for t in r.get("titles") or []:
            if t.get("id", "").startswith("LEGIARTI"):
                return await get_article(t["id"])
    return f"Aucun article '{article_num}' trouvé dans {code_text_id}."


@mcp.tool()
async def get_decision(decision_id: str) -> str:
    """Texte intégral d'une décision de justice (id JURITEXT…, CETATEXT…, CONSTEXT…)."""
    data = await client().post("/consult/juri", {"textId": decision_id})
    t = data.get("text") or {}
    head = (
        f"{t.get('titre') or t.get('titreJuri') or decision_id}\n"
        f"Juridiction: {t.get('juridiction')} | Date: {_fmt_ms(t.get('dateTexte')) or t.get('dateTexte')}"
        f" | N°: {t.get('numero') or t.get('numeroAffaire') or '-'}\n\n"
    )
    return _truncate(head + _html_to_text(t.get("texteHtml") or t.get("texte")))


@mcp.tool()
async def get_texte(text_id: str, date_version: str | None = None) -> str:
    """Sommaire d'une loi, d'un décret, d'une ordonnance ou d'un arrêté (id LEGITEXT… / JORFTEXT…)."""
    data = await client().post("/consult/lawDecree", {"textId": text_id, "date": _ms(date_version)})
    out = [_html_to_text(data.get("title") or "")]

    def walk(sections: list[dict[str, Any]], depth: int) -> None:
        for s in sections or []:
            out.append(f"{'  ' * depth}[{s.get('id')}] {_html_to_text(s.get('title'))}")
            for art in s.get("articles") or []:
                out.append(f"{'  ' * (depth + 1)}Art. {art.get('num')} ({art.get('id')})")
            walk(s.get("sections") or [], depth + 1)

    for art in data.get("articles") or []:
        out.append(f"Art. {art.get('num')} ({art.get('id')})")
    walk(data.get("sections") or [], 0)
    return _truncate("\n".join(out))


@mcp.tool()
async def lister_codes(query: str = "", page_size: int = 50) -> str:
    """Liste les codes disponibles (nom, id LEGITEXT…, état), filtrables par nom."""
    data = await client().post(
        "/list/code",
        {"codeName": query, "pageNumber": 1, "pageSize": min(page_size, 100),
         "sort": "TITLE_ASC", "states": ["VIGUEUR"]},
    )
    rows = [f"- {r.get('titre')} — {r.get('id') or r.get('cid')}" for r in data.get("results", [])]
    return "\n".join(rows) or "Aucun code trouvé."


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
