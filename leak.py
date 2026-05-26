import asyncio
import logging
import httpx

logger = logging.getLogger(__name__)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

SOURCES = {
    "emailrep": "https://emailrep.io/{}",
    "leakcheck": "https://leakcheck.io/api/public?check={}&type={}",
    "scylla": "https://scylla.so/api/search/{}",
}


async def leak_search(query: str, search_type: str = "auto") -> dict:
    """Search leaked databases. search_type: email/phone/username/auto."""
    query = query.strip().lower()
    results = {"query": query, "found": False, "sources": [], "details": []}

    tasks = []

    if search_type == "auto":
        if "@" in query:
            search_type = "email"
        elif query.replace("+", "").replace("-", "").replace(" ", "").isdigit():
            search_type = "phone"
        else:
            search_type = "username"

    if search_type == "email":
        tasks.append(_check_emailrep(query, results))
        tasks.append(_check_leakcheck(query, "email", results))

    elif search_type == "phone":
        phone_clean = query.replace("+", "").replace("-", "").replace(" ", "")
        tasks.append(_check_leakcheck(phone_clean, "phone", results))

    elif search_type == "username":
        tasks.append(_check_leakcheck(query, "username", results))

    await asyncio.gather(*tasks)

    return results


async def _check_emailrep(query: str, results: dict):
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(SOURCES["emailrep"].format(query), headers={"User-Agent": USER_AGENT})
            if r.status_code == 200:
                data = r.json()
                rep = data.get("reputation", "unknown")
                suspicious = data.get("suspicious", False)
                details = data.get("details", {})
                breaches = details.get("breaches", [])
                if breaches:
                    results["found"] = True
                    results["sources"].append("EmailRep.io")
                    results["details"].append({
                        "source": "EmailRep.io",
                        "reputation": rep,
                        "suspicious": suspicious,
                        "breaches": [b.get("name", b) for b in breaches[:10]],
                    })
    except Exception as e:
        logger.debug(f"emailrep check failed: {e}")


async def _check_leakcheck(query: str, lt: str, results: dict):
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(SOURCES["leakcheck"].format(query, lt), headers={"User-Agent": USER_AGENT})
            if r.status_code == 200:
                data = r.json()
                if data.get("success") and data.get("data"):
                    lines = data["data"]
                    if isinstance(lines, list) and len(lines) > 0:
                        results["found"] = True
                        results["sources"].append("LeakCheck")
                        sample = lines[:5]
                        results["details"].append({
                            "source": "LeakCheck",
                            "count": len(lines),
                            "sample": sample,
                        })
    except Exception as e:
        logger.debug(f"leakcheck check failed: {e}")
