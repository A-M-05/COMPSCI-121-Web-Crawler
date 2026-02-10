from helpers import *


def scraper(url, resp):
    if resp is None or resp.raw_response is None:
        return []

    status = resp.status

    if status in {404, 410, 403, 600, 601, 602, 603, 604, 605, 606, 607}:
        try:
            final_url = resp.url or url
            final_url, _ = urldefrag(final_url)
            final_url = normalize_url(final_url)
            mark_bad_url(final_url)
        except Exception:
            pass
        return []

    if status != 200 or resp.raw_response.content is None:
        return []

    html = to_text(resp.raw_response.content)
    text = extract_visible_text(html)

    if count_all_words(text) < MIN_WORDS:
        return []

    update_analytics(resp.url, text)

    links = []
    for link in extract_next_links(url, resp):
        n = normalize_url(link)
        if is_valid(n):
            links.append(n)
    return links


def extract_next_links(url, resp):
    html = to_text(resp.raw_response.content)
    soup = BeautifulSoup(html, "html.parser")
    found = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("mailto:", "javascript:", "tel:")):
            continue
        try:
            joined = urljoin(resp.url, href)
            defragged, _ = urldefrag(joined)
        except ValueError:
            continue
        found.add(defragged)

    return list(found)


def is_valid(url):
    try:
        parsed = urlparse(url)

        if parsed.scheme not in {"http", "https"}:
            return False

        if parsed.hostname is None or not host_allowed(parsed.hostname):
            return False

        n = normalize_url(url)
        if is_bad_url(n):
            return False

        if has_trap_path(parsed.path):
            return False

        if has_trap_query(parsed):
            return False

        if too_many_variants(url):
            return False

        path = parsed.path.lower()

        if "/events/" in path:
            if any(x in path for x in ("/day/", "/list", "/month")):
                return False

        if "doku.php" in path:
            params = dict(parse_qsl(parsed.query))
            blocked_actions = {"search", "recent", "index", "revisions", "backlink"}

            if params.get("do") in blocked_actions:
                return False
            if "rev" in params:
                return False
            if params.get("idx") and not params.get("id"):
                return False

        return not re.match(
            r".*\.(css|js|bmp|gif|jpe?g|ico"
            r"|png|tiff?|mid|mp2|mp3|mp4"
            r"|wav|avi|mov|mpeg|ram|m4v|mkv|ogg|ogv|pdf"
            r"|ps|eps|tex|ppt|pptx|doc|docx|xls|xlsx|names"
            r"|data|dat|exe|bz2|tar|msi|bin|7z|psd|dmg|iso"
            r"|epub|dll|cnf|tgz|sha1"
            r"|thmx|mso|arff|rtf|jar|csv"
            r"|rm|smil|wmv|swf|wma|zip|rar|gz"
            r"|apk|ipa|deb|rpm|img|toast|vcd"
            r"|txt|ppsx|pps|potx|pot|pptm|potm|ppam|ppsm)$",
            path
        )

    except Exception:
        return False