import asyncio
import logging
import httpx
import re

logger = logging.getLogger(__name__)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Только реально работающие публичные источники утечек
LEAK_SOURCES = {
    "emailrep": "https://emailrep.io/{}",
    "leakcheck": "https://leakcheck.io/api/public?check={}&type={}",
    "ghostproject": "https://ghostproject.fr/search.php",
    "leakpeek": "https://leakpeek.com/api?q={}",
}

LEAKCHECK_TYPES = {"email": "email", "phone": "phone", "username": "login"}


async def leak_search(query: str, search_type: str = "auto") -> dict:
    query = query.strip().lower()
    results = {"query": query, "found": False, "sources": [], "details": []}

    if search_type == "auto":
        if "@" in query:
            search_type = "email"
        elif query.replace("+", "").replace("-", "").replace(" ", "").isdigit():
            search_type = "phone"
        else:
            search_type = "username"

    tasks = []

    if search_type == "email":
        tasks.append(_check_emailrep(query, results))
        tasks.append(_check_leakcheck(query, "email", results))
        tasks.append(_check_ghostproject(query, results))
    elif search_type == "phone":
        phone_clean = query.replace("+", "").replace("-", "").replace(" ", "")
        tasks.append(_check_leakcheck(phone_clean, "phone", results))
    elif search_type == "username":
        tasks.append(_check_leakcheck(query, "username", results))

    await asyncio.gather(*tasks)
    results["sources"] = list(dict.fromkeys(results["sources"]))
    log_msg = f"leak_search({search_type}): {query} -> found={results['found']}, sources={results['sources']}"
    logger.info(log_msg)
    return results


async def _safe_get(url: str, params: dict = None, timeout: float = 15.0) -> httpx.Response | None:
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
            r = await c.get(url, params=params, headers={"User-Agent": USER_AGENT})
            return r
    except:
        return None


async def _check_emailrep(query: str, results: dict):
    r = await _safe_get(LEAK_SOURCES["emailrep"].format(query))
    if r and r.status_code == 200:
        try:
            data = r.json()
            rep = data.get("reputation", "unknown")
            suspicious = data.get("suspicious", False)
            details = data.get("details", {})
            credentials_leaked = details.get("credentials_leaked", False)
            breaches = details.get("breaches", [])
            items = []
            if credentials_leaked:
                items.append("Credentials leaked")
            for b in breaches[:10]:
                if isinstance(b, dict):
                    items.append(b.get("name", str(b)))
                else:
                    items.append(str(b))
            if items:
                results["found"] = True
                results["sources"].append("EmailRep.io")
                results["details"].append({
                    "source": "EmailRep.io", "reputation": rep,
                    "suspicious": suspicious, "breaches": items,
                })
        except:
            pass


async def _check_leakcheck(query: str, lt: str, results: dict):
    mapped = LEAKCHECK_TYPES.get(lt, lt)
    r = await _safe_get(LEAK_SOURCES["leakcheck"].format(query, mapped))
    if r and r.status_code == 200:
        try:
            data = r.json()
            if data.get("success") and data.get("data"):
                lines = data["data"]
                if isinstance(lines, list) and lines:
                    results["found"] = True
                    results["sources"].append("LeakCheck")
                    results["details"].append({
                        "source": "LeakCheck", "count": len(lines),
                        "sample": [str(s)[:120] for s in lines[:5]],
                    })
        except:
            pass


async def _check_ghostproject(query: str, results: dict):
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
            r = await c.post(LEAK_SOURCES["ghostproject"],
                             data={"param": query, "x": "0", "y": "0"},
                             headers={"User-Agent": USER_AGENT,
                                      "Content-Type": "application/x-www-form-urlencoded",
                                      "Referer": "https://ghostproject.fr/"})
            if r.status_code == 200:
                text = r.text
                if "found" in text.lower() or query in text.lower():
                    entries = re.findall(r'<td>([^<]*)</td>', text)
                    pw_entries = re.findall(r'<td[^>]*>([^<]*)</td>', text)
                    if entries and len(entries) > 1:
                        results["found"] = True
                        results["sources"].append("GhostProject")
                        results["details"].append({
                            "source": "GhostProject", "count": len(entries) // 2,
                            "sample": [e.strip()[:100] for e in entries[:6] if e.strip()],
                        })
    except:
        pass
