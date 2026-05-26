import asyncio
import logging
import httpx

logger = logging.getLogger(__name__)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

LEAK_SOURCES = {
    "emailrep": "https://emailrep.io/{}",
    "leakcheck": "https://leakcheck.io/api/public?check={}&type={}",
    "scylla": "https://scylla.so/api/search/{}",
    "intelx": "https://2.intelx.io/phonebook/search?k={}&limit=10&offset=0&type={}",
    "ghostproject": "https://ghostproject.fr/search.php",
    "leaklookup": "https://leak-lookup.com/api/search",
}

INTELX_TYPES = {"email": "email", "phone": "phone", "username": "login", "domain": "domain"}


async def leak_search(query: str, search_type: str = "auto") -> dict:
    """Search leaked databases using multiple sources."""
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
        tasks.append(_check_scylla(query, results))
        tasks.append(_check_intelx(query, "email", results))
        tasks.append(_check_ghostproject(query, results))

    elif search_type == "phone":
        phone_clean = query.replace("+", "").replace("-", "").replace(" ", "")
        tasks.append(_check_leakcheck(phone_clean, "phone", results))
        tasks.append(_check_intelx(phone_clean, "phone", results))
        tasks.append(_check_scylla(phone_clean, results))

    elif search_type == "username":
        tasks.append(_check_leakcheck(query, "username", results))
        tasks.append(_check_intelx(query, "username", results))
        tasks.append(_check_scylla(query, results))

    await asyncio.gather(*tasks)
    logger.info(f"leak_search({search_type}): {query} -> found={results['found']}, sources={results['sources']}")
    return results


async def _safe_get(url: str, params: dict = None, timeout: float = 12.0) -> httpx.Response | None:
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
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
                items.append(b.get("name", str(b)))
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
    r = await _safe_get(LEAK_SOURCES["leakcheck"].format(query, lt))
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


async def _check_scylla(query: str, results: dict):
    """Scylla.so — search engine for leaked credentials."""
    r = await _safe_get(LEAK_SOURCES["scylla"].format(query))
    if r and r.status_code == 200:
        try:
            data = r.json()
            if isinstance(data, list) and data:
                results["found"] = True
                results["sources"].append("Scylla.so")
                samples = []
                for entry in data[:5]:
                    line = f"{entry.get('email', '')}:{entry.get('password', '')}"[:120]
                    samples.append(line)
                results["details"].append({
                    "source": "Scylla.so", "count": len(data),
                    "sample": samples,
                })
        except:
            pass


async def _check_intelx(query: str, ix_type: str, results: dict):
    """Intelligence X — darknet/breach search."""
    t = INTELX_TYPES.get(ix_type, "login")
    r = await _safe_get(LEAK_SOURCES["intelx"].format(query, t))
    if r and r.status_code == 200:
        try:
            data = r.json()
            records = data.get("data", [])
            if records:
                results["found"] = True
                results["sources"].append("IntelX")
                samples = [str(r.get("value", ""))[:100] for r in records[:5]]
                results["details"].append({
                    "source": "IntelX", "count": len(records),
                    "sample": samples,
                })
        except:
            pass


async def _check_ghostproject(query: str, results: dict):
    """GhostProject.fr — email breach search."""
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.post(LEAK_SOURCES["ghostproject"], data={"param": query, "x": "0", "y": "0"},
                             headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"})
            if r.status_code == 200 and "found" in r.text.lower():
                text = r.text
                import re
                entries = re.findall(r'<td>([^<]+)</td>', text)
                if entries and len(entries) > 1:
                    results["found"] = True
                    results["sources"].append("GhostProject")
                    results["details"].append({
                        "source": "GhostProject", "count": len(entries) // 3,
                        "sample": entries[:6],
                    })
    except:
        pass
