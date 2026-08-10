import requests
from config import WIKIMEDIA_API_URL


class WikimediaClient:
    def __init__(self, timeout=20):
        self.timeout = timeout

    def nearby_pages(self, latitude, longitude, radius_m=10000, limit=30):
        response = requests.get(
            WIKIMEDIA_API_URL,
            params={
                "action": "query",
                "list": "geosearch",
                "gscoord": f"{latitude}|{longitude}",
                "gsradius": radius_m,
                "gslimit": limit,
                "format": "json",
                "origin": "*",
            },
            headers={"User-Agent": "TrailWiseAI-EducationalCapstone/1.0"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        hits = response.json().get("query", {}).get("geosearch", [])
        if not hits:
            return []

        pageids = "|".join(str(x["pageid"]) for x in hits)
        details = requests.get(
            WIKIMEDIA_API_URL,
            params={
                "action": "query",
                "pageids": pageids,
                "prop": "extracts|pageimages|info",
                "exintro": 1,
                "explaintext": 1,
                "inprop": "url",
                "piprop": "thumbnail",
                "pithumbsize": 600,
                "format": "json",
                "origin": "*",
            },
            headers={"User-Agent": "TrailWiseAI-EducationalCapstone/1.0"},
            timeout=self.timeout,
        )
        details.raise_for_status()
        pages = details.json().get("query", {}).get("pages", {})

        by_id = {str(x["pageid"]): x for x in hits}
        output = []
        for pageid, page in pages.items():
            geo = by_id.get(str(pageid), {})
            extract = (page.get("extract") or "").strip()
            if not extract:
                continue
            output.append(
                {
                    "external_id": str(pageid),
                    "title": page.get("title"),
                    "description": extract,
                    "source_url": page.get("fullurl"),
                    "image_url": (page.get("thumbnail") or {}).get("source"),
                    "latitude": geo.get("lat"),
                    "longitude": geo.get("lon"),
                    "distance_m": geo.get("dist"),
                }
            )
        return output
