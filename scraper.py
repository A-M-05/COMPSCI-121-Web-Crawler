from helpers import *  # import crawler utilities: parsing, normalization, trap checks, analytics, etc.


def scraper(url, resp):
    """
    Main scraping entrypoint called by the crawler worker.

    Responsibilities:
      - Validate the response (status/content/type)
      - Extract visible text and enforce minimum word threshold
      - Update crawl analytics for unique pages, longest page, word frequencies, subdomains
      - Extract outgoing links, normalize them, and filter them through is_valid()
      - Return the list of valid next URLs to add to the frontier
    """
    # If we got no response object or the underlying raw HTTP response is missing, stop.
    if resp is None or resp.raw_response is None:
        return []

    # Cache the HTTP status code for readability.
    status = resp.status

    # If the response status indicates a permanently bad/blocked/unreachable page,
    # record the final URL as "bad" so we can refuse it later and stop processing.
    if status in {404, 410, 403, 600, 601, 602, 603, 604, 605, 606, 607}:
        try:
            # Use the final URL after redirects if available; otherwise fall back to the input URL.
            final_url = resp.url or url
            # Remove URL fragments (#...) so variants of the same page collapse.
            final_url, _ = urldefrag(final_url)
            # Normalize URL (lowercase scheme/host, trim slash, drop trap query keys, etc.).
            final_url = normalize_url(final_url)
            # Add to global BAD_URLS set so future checks can reject it quickly.
            mark_bad_url(final_url)
        except Exception:
            # If anything goes wrong while marking bad, just ignore and move on.
            pass
        # Do not extract text or links from bad responses.
        return []

    # If it’s not a 200 OK, or there’s no body content, stop.
    if status != 200 or resp.raw_response.content is None:
        return []
    
    # Attempt to read the Content-Type header to ensure we're only processing HTML pages.
    content_type = ""
    try:
        # Grab Content-Type header (if present) and lower it for consistent matching.
        content_type = (resp.raw_response.headers.get("Content-Type") or "").lower()
    except Exception:
        # If headers are missing/malformed, keep content_type as empty string.
        pass

    # If Content-Type exists and it isn't HTML, skip it (e.g., PDF, images, etc.).
    if content_type and "text/html" not in content_type:
        return []

    # Convert raw bytes -> string HTML.
    html = to_text(resp.raw_response.content)
    # Strip scripts/styles/nav/etc and get visible text only.
    text = extract_visible_text(html)

    # Enforce minimum content threshold (prevents indexing near-empty boilerplate pages).
    # tokenize_with_stopwords counts "word-like" tokens (excluding pure digits).
    if len(tokenize_with_stopwords(text)) < MIN_WORDS:
        return []

    # Record analytics (unique page count, longest page, word/stopword frequencies, subdomains).
    update_analytics(resp.url, text)

    # Collect valid outgoing links.
    links = []
    # Extract all outgoing href links from the HTML response.
    for link in extract_next_links(url, resp):
        # Normalize the candidate link so variants collapse (fragment removed, trap queries dropped, etc.).
        n = normalize_url(link)
        # Only keep the link if it passes validity/trap checks.
        if is_valid(n):
            links.append(n)
    # Return all valid links to add to the crawl frontier.
    return links


def extract_next_links(url, resp):
    """
    Extract all outgoing links from the HTML page.

    Returns:
      A list of defragmented (fragment removed) absolute URLs.
      (No validity filtering happens here; that is done in is_valid().)
    """
    # Convert raw bytes -> string HTML.
    html = to_text(resp.raw_response.content)
    # Parse HTML to find <a href="..."> links.
    soup = BeautifulSoup(html, "html.parser")
    # Use a set to deduplicate links found on this page.
    found = set()

    # Iterate all anchor tags that have an href attribute.
    for a in soup.find_all("a", href=True):
        # Pull and trim the href value.
        href = a["href"].strip()
        # Skip empty hrefs and non-web link schemes we don't want to crawl.
        if not href or href.startswith(("mailto:", "javascript:", "tel:")):
            continue
        try:
            # Convert relative links to absolute URLs using the page's final URL as base.
            joined = urljoin(resp.url, href)
            # Remove fragments so #section links collapse to the same page.
            defragged, _ = urldefrag(joined)
        except ValueError:
            # urljoin/urlparse can raise ValueError on malformed bracketed netlocs (e.g. [YOUR_IP]).
            continue
        # Keep the cleaned URL.
        found.add(defragged)

    # Convert set back to list for the crawler.
    return list(found)


def is_valid(url):
    """
    Decide whether a URL should be crawled.

    Filters:
      - scheme must be http/https
      - hostname must be in allowed domains
      - reject known bad URLs
      - path/query trap checks
      - query-variant explosion checks
      - special-case trap rules for event calendars and doku.php
      - reject unwanted file extensions
    """
    try:
        # Parse URL into components.
        parsed = urlparse(url)

        # Only allow HTTP(S) URLs.
        if parsed.scheme not in {"http", "https"}:
            return False

        # Host must exist and must be within allowed domains.
        if parsed.hostname is None or not host_allowed(parsed.hostname):
            return False

        # Normalize URL and reject if it's already known as bad.
        n = normalize_url(url)
        if is_bad_url(n):
            return False

        # Reject if path looks like a known trap pattern.
        if has_trap_path(parsed.path):
            return False

        # Reject if query contains trap keys.
        if has_trap_query(parsed):
            return False

        # Reject if this (host,path) has too many distinct query variants.
        if too_many_variants(url):
            return False

        # Work with lowercased path for consistent substring checks.
        path = parsed.path.lower()

        # Extra hardening for common events/calendar traps:
        # If URL is under /events/ and contains calendar browsing patterns, reject.
        if "/events/" in path:
            if any(x in path for x in ("/day/", "/list", "/month")):
                return False

        # Extra hardening for DokuWiki traps (common on some ics.uci.edu sites).
        if "doku.php" in path:
            # Convert query string into a dict for key-based checks.
            params = dict(parse_qsl(parsed.query))
            # Block certain DokuWiki actions known to generate infinite pages.
            blocked_actions = {"search", "recent", "index", "revisions", "backlink"}

            # If 'do' action is one of the blocked actions, reject.
            if params.get("do") in blocked_actions:
                return False
            # 'rev' often causes revision browsing (trap).
            if "rev" in params:
                return False
            # 'idx' without 'id' is often index browsing rather than content.
            if params.get("idx") and not params.get("id"):
                return False

        # Finally, reject URLs that look like non-HTML resources based on file extension.
        # (path is already lowercased above)
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
        # Any parsing/normalization failure => treat as invalid.
        return False