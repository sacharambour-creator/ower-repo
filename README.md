# Serveur MCP Légifrance

Serveur MCP (Python, transport *streamable HTTP*) qui encapsule l'API Légifrance (PISTE).

Outils : `rechercher`, `get_article`, `get_article_by_number`, `get_code`, `get_texte`, `get_decision`, `lister_codes`.

## 1. Obtenir les identifiants PISTE
1. Créer un compte sur <https://piste.gouv.fr>, créer une application et souscrire à l'API **Légifrance**.
2. Récupérer `client_id` / `client_secret` (OAuth2 *client credentials*).

## 2. Lancer le serveur
```bash
pip install -r requirements.txt
export LEGIFRANCE_CLIENT_ID=... LEGIFRANCE_CLIENT_SECRET=...
export MCP_PATH_SECRET=$(openssl rand -hex 16)   # recommandé : rend l'URL non devinable
python -m legifrance_mcp.server                   # écoute sur :8000
```
Variables : `PORT` (8000), `HOST` (0.0.0.0), `LEGIFRANCE_SANDBOX=1` (bac à sable PISTE).
Endpoint MCP : `/<MCP_PATH_SECRET>/mcp` (ou `/mcp` si le secret n'est pas défini).

Docker : `docker build -t legifrance-mcp . && docker run -p 8000:8000 --env-file .env legifrance-mcp`

## 3. Exposer en HTTPS
Claude.ai a besoin d'une URL HTTPS publique. Déployer sur Fly.io / Render / Railway / Cloud Run
(le Dockerfile suffit), ou en test local : `cloudflared tunnel --url http://localhost:8000`.

## 4. Ajouter le connecteur dans Claude.ai
**Settings → Connectors → Add custom connector** → nom `Légifrance`,
URL `https://<votre-domaine>/<MCP_PATH_SECRET>/mcp` → Add. Activer ensuite le connecteur dans la conversation.

> Les connecteurs personnalisés de Claude.ai ne permettent pas d'en-tête d'authentification arbitraire
> (OAuth uniquement) : le secret dans le chemin d'URL protège l'accès. Ne le partagez pas.

## Tests
`pip install pytest && pytest`
