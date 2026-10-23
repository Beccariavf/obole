"""Couche MCP (surface de pilotage IA) — transport à sens unique vers `services/`.

Invariant de couche (`CLAUDE.md`, `PRD.md` §12.1) : `mcp/` est une **couche de
transport**, jamais un cœur. Elle expose des *verbes* à une IA cliente et délègue
toute logique à `services/` / `engine/` / `data/` — elle n'importe JAMAIS `api/`
ni `web/` (le MCP ne passe pas par HTTP).
"""
