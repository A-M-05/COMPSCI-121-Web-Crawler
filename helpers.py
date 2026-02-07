from imports import *

def has_trap_query(parsed) -> bool:
    """
    Check whether a URL contains query parameters known to generate crawler traps
    or infinite URL variants.
    """
    for k, _ in parse_qsl(parsed.query, keep_blank_values=True):
        if k.lower() in TRAP_QUERY_KEYS:
            return True
    return False

def has_trap_path(path: str) -> bool:
    """
    Check whether a URL path contains substrings associated with login pages,
    administrative interfaces, or other crawler traps.
    """
    p = path.lower()
    return any(t in p for t in TRAP_PATH_SUBSTRINGS)

def too_many_variants(url: str) -> bool:
    """
    Detect excessive query-string variations for the same path to prevent crawling
    infinite or near-duplicate URL families.
    """
    s = urlsplit(url)
    key = (s.netloc.lower(), s.path.lower())
    if not s.query:
        return False
    PATH_QUERY_SEEN[key].add(s.query)
    return len(PATH_QUERY_SEEN[key]) > MAX_VARIANTS_PER_PATH

def to_text(content : str) -> str:
    """
    Convert raw response content into a UTF-8 string suitable for HTML parsing.
    """
    if content is None:
        return ""
    if isinstance(content, bytes):
        return content.decode("utf-8", errors = "ignore")
    return str(content)

def extract_visible_text(html: str) -> str:
    """
    Extract visible, human-readable text from HTML by removing non-content elements
    such as scripts, styles, and navigation components.
    """

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
        tag.decompose()

    return soup.get_text(separator=" ", strip=True)

def tokenize_text(text: str) -> list[str]:
    """
    Extract all tokens from text excluding stop words.
    Returns list of tokens.
    """
    current = []
    tokens = []
    
    text_lower = text.lower()
    for char in text_lower:
        if char.isalnum() and char.isascii():
            current.append(char)
        else:
            if current:
                token = ''.join(current)
                if token not in STOP_WORDS:
                    tokens.append(token)
                current = []
    
    if current:
        token = ''.join(current)
        if token not in STOP_WORDS:
            tokens.append(token)
    
    return tokens

def host_allowed(host : str) -> bool:
    # Checks if hostname is allowed
    return any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)

def normalize_url(url: str) -> str:
    """
    Canonicalize a URL by lowercasing scheme and host, trimming trailing slashes,
    removing fragments, filtering query parameters, and producing a consistent form
    for duplicate detection.
    """
    s = urlsplit(url)
    scheme = s.scheme.lower()
    netloc = s.netloc.lower()
    path = s.path[:-1] if s.path.endswith("/") and s.path != "/" else s.path

    params = []
    for k, v in parse_qsl(s.query, keep_blank_values=False):
        kl = k.lower()
        if kl in TRAP_QUERY_KEYS:
            continue
        params.append((kl, v))
    params.sort()
    params = params[:MAX_PARAMS]
    query = urlencode(params, doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))

def link_extractor(raw_html: str, base_url: str):
    """
    Parse raw HTML content and extract all absolute, defragmented hyperlinks found
    in anchor tags.
    """
    html = to_text(raw_html)
    soup = BeautifulSoup(html, "html.parser")
    found = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        href = href.strip()
        if not href or href.startswith(("mailto:", "javascript:", "tel:")):
            continue
        joined = urljoin(base_url, href)
        defragged, _ = urldefrag(joined)
        found.add(normalize_url(defragged))
    return list(found)